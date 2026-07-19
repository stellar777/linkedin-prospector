"""CSV storage adapter — zero setup, works immediately."""

import csv
import json
import os
from .base import StorageAdapter

# Stable tracking schema. `platform` and `filter_config` carry TAM metadata
# (account vs lead, campaign_type, vertical, naics, region, persona) so nothing
# is silently dropped when storage is CSV. Nested values are JSON-encoded.
TRACKING_FIELDS = [
    "niche", "sub_niche", "platform", "keywords", "sales_nav_url", "region",
    "headcount", "expected_results", "actual_scraped", "status", "scraped_at",
    "filter_config",
]


def _flatten(record: dict) -> dict:
    """JSON-encode nested dict/list values so they survive a CSV cell."""
    return {k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
            for k, v in record.items()}


class CSVAdapter(StorageAdapter):
    def __init__(self, output_dir: str = "./output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def _tracking_path(self) -> str:
        return os.path.join(self.output_dir, "tracking.csv")

    def save_tracking(self, records: list[dict]) -> None:
        path = self._tracking_path()
        file_exists = os.path.exists(path)
        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRACKING_FIELDS, extrasaction="ignore")
            if not file_exists:
                writer.writeheader()
            writer.writerows(_flatten(r) for r in records)
        print(f"  Tracking: {len(records)} records written to {path}")

    def save_leads(self, niche: str, sub_niche: str, leads: list[dict]) -> None:
        niche_dir = os.path.join(self.output_dir, niche)
        os.makedirs(niche_dir, exist_ok=True)
        path = os.path.join(niche_dir, f"{sub_niche}.csv")
        if not leads:
            print(f"  No leads to save for {sub_niche}")
            return
        fieldnames = list(leads[0].keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(leads)
        print(f"  Leads: {len(leads)} saved to {path}")

    def get_scraped(self) -> list[dict]:
        path = self._tracking_path()
        if not os.path.exists(path):
            return []
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            return [row for row in reader if row.get("status") in ("scraped", "scraping")]
