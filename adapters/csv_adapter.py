"""CSV storage adapter — zero setup, works immediately."""

import csv
import os
from .base import StorageAdapter

TRACKING_FIELDS = [
    "niche", "sub_niche", "keywords", "sales_nav_url", "region",
    "expected_results", "actual_scraped", "status", "scraped_at",
]


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
            writer.writerows(records)
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
