"""Google Sheets storage adapter — requires google-api-python-client."""

from .base import StorageAdapter

TRACKING_FIELDS = [
    "niche", "sub_niche", "keywords", "sales_nav_url", "region",
    "expected_results", "actual_scraped", "status", "scraped_at",
]


class SheetsAdapter(StorageAdapter):
    def __init__(self, credentials_path: str, spreadsheet_id: str):
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError("Install: pip install google-api-python-client google-auth")
        creds = Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        self.service = build("sheets", "v4", credentials=creds)
        self.spreadsheet_id = spreadsheet_id

    def _append_rows(self, sheet_name: str, rows: list[list]) -> None:
        body = {"values": rows}
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

    def _ensure_sheet(self, sheet_name: str) -> None:
        meta = self.service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
        existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if sheet_name not in existing:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
            ).execute()

    def save_tracking(self, records: list[dict]) -> None:
        self._ensure_sheet("Tracking")
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range="Tracking!A1:A1"
        ).execute()
        if not result.get("values"):
            self._append_rows("Tracking", [TRACKING_FIELDS])
        rows = [[r.get(f, "") for f in TRACKING_FIELDS] for r in records]
        self._append_rows("Tracking", rows)
        print(f"  Tracking: {len(records)} rows appended to Tracking sheet")

    def save_leads(self, niche: str, sub_niche: str, leads: list[dict]) -> None:
        sheet_name = f"{niche}_{sub_niche}"[:100]
        self._ensure_sheet(sheet_name)
        if not leads:
            return
        fields = list(leads[0].keys())
        rows = [fields] + [[lead.get(f, "") for f in fields] for lead in leads]
        self._append_rows(sheet_name, rows)
        print(f"  Leads: {len(leads)} rows written to {sheet_name} sheet")

    def get_scraped(self) -> list[dict]:
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id, range="Tracking!A:I"
            ).execute()
            rows = result.get("values", [])
            if len(rows) < 2:
                return []
            headers = rows[0]
            return [
                dict(zip(headers, row))
                for row in rows[1:]
                if len(row) > 7 and row[7] in ("scraped", "scraping")
            ]
        except Exception:
            return []
