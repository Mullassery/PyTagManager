"""Live GTM Management API v2 (tagmanager.googleapis.com) client.

Distinct from `pytagmanager.export.gtm.build_gtm_container`, which only
*builds* a static container JSON for hand-import -- this client *retrieves*
a real container's currently published configuration, which
`pytagmanager.diagnostics.rules` compares against runtime dataLayer/network
behavior.

`GtmApiClient` takes an already-built `service` object so it is fully
unit-testable without real network calls; `from_service_account` is the
real-world constructor requiring the caller's own GCP credentials.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pytagmanager.analytics_api.models import GtmTag, GtmTrigger

GTM_READONLY_SCOPE = "https://www.googleapis.com/auth/tagmanager.readonly"


def _extract_custom_event_name(raw_trigger: dict) -> Optional[str]:
    """GTM represents a Custom Event trigger's "Event name equals X"
    condition as a `customEventFilter`: an EQUALS filter comparing the
    built-in `{{_event}}` variable (arg0) against a literal string (arg1).
    Returns that literal when present, else None (e.g. for a plain CLICK
    trigger that doesn't gate on a dataLayer event name at all).
    """
    for filt in raw_trigger.get("customEventFilter", []):
        if filt.get("type") != "EQUALS":
            continue
        params = {p.get("key"): p.get("value") for p in filt.get("parameter", [])}
        if params.get("arg0") == "{{_event}}" and "arg1" in params:
            return params["arg1"]
    return None


def _normalize_trigger(raw: dict) -> GtmTrigger:
    return GtmTrigger(
        trigger_id=raw.get("triggerId", ""),
        name=raw.get("name", ""),
        type=raw.get("type", ""),
        event_name=_extract_custom_event_name(raw),
    )


def _normalize_tag(raw: dict) -> GtmTag:
    return GtmTag(
        tag_id=raw.get("tagId", ""),
        name=raw.get("name", ""),
        type=raw.get("type", ""),
        firing_trigger_ids=list(raw.get("firingTriggerId", [])),
        parameters={p.get("key"): p.get("value") for p in raw.get("parameter", []) if p.get("key")},
    )


class GtmApiClient:
    def __init__(self, service: Any):
        self._service = service

    @classmethod
    def from_service_account(cls, key_path: str, scopes: Optional[List[str]] = None) -> "GtmApiClient":
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=scopes or [GTM_READONLY_SCOPE]
        )
        return cls(build("tagmanager", "v2", credentials=credentials, cache_discovery=False))

    @classmethod
    def from_oauth_user(cls, credentials: Any) -> "GtmApiClient":
        from googleapiclient.discovery import build

        return cls(build("tagmanager", "v2", credentials=credentials, cache_discovery=False))

    def find_container_by_public_id(self, public_id: str) -> Optional[Dict[str, Any]]:
        """`public_id` is the "GTM-XXXXXXX" string from a site's GTM
        snippet. The API addresses containers by internal account/container
        resource path, not this string, so accessible accounts/containers
        are scanned to resolve it. Returns the raw container resource, or
        None if the calling credentials can't see a matching container.
        """
        accounts = self._service.accounts().list().execute().get("account", [])
        for account in accounts:
            containers = (
                self._service.accounts().containers().list(parent=account["path"]).execute().get("container", [])
            )
            for container in containers:
                if container.get("publicId") == public_id:
                    return container
        return None

    def get_live_container_config(self, container_path: str) -> Dict[str, List]:
        """Fetch the currently *live* (published) container version -- the
        config actually running on the site right now, not an unpublished
        draft workspace, since that's what runtime behavior should be
        compared against.
        """
        version = self._service.accounts().containers().versions().live(parent=container_path).execute()
        return {
            "triggers": [_normalize_trigger(t) for t in version.get("trigger", [])],
            "tags": [_normalize_tag(t) for t in version.get("tag", [])],
        }
