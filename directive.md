# LinkedIn Prospector — Directive

## What This Does

Takes a niche (e.g. "B2B SaaS") and a location, breaks it into targetable sub-niches, builds LinkedIn Sales Navigator URLs with proper filters, validates result counts via Vayne API, scrapes leads, and stores everything organized by niche/sub-niche.

For a whole client ICP at once (every vertical × region × persona), use the **Full TAM mode** below.

## The 0-5K Rule

The #1 mistake people make with Sales Nav scraping: building URLs that return 50,000+ results. LinkedIn caps what you can scrape, so you get the top slice of a massive, unfocused pool. The leads are generic and reply rates are garbage.

**Target 0-5,000 results per URL.** Ideally 500-3,000.

How to get there:
- **Headcount filters** narrow by company size (11-50 is different from 5,001-10,000)
- **Location** narrows geography (US is broad, California is tight, a metro area is very tight)
- **Keywords** should be specific to the sub-niche, not the parent niche
- **Seniority** filters which level of person you're targeting

When a URL returns > 5K, narrow it. When it returns < 100, broaden it.

### Auto-cascade narrowing

`prospector.py check` automatically narrows any sub-niche that returns more than `max_results_per_url` (default 5,000). The cascade runs in this order until the URL is in range or all axes are exhausted:

1. **Headcount split** — if headcount has multiple buckets, fan out into one URL per bucket
2. **Region split** — if `region: "US"`, fan out into one URL per US state (all 50 are mapped in `url_builder.py` → `REGION_IDS`)
3. **Posted on LinkedIn** — add the "Posted on LinkedIn" filter (id RPOL) to narrow to recently active posters. Already wired, no setup needed.
4. **Exhausted** — if the URL is still too broad after all splits, it's flagged `exhausted`. The only fix is tighter keywords (the cascade can't reason about language).

The cascade respects two guardrails:
- `URL_CHECK_SLEEP_SECONDS` (6.5s) — sleeps between Vayne calls to stay under the 10 req/min rate limit on `/api/url_checks`
- `MAX_URL_CHECKS_PER_RUN` (250) — hard cap on total checks per run

The "Posted on LinkedIn" filter is wired in `url_builder.py`. If LinkedIn ever changes the ID, `python3 url_builder.py extract-filter '<url with the filter on>'` prints what a given URL uses so you can update the `POSTED_ON_LINKEDIN_FILTER` constant.

## Full TAM mode (`prospector.py tam`)

The `check` flow above is niche-at-a-time. For a whole client ICP in one shot, use `tam`. It builds the entire URL universe from a `tam:` block in `config.yaml` (or `--input` JSON):

- **Account URLs** = every `vertical × region` (returns companies)
- **Lead URLs** = every `persona × vertical × region` (returns people)

Then it free count-checks each URL (paced, budget-capped) and auto-slices any over 5K with the posted-on-linkedin filter. Example config:

```yaml
tam:
  region_set: "us"          # us | north_america | global, or an explicit regions: list
  campaign_type: "tam"
  revenue: [5, 30]          # millions USD; comment out to skip
  headcount: ["11-50", "51-200", "201-500"]
  verticals:
    commercial_hvac:
      label: "Commercial HVAC"
      naics: ["238220"]
      keywords: '"commercial HVAC" OR "HVAC contractor" OR "mechanical contractor"'
  personas:                 # omit for account URLs only
    ops:
      functions: ["Operations"]
      seniority: ["Director", "VP", "CXO", "Owner"]
```

Run: `python3 prospector.py tam --config config.yaml` (add `--no-check` to build without sizing). Nested YAML needs PyYAML (`pip install pyyaml`), or pass the same spec as `--input` JSON. Rows save via the adapter with a `filter_config` (campaign_type, vertical, naics, region, revenue, headcount, persona) for downstream traceability.

**Keyword rules for verticals (learned the hard way):**
- Use BROAD anchor terms. LinkedIn matches company description text, not curated labels. `"CPG"` beats `"household cleaning brand"`.
- No `&` characters, they break URL encoding. Use `and`.
- Keep each keyword string under ~800 chars (Sales Nav URL length limit).
- Free count-check one URL per vertical before committing the whole matrix.

**Anti-patterns (do NOT do these):**
- Pre-slicing into revenue × headcount × region bands up front (URL bloat — let the count-check decide which URLs actually need slicing).
- Narrow synthesized keywords like `"first aid brand"` (returns 0 — LinkedIn matches natural vocabulary, not synthesized labels).
- Scraping all leads first, then filtering. Scrape accounts first, qualify, then find people on the survivors.

## How Filters Work

### Keywords (Boolean Logic)
- `"exact phrase"` — quotes for exact match
- `OR` — match either: `"HRIS" OR "HR software"`
- `AND` — match both: `"B2B SaaS" AND "HRIS"`
- Combine: `"B2B SaaS" AND ("HRIS" OR "HR software" OR "people operations")`

The `check` flow uses **anchor AND sub-niche** construction (anchor = the niche, always included; sub-niche = specific keywords per segment). The `tam` flow uses one keyword string per vertical.

### Headcount
`self, 1-10, 11-50, 51-200, 201-500, 501-1000, 1001-5000, 5001-10000, 10001+`. Default: 11-50, 51-200, 201-500.

### Seniority (lead search only)
`Entry, Senior, Experienced Manager, Director, VP, CXO, Owner`. Default: Director, VP, CXO, Owner.

### Regions
Countries: US, CA, MX, UK, AU, NZ, DE, FR, IN, SG, AE.
US states: all 50 (US-CA, US-TX, US-NY, ...).
Canadian provinces: CA-BC, CA-ON, CA-QC, CA-AB, CA-MB, CA-NS, CA-SK.
Convenience sets for the TAM `region_set`: `us` (50 states), `north_america` (US + provinces + MX), `global`. Full list in `url_builder.py` → `REGION_IDS`.

### Revenue + account vs lead search
`build_sales_nav_url(revenue_min_max=(5, 30))` adds an ANNUAL_REVENUE band (millions USD). `is_account_search=True` returns companies (`/sales/search/company`) instead of people; seniority/function filters are lead-only.

## Vayne API

Vayne scrapes LinkedIn Sales Navigator. You need an account and API token.

- **URL check is FREE** — always check before scraping
- **Scraping costs 1 credit per lead**
- Orders go: initialization → pending → segmenting → scraping → finished
- Results come as CSV (simple or advanced format)

Get your token: https://www.vayne.io → API Settings → Generate API Token. Set it in `config.yaml` under `vayne_api_token`.

## Storage Options

### CSV (Default)
Zero setup. Results go to `./output/` (a `tracking.csv` plus one CSV per sub-niche).

### Supabase
Set `storage: "supabase"` in config. Requires `pip install supabase`. Tracking upserts to the `search_filters` table on `(niche, sub_niche)`, so re-runs dedup automatically. Leads go to the `leads` table. Your table needs columns matching the tracking rows.

### Google Sheets
Set `storage: "sheets"` in config. Requires `pip install google-api-python-client google-auth`.

## Customization

- **Default filters:** `config.yaml` → `defaults`.
- **TAM spec:** `config.yaml` → `tam`.
- **Add regions:** `url_builder.py` → `REGION_IDS`. Find a region's ID by inspecting a Sales Nav URL that uses it.
- **Storage:** edit or add an adapter in `adapters/` (`save_tracking()`, `save_leads()`, `get_scraped()`).

## Tips
- Split by state when > 5K, or let the cascade / TAM auto-slice do it.
- People who post on LinkedIn recently are more likely to respond.
- Run `python3 vayne_client.py credits` before batch scraping.
- Start with CSV before wiring up Supabase or Sheets.
