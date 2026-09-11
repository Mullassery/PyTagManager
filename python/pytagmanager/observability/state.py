"""Runtime state snapshot: cookies, localStorage, sessionStorage, and the
full `window.dataLayer` contents, captured at a point in time (page load,
or before/after a scenario step).

Fills the gap `docs/VISION.md` (Phase 1.6) is built on: before this, the
browser agent only ever observed `dataLayer.push()` *events* as they
happened, and cookies/localStorage/sessionStorage weren't captured at all.

**Privacy discipline:** a cookie/localStorage/sessionStorage *value* is
live session/credential state -- a materially more sensitive class of data
than a marketing dataLayer payload. By default only each key's name,
inferred type, and length are captured; raw values require
`capture_values=True` (`ObservationSession(..., capture_storage_values=True)`
/ `diagnose --capture-storage-values`), and even then a value is replaced
with a redaction marker when its key name looks sensitive (see
`events.is_sensitive_key` -- the same denylist `redact_payload` uses).
`dataLayer` contents are captured in full regardless, consistent with the
existing `dataLayer.push` event capture, which has never been gated.

**Known limitation:** `document.cookie` (browser JS) cannot see
`HttpOnly` cookies -- a browser security restriction, not a gap in this
implementation. Cookie capture therefore goes through Playwright's
CDP-backed `BrowserContext.cookies()` instead (see `session.py`), which
*does* see `HttpOnly` cookies, unlike a pure-JS approach.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pytagmanager.observability.events import is_sensitive_key, redact_payload

_REDACTED = "[REDACTED]"


@dataclass(frozen=True)
class StorageEntry:
    """One cookie / localStorage / sessionStorage key's captured shape."""

    key: str
    value_type: str  # "string" | "json_object" | "json_array" | "number" | "boolean" | "empty"
    length: int
    value: Optional[Any] = None  # populated only when values were captured


@dataclass(frozen=True)
class RuntimeStateSnapshot:
    """Cookies + localStorage + sessionStorage + dataLayer, captured at one
    instant. `label` distinguishes snapshots taken around the same page
    visit, e.g. "page_load", "before:step_0_click", "after:step_0_click".
    """

    page_url: str
    timestamp: float
    label: str
    cookies: Dict[str, StorageEntry] = field(default_factory=dict)
    local_storage: Dict[str, StorageEntry] = field(default_factory=dict)
    session_storage: Dict[str, StorageEntry] = field(default_factory=dict)
    data_layer: List[Dict[str, Any]] = field(default_factory=list)
    data_layer_truncated: bool = False

    @classmethod
    def from_raw(
        cls,
        js_state: dict,
        *,
        cookies: List[dict],
        page_url: str,
        timestamp: float,
        label: str,
    ) -> "RuntimeStateSnapshot":
        """`js_state` is `window.__ptm.captureState(...)`'s return value
        (localStorage/sessionStorage/dataLayer); `cookies` is Playwright's
        `BrowserContext.cookies()` list (name/value/httpOnly/secure/...).
        """
        return cls(
            page_url=page_url,
            timestamp=timestamp,
            label=label,
            cookies=_entries_from_cookie_list(cookies),
            local_storage=_entries_from_js(js_state.get("localStorage", {})),
            session_storage=_entries_from_js(js_state.get("sessionStorage", {})),
            data_layer=[
                redact_payload(item) if isinstance(item, dict) else item
                for item in js_state.get("dataLayer", [])
            ],
            data_layer_truncated=bool(js_state.get("dataLayerTruncated", False)),
        )


def _classify_raw_value(raw: str) -> tuple:
    if raw is None or raw == "":
        return "empty", 0
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return "string", len(raw)
    if isinstance(parsed, list):
        return "json_array", len(raw)
    if isinstance(parsed, dict):
        return "json_object", len(raw)
    if isinstance(parsed, bool):
        return "boolean", len(raw)
    if isinstance(parsed, (int, float)):
        return "number", len(raw)
    return "string", len(raw)


def _redact_value_if_sensitive(key: str, value: Optional[Any]) -> Optional[Any]:
    if value is not None and is_sensitive_key(key):
        return _REDACTED
    return value


def _entries_from_js(raw_entries: dict) -> Dict[str, StorageEntry]:
    entries: Dict[str, StorageEntry] = {}
    for key, meta in (raw_entries or {}).items():
        value = meta.get("value")
        entries[key] = StorageEntry(
            key=key,
            value_type=meta.get("type", "string"),
            length=int(meta.get("length", 0)),
            value=_redact_value_if_sensitive(key, value),
        )
    return entries


def _entries_from_cookie_list(cookies: List[dict]) -> Dict[str, StorageEntry]:
    entries: Dict[str, StorageEntry] = {}
    for cookie in cookies or []:
        key = cookie.get("name", "")
        raw_value = cookie.get("value")
        value_type, length = _classify_raw_value(raw_value if raw_value is not None else "")
        entries[key] = StorageEntry(
            key=key,
            value_type=value_type,
            length=length,
            value=_redact_value_if_sensitive(key, raw_value),
        )
    return entries


@dataclass(frozen=True)
class StateDiff:
    """What changed between two `RuntimeStateSnapshot`s of the same page
    visit -- the before/after diffing `docs/ROADMAP.md` Phase 1.6 calls
    for around each interaction."""

    before_label: str
    after_label: str
    cookies_added: List[str] = field(default_factory=list)
    cookies_removed: List[str] = field(default_factory=list)
    cookies_modified: List[str] = field(default_factory=list)
    local_storage_added: List[str] = field(default_factory=list)
    local_storage_removed: List[str] = field(default_factory=list)
    local_storage_modified: List[str] = field(default_factory=list)
    session_storage_added: List[str] = field(default_factory=list)
    session_storage_removed: List[str] = field(default_factory=list)
    session_storage_modified: List[str] = field(default_factory=list)
    new_data_layer_events: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.cookies_added
            or self.cookies_removed
            or self.cookies_modified
            or self.local_storage_added
            or self.local_storage_removed
            or self.local_storage_modified
            or self.session_storage_added
            or self.session_storage_removed
            or self.session_storage_modified
            or self.new_data_layer_events
        )


def _diff_entries(before: Dict[str, StorageEntry], after: Dict[str, StorageEntry]):
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(
        key
        for key in (set(before) & set(after))
        if (before[key].value, before[key].value_type, before[key].length)
        != (after[key].value, after[key].value_type, after[key].length)
    )
    return added, removed, modified


def _new_data_layer_event_names(before_items: List[dict], after_items: List[dict]) -> List[str]:
    def _fingerprint(item: Any) -> str:
        return json.dumps(item, sort_keys=True, default=str)

    seen = {_fingerprint(item) for item in before_items}
    return [
        item.get("event", "") if isinstance(item, dict) else ""
        for item in after_items
        if _fingerprint(item) not in seen
    ]


def diff_state_snapshots(before: RuntimeStateSnapshot, after: RuntimeStateSnapshot) -> StateDiff:
    cookies_added, cookies_removed, cookies_modified = _diff_entries(before.cookies, after.cookies)
    ls_added, ls_removed, ls_modified = _diff_entries(before.local_storage, after.local_storage)
    ss_added, ss_removed, ss_modified = _diff_entries(before.session_storage, after.session_storage)
    return StateDiff(
        before_label=before.label,
        after_label=after.label,
        cookies_added=cookies_added,
        cookies_removed=cookies_removed,
        cookies_modified=cookies_modified,
        local_storage_added=ls_added,
        local_storage_removed=ls_removed,
        local_storage_modified=ls_modified,
        session_storage_added=ss_added,
        session_storage_removed=ss_removed,
        session_storage_modified=ss_modified,
        new_data_layer_events=_new_data_layer_event_names(before.data_layer, after.data_layer),
    )
