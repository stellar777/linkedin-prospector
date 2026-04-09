"""Storage adapter factory."""

from .base import StorageAdapter
from .csv_adapter import CSVAdapter


def load_adapter(config: dict) -> StorageAdapter:
    backend = config.get("storage", "csv")

    if backend == "csv":
        output_dir = config.get("csv_output_dir", "./output")
        return CSVAdapter(output_dir=output_dir)
    elif backend == "supabase":
        from .supabase_adapter import SupabaseAdapter
        return SupabaseAdapter(
            url=config["supabase_url"],
            key=config["supabase_key"],
            table=config.get("supabase_table", "search_filters"),
        )
    elif backend == "sheets":
        from .sheets_adapter import SheetsAdapter
        return SheetsAdapter(
            credentials_path=config["google_credentials_path"],
            spreadsheet_id=config["spreadsheet_id"],
        )
    else:
        raise ValueError(f"Unknown storage backend: {backend}. Use: csv, supabase, sheets")
