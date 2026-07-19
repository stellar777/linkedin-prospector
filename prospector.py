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
import time
from datetime import datetime, timezone

from url_builder import (
    build_sales_nav_url, US_STATES, POSTED_ON_LINKEDIN_FILTER, REGION_SETS, TAM_US,
)
from vayne_client import VayneClient
from adapters import load_adapter


# Vayne /api/url_checks rate limit is 10 req/min. Sleep between checks to
# stay well under. Increase if you hit 429s.
URL_CHECK_SLEEP_SECONDS = 6.5

# Cap on how many URL-check API calls a single cmd_check run can make.
# Prevents a pathological cascade (broad niche + deep splits) from eating
# 30+ minutes of rate-limited calls.
MAX_URL_CHECKS_PER_RUN = 250


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


def _pick_next_axis(filters: dict) -> str | None:
    """Return the next axis to split on, or None if the cascade is exhausted.

    Order matches the manual workflow: headcount → region → posted filter.
    """
    if len(filters["headcount"]) > 1:
        return "headcount"
    if len(filters["regions"]) == 1 and filters["regions"][0] == "US":
        return "region"
    if not filters.get("posted", False) and POSTED_ON_LINKEDIN_FILTER is not None:
        return "posted"
    return None


def _split_axis(filters: dict, axis: str) -> list[dict]:
    """Return a list of new filter configs split along `axis`."""
    if axis == "headcount":
        return [{**filters, "headcount": [hc]} for hc in filters["headcount"]]
    if axis == "region":
        return [{**filters, "regions": [state]} for state in US_STATES]
    if axis == "posted":
        return [{**filters, "posted": True}]
    return [filters]


def _variant_label(filters: dict, seed_headcount: list, seed_regions: list) -> str:
    """Human-readable suffix for a narrowed variant (e.g. '11-50_US-CA_posted')."""
    parts = []
    if len(filters["headcount"]) == 1 and len(seed_headcount) > 1:
        parts.append(filters["headcount"][0])
    if filters["regions"] != seed_regions:
        parts.append(filters["regions"][0])
    if filters.get("posted"):
        parts.append("posted")
    return "_".join(parts)


def _check_and_narrow(
    filters: dict,
    vayne: VayneClient,
    max_results: int,
    min_results: int,
    budget: dict,
    depth: int = 0,
    max_depth: int = 3,
) -> list[dict]:
    """Recursively check a filter config, splitting when count > max_results.

    Returns a flat list of filter configs, each tagged with:
      status ∈ {good, too_narrow, exhausted, error, budget_exceeded}
      count  — Vayne count (or -1 on error)
      sales_nav_url — the built URL
    """
    if budget["checks_used"] >= budget["max_checks"]:
        return [{**filters, "count": -1, "sales_nav_url": None, "status": "budget_exceeded"}]

    try:
        url = build_sales_nav_url(
            keywords=filters["keywords"],
            regions=filters["regions"],
            seniority=filters.get("seniority"),
            headcount=filters["headcount"],
            posted_on_linkedin=filters.get("posted", False),
        )
    except ValueError as e:
        return [{**filters, "count": -1, "sales_nav_url": None,
                 "status": "error", "error": str(e)}]

    count = vayne.check_url(url)
    budget["checks_used"] += 1
    time.sleep(URL_CHECK_SLEEP_SECONDS)

    result = {**filters, "count": count, "sales_nav_url": url}

    if count < 0:
        result["status"] = "error"
        return [result]
    if count < min_results:
        result["status"] = "too_narrow"
        return [result]
    if count <= max_results:
        result["status"] = "good"
        return [result]

    # count > max_results — try to narrow
    if depth >= max_depth:
        result["status"] = "exhausted"
        return [result]

    next_axis = _pick_next_axis(filters)
    if next_axis is None:
        result["status"] = "exhausted"
        return [result]

    indent = "  " * (depth + 1)
    print(f"  {indent}{count:>7,} too broad → splitting by {next_axis}")

    results = []
    for branch in _split_axis(filters, next_axis):
        branch_results = _check_and_narrow(
            branch, vayne, max_results, min_results,
            budget, depth=depth + 1, max_depth=max_depth,
        )
        results.extend(branch_results)
    return results


def cmd_check(args):
    """Check counts for sub-niches with auto-cascade narrowing.

    For each sub-niche:
      1. Build a URL with the default filters and check the count
      2. If count > max_results, recursively narrow:
         headcount split → US state split → posted filter
      3. Return the flat list of in-range (or flagged) URLs
    """
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

    regions = [region] if isinstance(region, str) else region

    print(f"\nNiche:     {niche}")
    print(f"Region:    {', '.join(regions)}")
    print(f"Headcount: {', '.join(headcount)}")
    print(f"Seniority: {', '.join(seniority)}")
    print(f"Target:    {min_results:,}–{max_results:,} results per URL")
    if POSTED_ON_LINKEDIN_FILTER is None:
        print("Note:      POSTED_ON_LINKEDIN filter not wired — cascade stops at region split.")
        print("           Run: python3 url_builder.py extract-filter '<url>' to enable.")
    print()

    budget = {"checks_used": 0, "max_checks": MAX_URL_CHECKS_PER_RUN}
    all_results = []

    for sn in sub_niches:
        sub_niche_name = sn["sub_niche"]
        sub_keywords = sn["keywords"]

        key = f"{niche}_{sub_niche_name}"
        if key in already_scraped:
            print(f"  [skip] {sub_niche_name} — already scraped")
            continue

        combined_keywords = f'{anchor_keywords} AND ({sub_keywords})'

        print(f"  [{sub_niche_name}]")
        seed = {
            "niche": niche,
            "sub_niche": sub_niche_name,
            "keywords": combined_keywords,
            "regions": list(regions),
            "headcount": list(headcount),
            "seniority": list(seniority),
            "posted": False,
        }

        narrowed = _check_and_narrow(seed, vayne, max_results, min_results, budget)

        for r in narrowed:
            suffix = _variant_label(r, headcount, regions)
            effective_sub = f"{sub_niche_name}__{suffix}" if suffix else sub_niche_name
            effective_sub = effective_sub.replace("/", "_")

            all_results.append({
                "niche": niche,
                "sub_niche": effective_sub,
                "keywords": r["keywords"],
                "sales_nav_url": r.get("sales_nav_url"),
                "region": ",".join(r["regions"]),
                "headcount": ",".join(r["headcount"]),
                "posted_filter": r.get("posted", False),
                "expected_results": r["count"],
                "actual_scraped": 0,
                "status": r["status"],
            })

    # Summary table
    print(f"\n{'─' * 78}")
    print(f"{'Sub-niche':<52} {'Count':>10}  Status")
    print("─" * 78)
    for r in all_results:
        status = r["status"]
        count_str = f"{r['expected_results']:,}" if r['expected_results'] >= 0 else "—"
        label = r["sub_niche"][:50]
        print(f"  {label:<50} {count_str:>10}  {status}")

    good_count = sum(1 for r in all_results if r["status"] == "good")
    broad_count = sum(1 for r in all_results if r["status"] == "exhausted")
    narrow_count = sum(1 for r in all_results if r["status"] == "too_narrow")
    error_count = sum(1 for r in all_results if r["status"] in ("error", "budget_exceeded"))

    print(f"\n{good_count} good / {broad_count} still too broad / {narrow_count} too narrow / {error_count} errored")
    print(f"Vayne URL checks used: {budget['checks_used']}")
    print(f"\n{json.dumps(all_results, indent=2)}")


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


# ── Full TAM matrix (verticals × regions × revenue × headcount × personas) ──

def _load_tam_spec(config: dict, input_data: dict):
    """Resolve the TAM spec from --input JSON (takes priority) or config['tam']."""
    tam = (input_data or {}).get("tam") or config.get("tam", {}) or {}
    verticals = tam.get("verticals") or {}
    personas = tam.get("personas") or {}
    regions = tam.get("regions")
    if not regions:
        regions = REGION_SETS.get(str(tam.get("region_set", "us")).lower(), TAM_US)
    revenue = tam.get("revenue")
    revenue = (int(revenue[0]), int(revenue[1])) if isinstance(revenue, (list, tuple)) and len(revenue) == 2 else None
    headcount = tam.get("headcount") or config.get("defaults", {}).get(
        "headcount", ["11-50", "51-200", "201-500"])
    campaign_type = tam.get("campaign_type", "tam")
    return verticals, personas, regions, revenue, headcount, campaign_type


def _vert_bits(vcfg):
    if isinstance(vcfg, dict):
        return vcfg.get("keywords", ""), vcfg.get("naics", [])
    return str(vcfg), []


def _build_tam_rows(verticals, personas, regions, revenue, headcount, campaign_type):
    """Account URLs = vertical × region. Lead URLs = persona × vertical × region."""
    rows = []
    for vslug, vcfg in verticals.items():
        kw, naics = _vert_bits(vcfg)
        for region in regions:
            url = build_sales_nav_url(keywords=kw, regions=[region], headcount=headcount,
                                      revenue_min_max=revenue, is_account_search=True)
            rows.append({
                "niche": vslug, "sub_niche": f"tam__{region.lower()}",
                "platform": "sales_nav_account", "sales_nav_url": url,
                "keywords": kw, "region": region, "headcount": ",".join(headcount),
                "filter_config": {
                    "campaign_type": campaign_type, "vertical": vslug, "naics": naics,
                    "region": region,
                    "revenue_min_max_usd_millions": list(revenue) if revenue else None,
                    "headcount": headcount, "keywords": kw, "is_account_search": True,
                },
                "expected_results": 0, "actual_scraped": 0, "status": "planned",
            })
    for pslug, pcfg in personas.items():
        functions = pcfg.get("functions", []) if isinstance(pcfg, dict) else []
        seniority = pcfg.get("seniority", []) if isinstance(pcfg, dict) else []
        for vslug, vcfg in verticals.items():
            kw, naics = _vert_bits(vcfg)
            for region in regions:
                url = build_sales_nav_url(keywords=kw, regions=[region], seniority=seniority,
                                          functions=functions, headcount=headcount,
                                          is_account_search=False)
                rows.append({
                    "niche": vslug, "sub_niche": f"tam_lead__{pslug}__{region.lower()}",
                    "platform": "sales_nav", "sales_nav_url": url,
                    "keywords": kw, "region": region, "headcount": ",".join(headcount),
                    "filter_config": {
                        "campaign_type": campaign_type, "vertical": vslug, "naics": naics,
                        "region": region, "headcount": headcount, "keywords": kw,
                        "is_account_search": False, "persona": pslug,
                        "functions": functions, "seniority": seniority,
                    },
                    "expected_results": 0, "actual_scraped": 0, "status": "planned",
                })
    return rows


def _size_tam_rows(rows, vayne, budget, max_results=5000, min_results=100):
    """Free count-check each planned URL (paced); auto-slice >5K via posted-on-linkedin."""
    for r in rows:
        if budget["checks_used"] >= budget["max_checks"]:
            continue  # left as "planned" for a follow-up run
        count = vayne.check_url(r["sales_nav_url"])
        budget["checks_used"] += 1
        time.sleep(URL_CHECK_SLEEP_SECONDS)
        r["expected_results"] = count if count is not None else -1
        if count is None or count < 0:
            r["status"] = "error"
        elif count < min_results:
            r["status"] = "too_few"
        elif count <= max_results:
            r["status"] = "in_range"
        else:
            fc = r["filter_config"]
            rev = tuple(fc["revenue_min_max_usd_millions"]) if fc.get("revenue_min_max_usd_millions") else None
            sliced = build_sales_nav_url(
                keywords=fc["keywords"], regions=[fc["region"]],
                seniority=fc.get("seniority"), functions=fc.get("functions"),
                headcount=fc["headcount"], revenue_min_max=rev,
                is_account_search=fc["is_account_search"], posted_on_linkedin=True,
            )
            if budget["checks_used"] < budget["max_checks"]:
                c2 = vayne.check_url(sliced)
                budget["checks_used"] += 1
                time.sleep(URL_CHECK_SLEEP_SECONDS)
                r["sales_nav_url"] = sliced
                r["filter_config"]["posted_on_linkedin"] = True
                r["expected_results"] = c2 if c2 is not None else -1
                r["status"] = "in_range" if (c2 is not None and 0 <= c2 <= max_results) else "exceeds_5000"
            else:
                r["status"] = "exceeds_5000"
    return rows


def cmd_tam(args):
    """Build the full TAM URL universe: verticals × regions [× personas] → account + lead URLs.

    Reads the `tam:` block from config.yaml (or --input JSON). Free count-checks
    up to the per-run budget and auto-slices any URL over 5K. Saves via the adapter.
    """
    config = load_yaml_config(args.config)
    input_data = json.loads(args.input) if args.input else {}
    verticals, personas, regions, revenue, headcount, campaign_type = _load_tam_spec(config, input_data)
    if not verticals:
        print("No verticals found. Add a `tam.verticals` block to config.yaml "
              "(see config.example.yaml) or pass --input '{\"tam\": {...}}'.")
        return

    rows = _build_tam_rows(verticals, personas, regions, revenue, headcount, campaign_type)
    n_acct = sum(1 for r in rows if r["filter_config"]["is_account_search"])
    print(f"\nTAM universe: {len(verticals)} verticals × {len(regions)} regions × {len(personas)} personas")
    print(f"Built {len(rows)} URLs  ({n_acct} account, {len(rows) - n_acct} lead)")
    if revenue:
        print(f"Revenue band: ${revenue[0]}M-${revenue[1]}M   Headcount: {','.join(headcount)}")

    if not args.no_check:
        vayne = VayneClient(token=config.get("vayne_api_token"))
        budget = {"checks_used": 0, "max_checks": MAX_URL_CHECKS_PER_RUN}
        print(f"\nFree count-check (up to {MAX_URL_CHECKS_PER_RUN} URLs this run, "
              f"{URL_CHECK_SLEEP_SECONDS}s apart)...")
        _size_tam_rows(rows, vayne, budget)
        buckets = {}
        for r in rows:
            buckets[r["status"]] = buckets.get(r["status"], 0) + 1
        total = sum(r["expected_results"] for r in rows
                    if r["status"] == "in_range" and r["expected_results"] > 0)
        print("  " + "  ".join(f"{k}={v}" for k, v in sorted(buckets.items())))
        print(f"  addressable (in_range URLs): ~{total:,}")
        print(f"  Vayne checks used: {budget['checks_used']}")

    adapter = load_adapter(config)
    adapter.save_tracking(rows)
    print(f"\nSaved {len(rows)} URL rows via the {config.get('storage', 'csv')} adapter.")
    if any(r["status"] == "planned" for r in rows):
        print("Some URLs are still `planned` (hit the per-run check budget). "
              "Re-run `python3 prospector.py tam` to continue sizing them.")


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Prospector")
    parser.add_argument("command", choices=["check", "scrape", "status", "tam"])
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--input", default=None)
    parser.add_argument("--no-check", action="store_true",
                        help="tam: build + save URLs without the free count-check pass")
    args = parser.parse_args()

    if args.command == "check":
        cmd_check(args)
    elif args.command == "scrape":
        cmd_scrape(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "tam":
        cmd_tam(args)


if __name__ == "__main__":
    main()
