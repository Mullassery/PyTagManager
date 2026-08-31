"""Live GA4 Admin API (config) + Data API (realtime ingestion) client.

The Admin API side plays the same "what's configured" role for GA4 that
GtmApiClient plays for GTM: registered custom dimensions and conversion
events. The Data API's realtime report additionally lets diagnostics
confirm an observed event was actually *ingested* server-side, which is
stronger evidence than "a network request was sent" (client-side network
sniffing can't tell you whether an ad-blocker silently dropped the
request, or GA4 rejected a malformed hit).
"""

from __future__ import annotations

from typing import Any, List, Optional

from pytagmanager.analytics_api.models import Ga4CustomDimension, Ga4EventDefinition

GA4_READONLY_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


class Ga4ApiClient:
    def __init__(self, admin_service: Any, data_service: Any):
        self._admin = admin_service
        self._data = data_service

    @classmethod
    def from_service_account(cls, key_path: str, scopes: Optional[List[str]] = None) -> "Ga4ApiClient":
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            key_path, scopes=scopes or [GA4_READONLY_SCOPE]
        )
        admin_service = build("analyticsadmin", "v1beta", credentials=credentials, cache_discovery=False)
        data_service = build("analyticsdata", "v1beta", credentials=credentials, cache_discovery=False)
        return cls(admin_service, data_service)

    def list_custom_dimensions(self, property_id: str) -> List[Ga4CustomDimension]:
        response = self._admin.properties().customDimensions().list(parent=f"properties/{property_id}").execute()
        return [
            Ga4CustomDimension(
                parameter_name=item.get("parameterName", ""),
                display_name=item.get("displayName", ""),
                scope=item.get("scope", ""),
            )
            for item in response.get("customDimensions", [])
        ]

    def list_conversion_events(self, property_id: str) -> List[Ga4EventDefinition]:
        response = self._admin.properties().conversionEvents().list(parent=f"properties/{property_id}").execute()
        return [Ga4EventDefinition(event_name=item.get("eventName", "")) for item in response.get("conversionEvents", [])]

    def was_event_ingested_realtime(self, property_id: str, event_name: str) -> Optional[bool]:
        """Returns True/False when the realtime report can answer the
        question, or None when the API call itself failed/was unavailable --
        diagnostics must not treat "couldn't check" as "confirmed missing",
        which would be a false positive.
        """
        try:
            response = (
                self._data.properties()
                .runRealtimeReport(
                    property=f"properties/{property_id}",
                    body={
                        "dimensions": [{"name": "eventName"}],
                        "metrics": [{"name": "eventCount"}],
                        "dimensionFilter": {
                            "filter": {"fieldName": "eventName", "stringFilter": {"value": event_name}}
                        },
                    },
                )
                .execute()
            )
        except Exception:
            return None
        rows = response.get("rows", [])
        return any(int(row["metricValues"][0]["value"]) > 0 for row in rows)
