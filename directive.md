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
