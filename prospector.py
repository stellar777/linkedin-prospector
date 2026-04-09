#!/usr/bin/env python3
"""
LinkedIn Prospector — build Sales Nav URLs, check counts, scrape, store.

Called by Claude Code via the skill. Claude handles sub-niche generation
(thinking about the niche and producing sub-niches with keywords).
This script handles: URL construction, Vayne API, storage.

Usage:
    python3 prospector.py check --config config.yaml --input '<json>'
    python3 prospector.py scrape --config config.yaml --input '<json>'
    python3 prospector.py status --config config.yaml
"""

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone

from url_builder import build_sales_nav_url
from vayne_client import VayneClient
from adapters import load_adapter


def load_yaml_config(config_path: str) -> dict:
    """Load config — try PyYAML first, fall back to simple parser."""
    try:
        import yaml
        with open(config_path) as f:
            return yaml.safe_load(f)
    except ImportError:
        return _parse_simple_yaml(config_path)


def _parse_simple_yaml(config_path: str) -> dict:
    """Minimal YAML parser for config.yaml (no PyYAML dependency)."""
    config = {}
    current_key = None
    current_dict = None

    with open(config_path) as f:
        for line in f:
            raw = line.rstrip('\n')
            stripped = raw.lstrip()

            if not stripped or stripped.startswith("#"):
                continue

            indent = len(raw) - len(stripped)

            if indent == 0 and ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if not val:
                    current_key = key
                    current_dict = {}
                    config[key] = current_dict
                else:
                    current_key = None
                    current_dict = None
                    config[key] = val

            elif indent > 0 and current_key:
                if stripped.startswith("- "):
                    val = stripped[2:].strip().strip('"').strip("'")
                    # Find which sub-key this list belongs to by looking at config[current_key]
                    # The last non-list key added is the parent
                    if isinstance(current_dict, dict):
                        # Find the last key that was set
                        last_key = None
                        for k, v in current_dict.items():
                            if isinstance(v, list) or v == "__pending_list__":
                                last_key = k
                        if last_key and isinstance(current_dict.get(last_key), list):
                            current_dict[last_key].append(val)
                        elif last_key and current_dict.get(last_key) == "__pending_list__":
                            current_dict[last_key] = [val]

                elif ":" in stripped:
                    key, _, val = stripped.partition(":")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if isinstance(current_dict, dict):
                        if not val:
                            current_dict[key] = "__pending_list__"
                        else:
                            current_dict[key] = val

    # Clean up pending lists
    for k, v in config.items():
        if isinstance(v, dict):
            for sk, sv in list(v.items()):
                if sv == "__pending_list__":
                    v[sk] = []

    return config


def cmd_check(args):
    """Check counts for sub-niches."""
    config = load_yaml_config(args.config)
    defaults = config.get("defaults", {})

    input_data = json.loads(args.input) if args.input else json.load(sys.stdin)
    niche = input_data["niche"]
    anchor_keywords = input_data["anchor_keywords"]
    sub_niches = input_data["sub_niches"]
    region = input_data.get("region", defaults.get("region", "US"))

    headcount = input_data.get("headcount", defaults.get("headcount", ["11-50", "51-200", "201-500"]))
    seniority = input_data.get("seniority", defaults.get("seniority", ["Director", "VP", "CXO", "Owner"]))
    max_results = int(defaults.get("max_results_per_url", 5000))
    min_results = int(defaults.get("min_results_per_url", 100))

    adapter = load_adapter(config)
    already_scraped = {f"{r['niche']}_{r['sub_niche']}" for r in adapter.get_scraped()}

    vayne = VayneClient(token=config.get("vayne_api_token"))

    results = []
    regions = [region] if isinstance(region, str) else region

    print(f"\nNiche: {niche}")
    print(f"Anchor keywords: {anchor_keywords}")
    print(f"Region: {', '.join(regions)}")
    print(f"Headcount: {', '.join(headcount)}")
    print(f"Seniority: {', '.join(seniority)}")
    print(f"\n{'Sub-niche':<30} {'Count':>8}  Status")
    print("-" * 60)

    for sn in sub_niches:
        sub_niche_name = sn["sub_niche"]
        sub_keywords = sn["keywords"]

        key = f"{niche}_{sub_niche_name}"
        if key in already_scraped:
            print(f"  {sub_niche_name:<28} {'SKIP':>8}  already scraped")
            continue

        combined_keywords = f'{anchor_keywords} AND ({sub_keywords})'

        url = build_sales_nav_url(
            keywords=combined_keywords,
            regions=regions,
            seniority=seniority,
            headcount=headcount,
        )

        count = vayne.check_url(url)

        if count < 0:
            status_label = "ERROR"
        elif count > max_results:
            status_label = "too broad — split by state or tighten filters"
        elif count < min_results:
            status_label = "too narrow — broaden keywords"
        else:
            status_label = "good"

        print(f"  {sub_niche_name:<28} {count:>8,}  {status_label}")

        results.append({
            "niche": niche,
            "sub_niche": sub_niche_name,
            "keywords": combined_keywords,
            "sales_nav_url": url,
            "region": ",".join(regions),
            "expected_results": count,
            "actual_scraped": 0,
            "status": "counted",
        })

    print(f"\n{json.dumps(results, indent=2)}")


def cmd_scrape(args):
    """Scrape approved sub-niches."""
    config = load_yaml_config(args.config)
    vayne = VayneClient(token=config.get("vayne_api_token"))
    adapter = load_adapter(config)

    approved = json.loads(args.input) if args.input else json.load(sys.stdin)

    print(f"\nScraping {len(approved)} sub-niches...\n")

    for item in approved:
        niche = item["niche"]
        sub_niche = item["sub_niche"]
        url = item["sales_nav_url"]
        expected = item.get("expected_results", 0)

        print(f"{'=' * 60}")
        print(f"Sub-niche: {sub_niche} (expected: {expected:,})")

        order_name = f"{niche}_{sub_niche}"
        try:
            order = vayne.create_order(url, name=order_name)
        except RuntimeError as e:
            print(f"  ERROR creating order: {e}")
            item["status"] = "error"
            continue

        order_id = order["id"]
        print(f"  Order created: {order_id}")

        try:
            vayne.poll_until_done(order_id)
        except (RuntimeError, TimeoutError) as e:
            print(f"  ERROR polling: {e}")
            item["status"] = "error"
            continue

        print("  Downloading CSV...")
        csv_text = vayne.download_csv(order_id)

        reader = csv.DictReader(io.StringIO(csv_text))
        leads = list(reader)
        actual_count = len(leads)

        print(f"  Downloaded {actual_count} leads")

        adapter.save_leads(niche, sub_niche, leads)

        item["actual_scraped"] = actual_count
        item["status"] = "scraped"
        item["scraped_at"] = datetime.now(timezone.utc).isoformat()
        item["vayne_order_id"] = str(order_id)

    adapter.save_tracking(approved)

    scraped_count = sum(1 for a in approved if a["status"] == "scraped")
    print(f"\nDone. {scraped_count}/{len(approved)} scraped successfully.")


def cmd_status(args):
    """Show what's already been scraped."""
    config = load_yaml_config(args.config)
    adapter = load_adapter(config)
    scraped = adapter.get_scraped()

    if not scraped:
        print("No scrapes recorded yet.")
        return

    print(f"\n{'Niche':<20} {'Sub-niche':<25} {'Status':<10}")
    print("-" * 55)
    for r in scraped:
        print(f"  {r.get('niche', '-'):<18} {r.get('sub_niche', '-'):<23} {r.get('status', '-'):<10}")


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Prospector")
    parser.add_argument("command", choices=["check", "scrape", "status"])
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--input", default=None)
    args = parser.parse_args()

    if args.command == "check":
        cmd_check(args)
    elif args.command == "scrape":
        cmd_scrape(args)
    elif args.command == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
