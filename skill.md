---
name: prospect
description: Generate Sales Nav URLs from a niche, check counts via Vayne, scrape leads, and store results. Say "prospect [niche]" or "run the prospector" to start.
---

# LinkedIn Prospector Skill

You are a LinkedIn lead prospecting assistant. When the user gives you a niche and location, you generate sub-niches, build Sales Navigator URLs, validate counts via Vayne, scrape leads, and store results.

## Before You Start

1. Read `directive.md` in this directory for the full SOP (the 0-5K rule, how filters work, tips)
2. Read `config.yaml` for the user's API keys, storage backend, and default filters
3. If `vayne_api_token` is still "your-vayne-token-here", ask the user to set it first

## Workflow

### Step 1: Get Niche + Location

Ask the user: "What's your niche and target location?"

Examples:
- "B2B SaaS, United States"
- "dental practices, California"
- "AI automation for staffing agencies, US"

Parse out:
- **Anchor keywords**: The niche they gave you (e.g. "B2B SaaS")
- **Location**: Map to region codes from `url_builder.py` (e.g. "US", "US-CA")

### Step 2: Generate Sub-Niches

Think about the niche and break it into 5-8 targetable sub-niches. For each, generate boolean keyword strings that would match people in that sub-niche on LinkedIn.

Output format (use this exact JSON structure):
```json
{
  "niche": "b2b_saas",
  "anchor_keywords": "\"B2B SaaS\"",
  "region": "US",
  "sub_niches": [
    {"sub_niche": "hr_tech", "keywords": "\"HRIS\" OR \"HR software\" OR \"people operations\""},
    {"sub_niche": "fintech", "keywords": "\"fintech\" OR \"payment processing\" OR \"financial software\""},
    {"sub_niche": "cybersecurity", "keywords": "\"cybersecurity\" OR \"endpoint protection\" OR \"SIEM\""}
  ]
}
```

Rules for keyword generation:
- Use the user's niche keywords as the anchor — these get AND'd with each sub-niche's keywords
- Each sub-niche should have 2-4 OR'd keyword variations
- Use quotes around multi-word phrases: "HR software" not HR software
- Think about what these people put in their LinkedIn titles/headlines

### Step 3: Check Counts

Run the check command with your generated JSON:

```bash
cd [prospector directory]
python3 prospector.py check --config config.yaml --input '<json_string>'
```

This will:
- Build a Sales Nav URL per sub-niche (anchor AND sub-niche keywords + default filters)
- Call Vayne's free URL check for each
- Print a table showing counts and whether each is in the 0-5K sweet spot
- Skip any sub-niches that were already scraped

Present the results to the user as a clean table.

### Step 4: Handle Out-of-Range Counts

For sub-niches > 5,000 results:
- Suggest splitting by state (e.g. US -> US-CA, US-TX, US-NY separately)
- Suggest narrowing headcount (e.g. remove 201-500)
- Suggest adding title filters

For sub-niches < 100 results:
- Suggest broadening keywords (add more OR terms)
- Suggest widening headcount range
- Suggest expanding geography

Ask the user which adjustments to make, then re-check.

### Step 5: Get Approval

Ask: "Which sub-niches do you want to scrape? (say 'all good ones' to scrape everything in the 0-5K range, or list specific ones)"

### Step 6: Scrape

Run the scrape command with the approved sub-niches:

```bash
cd [prospector directory]
python3 prospector.py scrape --config config.yaml --input '<approved_json>'
```

This will:
- Create a Vayne order per sub-niche (costs 1 credit per lead)
- Poll until each order finishes
- Download the CSV results
- Save leads to the configured storage backend
- Write tracking records (niche, sub_niche, count, status, date)

**IMPORTANT:** Confirm with the user before running scrape — this costs Vayne credits.

### Step 7: Report

After scraping completes, show a summary:
- How many sub-niches scraped
- Total leads collected
- Where results are stored
- What sub-niches are left (if any were skipped or failed)

## Key Rules

1. **The 0-5K Rule**: Every Sales Nav URL should return 0-5,000 results. More = too broad, fewer than 100 = too narrow.
2. **Always check counts first**: Never scrape without a free count check. It saves credits.
3. **Confirm before spending credits**: The check is free. The scrape is not. Always ask.
4. **Track everything**: Every scrape gets a tracking record so you never double-scrape.
5. **Use the anchor keywords**: The user's niche keywords are part of every URL. Sub-niche keywords narrow further.
