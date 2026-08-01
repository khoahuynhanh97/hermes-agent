from __future__ import annotations

import json
import os
from typing import Any, Protocol

from hermes.domain.affiliate_research import ProjectionResult
from hermes.ports.affiliate_research import AffiliateResearchRepository


class SheetsClient(Protocol):
    def read_rows(self, spreadsheet_id: str, tab_name: str) -> list[list[object]]: ...

    def replace_rows(self, spreadsheet_id: str, tab_name: str, rows: list[list[object]]) -> None: ...


class GoogleSheetsProjection:
    """Projects canonical affiliate research rows to a Google Sheets workbook."""

    def __init__(
        self,
        repository: AffiliateResearchRepository,
        client: SheetsClient,
        spreadsheet_id: str,
    ):
        self._repository = repository
        self._client = client
        self._spreadsheet_id = spreadsheet_id

    @classmethod
    def from_environment(cls, repository: AffiliateResearchRepository) -> GoogleSheetsProjection:
        credentials_file = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE")
        spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
        if not credentials_file or not spreadsheet_id:
            raise RuntimeError(
                "Google Sheets projection requires GOOGLE_SHEETS_CREDENTIALS_FILE "
                "and GOOGLE_SHEETS_SPREADSHEET_ID."
            )
        return cls(repository, _GoogleSheetsClient.from_credentials_file(credentials_file), spreadsheet_id)

    def sync(self, owner_user_id: str, run_id: str) -> ProjectionResult:
        try:
            projection_rows = self._repository.projection_rows(owner_user_id, run_id)
            for tab_name, payload in self._tab_payloads(projection_rows).items():
                current_rows = self._client.read_rows(self._spreadsheet_id, tab_name)
                reconciled_rows = self._reconcile(current_rows, payload)
                self._client.replace_rows(self._spreadsheet_id, tab_name, reconciled_rows)
        except Exception as error:
            return ProjectionResult(ok=False, retryable=True, detail=str(error)[:1000])
        return ProjectionResult(ok=True, retryable=False, detail="synced")

    @classmethod
    def _tab_payloads(cls, projection_rows: dict[str, list[dict]]) -> dict[str, list[dict]]:
        products = projection_rows.get("products", [])
        references_by_product: dict[str, list[str]] = {}
        for reference in projection_rows.get("references", []):
            references_by_product.setdefault(str(reference["product_id"]), []).append(str(reference["id"]))

        ideas = []
        for idea in projection_rows.get("ideas", []):
            ideas.append({**idea, "reference_ids": references_by_product.get(str(idea["product_id"]), [])})

        events_by_package: dict[str, list[dict]] = {}
        for event in projection_rows.get("approval_events", []):
            events_by_package.setdefault(str(event["package_id"]), []).append(event)

        approval_queue = []
        for package in projection_rows.get("packages", []):
            events = events_by_package.get(str(package["id"]), [])
            approval_queue.append(
                {
                    "id": package["id"],
                    "product_id": package["product_id"],
                    "run_id": package["run_id"],
                    "revision": package["revision"],
                    "status": package["status"],
                    "updated_at": package["updated_at"],
                    "approval_events": events,
                }
            )

        return {
            "Products": products,
            "Shortlist": [
                product for product in products if product.get("eligibility_status") == "shortlisted"
            ],
            "Ideas": ideas,
            "Scripts": projection_rows.get("packages", []),
            "Approval Queue": approval_queue,
            "Runs & Errors": projection_rows.get("runs", []),
        }

    @classmethod
    def _reconcile(cls, current_rows: list[list[object]], payload: list[dict]) -> list[list[object]]:
        header = cls._header(current_rows, payload)
        desired_by_id = {str(row["id"]): row for row in payload}
        reconciled = []
        seen_ids = set()
        if current_rows and current_rows[0] and str(current_rows[0][0]) == "stable_id":
            for current_row in current_rows[1:]:
                stable_id = str(current_row[0]) if current_row else ""
                if stable_id in desired_by_id and stable_id not in seen_ids:
                    reconciled.append(
                        cls._encode_row(stable_id, desired_by_id[stable_id], header)
                    )
                    seen_ids.add(stable_id)
        for stable_id, row in desired_by_id.items():
            if stable_id not in seen_ids:
                reconciled.append(cls._encode_row(stable_id, row, header))
        return [header, *reconciled]

    @staticmethod
    def _header(current_rows: list[list[object]], payload: list[dict]) -> list[str]:
        existing_header = [str(value) for value in current_rows[0]] if current_rows else []
        fields = {key for row in payload for key in row if key != "id"}
        fields.update(column for column in existing_header if column != "stable_id")
        return ["stable_id", *sorted(fields)]

    @staticmethod
    def _encode_row(stable_id: str, row: dict, header: list[str]) -> list[object]:
        return [stable_id, *[GoogleSheetsProjection._cell_value(row.get(column)) for column in header[1:]]]

    @staticmethod
    def _cell_value(value: Any) -> object:
        if value is None or isinstance(value, (str, int, float, bool)):
            return "" if value is None else value
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


class DisabledSheetsProjection:
    def sync(self, owner_user_id: str, run_id: str) -> ProjectionResult:
        return ProjectionResult(ok=True, retryable=False, detail="disabled")


class FakeSheetsProjection:
    def __init__(self):
        self.calls = []

    def sync(self, owner_user_id: str, run_id: str) -> ProjectionResult:
        self.calls.append((owner_user_id, run_id))
        return ProjectionResult(ok=True, retryable=False, detail="fake")


class _GoogleSheetsClient:
    _SCOPE = "https://www.googleapis.com/auth/spreadsheets"

    def __init__(self, service: Any):
        self._service = service

    @classmethod
    def from_credentials_file(cls, credentials_file: str) -> _GoogleSheetsClient:
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError as error:
            raise RuntimeError(
                "Google Sheets support requires google-api-python-client and google-auth. "
                "Install the optional Google Sheets dependencies before configuring this projection."
            ) from error
        credentials = Credentials.from_service_account_file(credentials_file, scopes=[cls._SCOPE])
        return cls(build("sheets", "v4", credentials=credentials, cache_discovery=False))

    def read_rows(self, spreadsheet_id: str, tab_name: str) -> list[list[object]]:
        self._ensure_tab(spreadsheet_id, tab_name)
        response = self._service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"'{tab_name}'"
        ).execute()
        return response.get("values", [])

    def replace_rows(self, spreadsheet_id: str, tab_name: str, rows: list[list[object]]) -> None:
        self._ensure_tab(spreadsheet_id, tab_name)
        values = self._service.spreadsheets().values()
        values.clear(spreadsheetId=spreadsheet_id, range=f"'{tab_name}'").execute()
        values.update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()

    def _ensure_tab(self, spreadsheet_id: str, tab_name: str) -> None:
        spreadsheet = self._service.spreadsheets().get(
            spreadsheetId=spreadsheet_id, fields="sheets.properties"
        ).execute()
        titles = {sheet["properties"]["title"] for sheet in spreadsheet.get("sheets", [])}
        if tab_name not in titles:
            self._service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
            ).execute()
