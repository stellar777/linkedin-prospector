"""Supabase storage adapter — requires supabase-py package."""

from .base import StorageAdapter


class SupabaseAdapter(StorageAdapter):
    def __init__(self, url: str, key: str, table: str = "search_filters", leads_table: str = "leads"):
        try:
            from supabase import create_client
        except ImportError:
            raise ImportError("Install supabase: pip install supabase")
        self.client = create_client(url, key)
        self.table = table
        self.leads_table = leads_table

    def save_tracking(self, records: list[dict]) -> None:
        for record in records:
            self.client.table(self.table).upsert(record, on_conflict="niche,sub_niche").execute()
        print(f"  Tracking: {len(records)} records upserted to {self.table}")

    def save_leads(self, niche: str, sub_niche: str, leads: list[dict]) -> None:
        for lead in leads:
            lead["niche"] = niche
            lead["sub_niche"] = sub_niche
        batch_size = 500
        for i in range(0, len(leads), batch_size):
            batch = leads[i:i + batch_size]
            self.client.table(self.leads_table).insert(batch).execute()
        print(f"  Leads: {len(leads)} inserted into {self.leads_table}")

    def get_scraped(self) -> list[dict]:
        result = self.client.table(self.table).select("niche,sub_niche,status").in_("status", ["scraped", "scraping"]).execute()
        return result.data or []
