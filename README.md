# LinkedIn Prospector

A Claude Code skill that turns a niche into scraped, organized LinkedIn leads.

Give it a niche and location. It breaks the niche into sub-niches, builds Sales Navigator URLs with smart filters, checks result counts (free), scrapes via Vayne API, and stores everything tracked by niche/sub-niche/status.

## The 0-5K Rule

Most people build Sales Nav URLs with 50K+ results and scrape the top 2,500. The leads are unfocused and reply rates are garbage.

**This tool targets 0-5,000 results per URL.** It does this by:
- Breaking broad niches into specific sub-niches
- Using boolean keyword construction (anchor AND sub-niche)
- Applying headcount, seniority, and location filters
- Checking counts before scraping (free) and flagging URLs outside the sweet spot

## Quick Start

1. **Drop this folder into your Claude Code project**

2. **Copy the config template and add your Vayne API token:**
   ```bash
   cp config.example.yaml config.yaml
   # Edit config.yaml — add your Vayne token from https://www.vayne.io
   ```

3. **Run it:**
   ```
   > prospect B2B SaaS, United States
   ```

   Claude will:
   - Generate 5-8 sub-niches (HR tech, fintech, cybersecurity, dev tools...)
   - Build a Sales Nav URL per sub-niche
   - Check counts via Vayne (free)
   - Show you a table of results
   - Ask which to scrape
   - Scrape, store, and track everything

## What You Get

```
output/
├── tracking.csv                    # Everything you've scraped
├── b2b_saas/
│   ├── hr_tech.csv                 # 2,340 leads
│   ├── cybersecurity.csv           # 1,890 leads
│   └── dev_tools.csv               # 450 leads
└── dental_practices/
    ├── cosmetic.csv
    └── orthodontics.csv
```

## Storage Options

**CSV** (default) — zero setup, results go to `./output/`

**Supabase** — set `storage: "supabase"` in config. Requires `pip install supabase`.

**Google Sheets** — set `storage: "sheets"` in config. Requires `pip install google-api-python-client google-auth`.

## How It Works

```
"B2B SaaS, United States"
         |
         v
Generate sub-niches (Claude thinks)
  - HR tech, fintech, cybersecurity, dev tools...
         |
         v
Build keyword strings per sub-niche
  "B2B SaaS" AND ("HRIS" OR "HR software")
  "B2B SaaS" AND ("cybersecurity" OR "SIEM")
         |
         v
Construct Sales Nav URLs (headcount + seniority + region)
         |
         v
Free Vayne count check per URL
  HR Tech: 2,340 -> good
  Fintech: 8,120 -> too broad, split by state
         |
         v
Scrape approved sub-niches (1 credit/lead)
         |
         v
Store leads + tracking records
```

## Customization

Everything is editable:

- **Default filters** — edit `config.yaml` (headcount, seniority, region)
- **How it works** — edit `directive.md` (the SOP Claude follows)
- **Regions** — edit `url_builder.py` to add new LinkedIn region IDs
- **Storage** — edit adapters in `adapters/` or add your own

## File Structure

```
linkedin-prospector/
├── skill.md                # Claude Code skill (entry point)
├── directive.md            # SOP — the 0-5K rule, filters, tips
├── config.example.yaml     # Config template (copy to config.yaml)
├── prospector.py           # Main orchestrator
├── url_builder.py          # Sales Nav URL construction
├── vayne_client.py         # Vayne API client
└── adapters/
    ├── __init__.py         # Adapter factory
    ├── base.py             # Abstract interface
    ├── csv_adapter.py      # CSV storage (default)
    ├── supabase_adapter.py # Supabase storage
    └── sheets_adapter.py   # Google Sheets storage
```

## Requirements

- Python 3.10+
- [Claude Code](https://claude.ai/code)
- [Vayne API](https://www.vayne.io) account + token
- LinkedIn Sales Navigator subscription (Vayne uses your session)

## CLI Usage (without Claude Code)

The scripts also work standalone:

```bash
# Build a URL
python3 url_builder.py build --keywords '"data center construction"' --regions US --headcount 11-50,51-200

# Check credits
python3 vayne_client.py credits

# Check a URL count (free)
python3 vayne_client.py check '<sales_nav_url>'

# Check counts for sub-niches
python3 prospector.py check --config config.yaml --input '<json>'

# Scrape approved sub-niches
python3 prospector.py scrape --config config.yaml --input '<json>'

# See what you've scraped
python3 prospector.py status --config config.yaml
```

## License

MIT
