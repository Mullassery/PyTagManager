"""Filesystem-based CDN publication with immutable revisions and atomic pointers."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import posixpath
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from pytagmanager.control.errors import ConflictError, NotFoundError, ValidationError
from pytagmanager.control.ids import container_storage_key, utc_now
from pytagmanager.control.service import ControlPlaneService
from pytagmanager.distribution.public_config import (
    build_published_config,
    environment_slug,
    verify_published_config,
)

try:  # pragma: no cover - platform-specific locking
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None
try:  # pragma: no cover
    import msvcrt
except ImportError:  # pragma: no cover
    msvcrt = None

WEB_SDK_NAME = "pytagmanager-web"
PUBLISHED_SCHEMA_VERSION = "1.0"
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
POINTER_CACHE = "no-cache, max-age=0, must-revalidate"


@dataclass(frozen=True)
class PublishResult:
    container_id: str
    environment: str
    config_version: str
    revision_number: int
    config_path: str
    latest_path: str
    manifest_path: str
    config_url: str
    latest_url: str
    integrity_digest: str
    file_sha256: str
    sdk_version: str
    sdk_path: str
    published_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "container_id": self.container_id,
            "environment": self.environment,
            "config_version": self.config_version,
            "revision_number": self.revision_number,
            "config_path": self.config_path,
            "latest_path": self.latest_path,
            "manifest_path": self.manifest_path,
            "config_url": self.config_url,
            "latest_url": self.latest_url,
            "integrity_digest": self.integrity_digest,
            "file_sha256": self.file_sha256,
            "sdk_version": self.sdk_version,
            "sdk_path": self.sdk_path,
            "published_at": self.published_at,
        }


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Any, *, pretty: bool = True) -> bytes:
    if pretty:
        text = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    else:
        text = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
    return text.encode("utf-8")


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise


def _write_immutable(path: Path, data: bytes, *, label: str) -> None:
    if path.exists():
        existing = path.read_bytes()
        if existing != data:
            raise ConflictError(
                f"{label} already exists with different contents: {path}"
            )
        return
    _atomic_write(path, data)


@contextmanager
def _publish_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".publish.lock"
    with lock_path.open("a+b") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        elif msvcrt is not None:  # pragma: no cover
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _join_url(base_url: str | None, path: str) -> str:
    if not base_url:
        return "/" + path.lstrip("/")
    return base_url.rstrip("/") + "/" + path.lstrip("/")


class FilesystemCDN:
    """Publish static CDN artifacts under a local directory.

    The layout is provider-neutral. A self-hosted web server, object storage
    bucket, or static host can serve the tree; ``_headers.json`` describes the
    required cache policy for each immutable or mutable path.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        base_url: str | None = None,
        sdk_version: str = "0.1.0",
        sdk_asset: str | Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.base_url = base_url.rstrip("/") if base_url else None
        self.sdk_version = sdk_version
        default_asset = Path(__file__).with_name("assets") / "pytagmanager.js"
        self.sdk_asset = Path(sdk_asset) if sdk_asset is not None else default_asset

    def publish_environment(
        self,
        service: ControlPlaneService,
        container_id: str,
        environment_ref: str,
        *,
        org_id: str | None = None,
        default_consent: Mapping[str, bool] | None = None,
        min_sdk: Mapping[str, str] | None = None,
        allow_protected: bool = False,
        published_at: str | None = None,
    ) -> PublishResult:
        container = service.get_container(container_id, org_id=org_id)
        config = build_published_config(
            service,
            container_id,
            environment_ref,
            org_id=org_id,
            published_at=published_at,
            default_consent=default_consent,
            min_sdk=min_sdk,
            allow_protected=allow_protected,
        )
        container_key = container_storage_key(container.org_id, container.container_id)
        slug = environment_slug(config["environment"]["name"])
        config_version = config["config_version"]
        base = f"containers/{container_key}"
        config_path = f"{base}/revisions/{config_version}/config.json"
        latest_path = f"{base}/environments/{slug}/latest.json"
        manifest_path = f"{base}/environments/{slug}/manifest.json"
        sdk_path = f"sdk/web/{self.sdk_version}/pytagmanager.js"

        existing_config_path = self.root / config_path
        if existing_config_path.is_file():
            try:
                existing = json.loads(existing_config_path.read_text(encoding="utf-8"))
                if (
                    existing.get("container_id") != container.container_id
                    or existing.get("config_version") != config_version
                ):
                    raise ConflictError(
                        f"published configuration identity mismatch: {existing_config_path}"
                    )
                verify_published_config(existing)
                config = existing
            except (OSError, json.JSONDecodeError, ValidationError) as exc:
                raise ConflictError(
                    f"existing published configuration is unreadable or invalid: {exc}"
                ) from exc
        config_bytes = existing_config_path.read_bytes() if existing_config_path.is_file() else _json_bytes(config)
        file_sha256 = _sha256_bytes(config_bytes)
        integrity_digest = verify_published_config(config)

        if not self.sdk_asset.is_file():
            raise NotFoundError(f"Web SDK asset not found: {self.sdk_asset}")
        sdk_bytes = self.sdk_asset.read_bytes()
        sdk_digest = _sha256_bytes(sdk_bytes)

        with _publish_lock(self.root):
            _write_immutable(
                self.root / config_path,
                config_bytes,
                label="published configuration",
            )
            _write_immutable(
                self.root / f"{config_path}.sha256",
                f"{file_sha256}  config.json\n".encode("ascii"),
                label="published configuration checksum",
            )
            _write_immutable(
                self.root / sdk_path,
                sdk_bytes,
                label="Web SDK asset",
            )
            _write_immutable(
                self.root / f"{sdk_path}.sha256",
                f"{sdk_digest}  pytagmanager.js\n".encode("ascii"),
                label="Web SDK checksum",
            )

            latest = {
                "schema_version": PUBLISHED_SCHEMA_VERSION,
                "kind": "pytagmanager.environment",
                "container_id": container.container_id,
                "environment": {
                    "name": config["environment"]["name"],
                    "slug": slug,
                    "protected": config["environment"]["protected"],
                },
                "config_version": config_version,
                "revision_number": config["revision_number"],
                "config_path": f"revisions/{config_version}/config.json",
                "config_url": _join_url(
                    self.base_url, f"{base}/revisions/{config_version}/config.json"
                ),
                "config_file_sha256": file_sha256,
                "integrity_digest": integrity_digest,
                "sdk": {
                    "web": {
                        "version": self.sdk_version,
                        "path": sdk_path,
                        "url": _join_url(self.base_url, sdk_path),
                        "sha256": sdk_digest,
                    }
                },
                "published_at": config["published_at"],
                "cache": {"max_age_seconds": 0, "immutable": False},
            }
            latest_bytes = _json_bytes(latest)
            _atomic_write(self.root / latest_path, latest_bytes)
            _atomic_write(
                self.root / f"{latest_path}.sha256",
                f"{_sha256_bytes(latest_bytes)}  latest.json\n".encode("ascii"),
            )

            manifest = self._build_manifest(
                base,
                config,
                slug,
                config_path,
                file_sha256,
                integrity_digest,
                sdk_path,
                sdk_digest,
            )
            _atomic_write(self.root / manifest_path, _json_bytes(manifest))
            self._update_headers(base, slug, self.sdk_version, config_version)
            _atomic_write(
                self.root / "index.json",
                _json_bytes(self._build_index()),
            )

        return PublishResult(
            container_id=container.container_id,
            environment=config["environment"]["name"],
            config_version=config_version,
            revision_number=config["revision_number"],
            config_path=config_path,
            latest_path=latest_path,
            manifest_path=manifest_path,
            config_url=_join_url(self.base_url, config_path),
            latest_url=_join_url(self.base_url, latest_path),
            integrity_digest=integrity_digest,
            file_sha256=file_sha256,
            sdk_version=self.sdk_version,
            sdk_path=sdk_path,
            published_at=config["published_at"],
        )

    def _build_manifest(
        self,
        base: str,
        config: Mapping[str, Any],
        slug: str,
        config_path: str,
        file_sha256: str,
        integrity_digest: str,
        sdk_path: str,
        sdk_digest: str,
    ) -> dict[str, Any]:
        manifest_path = self.root / base / "environments" / slug / "manifest.json"
        existing: dict[str, Any] = {}
        if manifest_path.is_file():
            try:
                loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = loaded
            except (OSError, json.JSONDecodeError):
                existing = {}
        revisions = {
            item.get("config_version"): item
            for item in existing.get("revisions", [])
            if isinstance(item, dict) and item.get("config_version")
        }
        revisions[config["config_version"]] = {
            "config_version": config["config_version"],
            "revision_number": config["revision_number"],
            "config_path": f"revisions/{config['config_version']}/config.json",
            "file_sha256": file_sha256,
            "integrity_digest": integrity_digest,
            "published_at": config["published_at"],
        }
        return {
            "schema_version": PUBLISHED_SCHEMA_VERSION,
            "kind": "pytagmanager.publication-manifest",
            "container_id": config["container_id"],
            "environment": {
                "name": config["environment"]["name"],
                "slug": slug,
                "protected": config["environment"]["protected"],
            },
            "current_config_version": config["config_version"],
            "published_at": config["published_at"],
            "revisions": sorted(
                revisions.values(),
                key=lambda item: item["revision_number"],
                reverse=True,
            ),
            "sdk_assets": [
                {"platform": "web", "version": self.sdk_version, "path": sdk_path, "sha256": sdk_digest}
            ],
        }

    def _build_index(self) -> dict[str, Any]:
        containers = []
        root = self.root / "containers"
        if root.is_dir():
            for container_dir in sorted(root.iterdir()):
                if not container_dir.is_dir():
                    continue
                environments_dir = container_dir / "environments"
                if not environments_dir.is_dir():
                    continue
                for environment_dir in sorted(environments_dir.iterdir()):
                    latest = environment_dir / "latest.json"
                    if not latest.is_file():
                        continue
                    try:
                        document = json.loads(latest.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    containers.append(
                        {
                            "container_id": document.get("container_id"),
                            "environment": document.get("environment", {}).get("name"),
                            "config_version": document.get("config_version"),
                            "latest_path": latest.relative_to(self.root).as_posix(),
                            "published_at": document.get("published_at"),
                        }
                    )
        containers.sort(
            key=lambda item: (
                str(item.get("container_id") or ""),
                str(item.get("environment") or ""),
            )
        )
        return {
            "schema_version": PUBLISHED_SCHEMA_VERSION,
            "kind": "pytagmanager.cdn-index",
            "generated_at": utc_now(),
            "publications": containers,
        }

    def _update_headers(
        self,
        base: str,
        slug: str,
        sdk_version: str,
        config_version: str,
    ) -> None:
        path = self.root / "_headers.json"
        headers: dict[str, Any] = {}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    headers = loaded
            except (OSError, json.JSONDecodeError):
                headers = {}
        headers[f"/sdk/web/{sdk_version}/pytagmanager.js"] = {
            "Cache-Control": IMMUTABLE_CACHE,
            "Content-Type": "application/javascript; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
        }
        headers[
            f"/{base}/revisions/{config_version}/config.json"
        ] = {
            "Cache-Control": IMMUTABLE_CACHE,
            "Content-Type": "application/json; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
            "Access-Control-Allow-Origin": "*",
        }
        headers[f"/{base}/environments/{slug}/latest.json"] = {
            "Cache-Control": POINTER_CACHE,
            "Content-Type": "application/json; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
            "Access-Control-Allow-Origin": "*",
        }
        headers[f"/{base}/environments/{slug}/manifest.json"] = {
            "Cache-Control": POINTER_CACHE,
            "Content-Type": "application/json; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
        }
        headers["/index.json"] = {
            "Cache-Control": POINTER_CACHE,
            "Content-Type": "application/json; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
        }
        _atomic_write(path, _json_bytes(headers))

    def read_manifest(
        self, container_id: str, environment_ref: str, *, org_id: str
    ) -> dict[str, Any]:
        key = container_storage_key(org_id, container_id)
        base = self.root / "containers" / key / "environments"
        candidates = []
        if base.is_dir():
            for directory in base.iterdir():
                manifest = directory / "manifest.json"
                if not manifest.is_file():
                    continue
                try:
                    document = json.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if (
                    str(document.get("environment", {}).get("name", "")).casefold()
                    == environment_ref.casefold()
                    or str(document.get("environment", {}).get("slug", "")).casefold()
                    == environment_ref.casefold()
                ):
                    candidates.append(document)
        if not candidates:
            raise NotFoundError(
                f"no published manifest for container {container_id!r} environment "
                f"{environment_ref!r}"
            )
        return candidates[0]

    def verify(self) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        containers = self.root / "containers"
        if not containers.is_dir():
            return [{"path": "containers", "message": "no published containers"}]
        for manifest_path in sorted(containers.glob("*/environments/*/manifest.json")):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                issues.append({"path": str(manifest_path), "message": f"invalid manifest: {exc}"})
                continue
            container_key = manifest_path.parents[2].name
            for revision in manifest.get("revisions", []):
                if not isinstance(revision, dict):
                    continue
                config_path = revision.get("config_path")
                if not isinstance(config_path, str):
                    continue
                path = self.root / "containers" / container_key / config_path
                if not path.is_file():
                    issues.append({"path": str(path), "message": "missing configuration"})
                    continue
                data = path.read_bytes()
                if _sha256_bytes(data) != revision.get("file_sha256"):
                    issues.append({"path": str(path), "message": "file checksum mismatch"})
                    continue
                try:
                    document = json.loads(data)
                    verify_published_config(document)
                except (json.JSONDecodeError, ValidationError) as exc:
                    issues.append({"path": str(path), "message": f"integrity failure: {exc}"})
                    continue
                if document.get("config_version") != revision.get("config_version"):
                    issues.append({"path": str(path), "message": "revision identity mismatch"})
            latest = manifest_path.parent / "latest.json"
            if latest.is_file():
                try:
                    pointer = json.loads(latest.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    issues.append({"path": str(latest), "message": f"invalid pointer: {exc}"})
                    continue
                if pointer.get("config_version") != manifest.get("current_config_version"):
                    issues.append(
                        {"path": str(latest), "message": "latest pointer does not match manifest"}
                    )
        return issues


def write_static_server_config(root: str | Path) -> Path:
    """Write a minimal provider-neutral cache policy example."""
    destination = Path(root) / "CACHE_POLICY.md"
    content = """# PyTagManager CDN cache policy

- SDK assets and revision configs: `Cache-Control: public, max-age=31536000, immutable`
- `latest.json`, manifests, and `index.json`: `Cache-Control: no-cache, max-age=0, must-revalidate`
- Serve revision configs and SDK assets with `X-Content-Type-Options: nosniff`.
- Do not cache `latest.json` in shared caches: rollback depends on it changing.
- `_headers.json` is machine-readable metadata for a static host adapter.
- A CDN is not an event collection service; collection endpoints are separate.
"""
    _atomic_write(destination, content.encode("utf-8"))
    return destination


def copy_tree(source: str | Path, destination: str | Path) -> None:
    """Test/helper utility for packaging a published tree."""
    shutil.copytree(source, destination, dirs_exist_ok=True)
