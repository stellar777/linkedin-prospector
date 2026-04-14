# LinkedIn Prospector — Directive

## What This Does

Takes a niche (e.g. "B2B SaaS") and a location, breaks it into targetable sub-niches, builds LinkedIn Sales Navigator URLs with proper filters, validates result counts via Vayne API, scrapes leads, and stores everything organized by niche/sub-niche.

## The 0-5K Rule

The #1 mistake people make with Sales Nav scraping: building URLs that return 50,000+ results. LinkedIn caps what you can scrape, so you get the top slice of a massive, unfocused pool. The leads are generic and reply rates are garbage.

**Target 0-5,000 results per URL.** Ideally 500-3,000.

How to get there:
- **Headcount filters** narrow by company size (11-50 is different from 5,001-10,000)
- **Location** narrows geography (US is broad, California is tight, San Francisco Bay Area is very tight)
- **Keywords** should be specific to the sub-niche, not the parent niche
- **Seniority** filters which level of person you're targeting

When a URL returns > 5K, narrow it. When it returns < 100, broaden it.

### Auto-cascade narrowing

`prospector.py check` automatically narrows any sub-niche that returns more than
`max_results_per_url` (default 5,000). The cascade runs in this order until the
URL is in range or all axes are exhausted:

1. **Headcount split** — if headcount has multiple buckets (e.g. `11-50`, `51-200`,
   `201-500`), fan out into one URL per bucket
2. **Region split** — if `region: "US"`, fan out into one URL per US state in
   `US_STATES` (16 top states by population — add more in `url_builder.py`)
3. **Posted on LinkedIn** — add the "Posted on LinkedIn" filter to narrow to
   recently active posters (must wire `POSTED_ON_LINKEDIN_FILTER` in `url_builder.py`
   first — see below)
4. **Exhausted** — if the URL is still too broad after all splits, it's flagged
   `exhausted`. The only fix is tighter keywords (the cascade can't reason about
   language).

A single sub-niche can produce many URLs. A broad B2B SaaS sub-niche might
fan out to 3 headcounts × 16 states = 48 URLs. That's fine — the check is free.
The run will use roughly one Vayne URL check per leaf + each intermediate node.

The cascade respects two guardrails:
- `URL_CHECK_SLEEP_SECONDS` (6.5s) — sleeps between Vayne calls to stay under
  the 10 req/min rate limit on `/api/url_checks`
- `MAX_URL_CHECKS_PER_RUN` (250) — hard cap on total checks per run

### Wiring the "Posted on LinkedIn" filter

This filter isn't hardcoded because LinkedIn uses opaque filter IDs that can
change. To enable it:

1. Open Sales Navigator, toggle on the "Posted on LinkedIn" filter
2. Copy the URL
3. Run: `python3 url_builder.py extract-filter '<url>'`
4. Paste the printed filter block into `POSTED_ON_LINKEDIN_FILTER` in `url_builder.py`

Once wired, the cascade will automatically use it as the final narrowing step.

## How Filters Work

### Keywords (Boolean Logic)
LinkedIn supports boolean operators in the keyword field:
- `"exact phrase"` — quotes for exact match
- `OR` — match either term: `"HRIS" OR "HR software"`
- `AND` — match both: `"B2B SaaS" AND "HRIS"`
- Combine: `"B2B SaaS" AND ("HRIS" OR "HR software" OR "people operations")`

The prospector uses **anchor AND sub-niche** construction:
- Anchor = the user's niche keywords (always included)
- Sub-niche = specific keywords for each segment

### Headcount
| Code | Range |
|------|-------|
| self | Self-employed |
| 1-10 | 1-10 employees |
| 11-50 | 11-50 |
| 51-200 | 51-200 |
| 201-500 | 201-500 |
| 501-1000 | 501-1,000 |
| 1001-5000 | 1,001-5,000 |
| 5001-10000 | 5,001-10,000 |
| 10001+ | 10,001+ |

Default: 11-50, 51-200, 201-500. Edit in `config.yaml`.

### Seniority
| Level | Who |
|-------|-----|
| Entry | Junior roles |
| Senior | Senior ICs |
| Experienced Manager | Mid-management |
| Director | Department heads |
| VP | Vice Presidents |
| CXO | C-suite |
| Owner | Founders, Partners |

Default: Director, VP, CXO, Owner. Edit in `config.yaml`.

### Regions
Countries: US, CA, UK, AU, DE, FR, IN, SG, AE, NZ
US States: US-CA, US-TX, US-NY, US-FL, US-IL, etc.
US Metros: US-SF, US-NYC, US-LA, US-CHI, US-DFW, etc.

Full list in `url_builder.py` → `REGION_IDS`.

## Vayne API

Vayne scrapes LinkedIn Sales Navigator. You need an account and API token.

**Key facts:**
- **URL check is FREE** — always check before scraping
- **Scraping costs 1 credit per lead**
- Orders go through: initialization → pending → segmenting → scraping → finished
- Results come as CSV (simple or advanced format)
- Rate limit: 5 req/s burst, 60 req/min sustained

Get your token: https://www.vayne.io → API Settings → Generate API Token
Set it in `config.yaml` under `vayne_api_token`.

## Storage Options

### CSV (Default)
Zero setup. Results go to `./output/`:
```
output/
├── tracking.csv
├── b2b_saas/
│   ├── hr_tech.csv
│   ├── fintech.csv
│   └── cybersecurity.csv
└── dental_practices/
    ├── cosmetic.csv
    └── orthodontics.csv
```

### Supabase
Set `storage: "supabase"` in config. Requires `pip install supabase`.
Tracking goes to `search_filters` table, leads to `leads` table.

### Google Sheets
Set `storage: "sheets"` in config. Requires `pip install google-api-python-client google-auth`.
Creates a "Tracking" tab and a tab per sub-niche.

## Customization

**Change default filters:** Edit `config.yaml` → `defaults` section.

**Add new regions:** Edit `url_builder.py` → `REGION_IDS` dict. Find LinkedIn's region ID by inspecting a Sales Nav URL that uses that filter.

**Change the storage schema:** Edit the relevant adapter in `adapters/`. The interface is simple: `save_tracking()`, `save_leads()`, `get_scraped()`.

**Add a new storage backend:** Create a new adapter in `adapters/` that extends `StorageAdapter`, then add it to `adapters/__init__.py`.

## Tips

- **Split by state when > 5K**: If "US" returns 8,000 results, try US-CA, US-TX, US-NY separately.
- **Title filters for precision**: Add title filters to target specific roles beyond seniority level.
- **Recent posters**: People who post on LinkedIn recently are more likely to respond.
- **Check credits before batch scraping**: Run `python3 vayne_client.py credits` to see what you have.
- **Start with CSV**: Get comfortable with the flow before wiring up Supabase or Sheets.
