#!/usr/bin/env python3
"""
Sales Navigator URL Builder — constructs encoded Sales Nav search URLs.

Standalone module. No external dependencies (Vayne calls live in vayne_client.py).

Usage:
    from url_builder import build_sales_nav_url, decode_sales_nav_url

    # Lead search (default)
    url = build_sales_nav_url(
        keywords='"B2B SaaS" AND ("HRIS" OR "HR software")',
        regions=["US"],
        seniority=["Director", "VP", "CXO", "Owner"],
        headcount=["11-50", "51-200", "201-500"],
    )

    # Account search (returns companies, not people) with a revenue band
    url = build_sales_nav_url(
        keywords='"commercial HVAC"',
        regions=["US-TX"],
        headcount=["51-200"],
        revenue_min_max=(5, 30),      # millions USD
        is_account_search=True,
    )

CLI:
    python3 url_builder.py parse "<sales_nav_url>"
    python3 url_builder.py build --keywords '"data center"' --regions US-CA,US-TX --headcount 11-50,51-200
    python3 url_builder.py build --keywords '"HVAC"' --regions US-TX --revenue 5-30 --account
"""

import re
import sys
from urllib.parse import unquote

# ── LinkedIn Sales Nav ID Mappings ──────────────────────────────────────
# These are LinkedIn's public geo/filter URNs. No secrets, no account data.

REGION_IDS = {
    # Countries
    "US": ("103644278", "United States"),
    "CA": ("101174742", "Canada"),
    "MX": ("103323778", "Mexico"),
    "UK": ("101165590", "United Kingdom"),
    "AU": ("101452733", "Australia"),
    "NZ": ("105490917", "New Zealand"),
    "DE": ("101282230", "Germany"),
    "FR": ("105015875", "France"),
    "IN": ("102713980", "India"),
    "SG": ("102454443", "Singapore"),
    "AE": ("104305776", "United Arab Emirates"),
    # Canadian Provinces
    "CA-BC": ("102044150", "British Columbia, Canada"),
    "CA-ON": ("100506914", "Ontario, Canada"),
    "CA-QC": ("100875116", "Quebec, Canada"),
    "CA-AB": ("104819541", "Alberta, Canada"),
    "CA-MB": ("106393891", "Manitoba, Canada"),
    "CA-NS": ("103658330", "Nova Scotia, Canada"),
    "CA-SK": ("100977905", "Saskatchewan, Canada"),
    # All 50 US States
    "US-AL": ("106197902", "Alabama, United States"),
    "US-AK": ("103231649", "Alaska, United States"),
    "US-AZ": ("104937023", "Arizona, United States"),
    "US-AR": ("102043820", "Arkansas, United States"),
    "US-CA": ("102095887", "California, United States"),
    "US-CO": ("105763343", "Colorado, United States"),
    "US-CT": ("102047884", "Connecticut, United States"),
    "US-DE": ("103192344", "Delaware, United States"),
    "US-FL": ("101318387", "Florida, United States"),
    "US-GA": ("103588929", "Georgia, United States"),
    "US-HI": ("106805931", "Hawaii, United States"),
    "US-ID": ("105269353", "Idaho, United States"),
    "US-IL": ("101768227", "Illinois, United States"),
    "US-IN": ("104468137", "Indiana, United States"),
    "US-IA": ("105995230", "Iowa, United States"),
    "US-KS": ("104726492", "Kansas, United States"),
    "US-KY": ("105759904", "Kentucky, United States"),
    "US-LA": ("106187514", "Louisiana, United States"),
    "US-ME": ("105751900", "Maine, United States"),
    "US-MD": ("104256044", "Maryland, United States"),
    "US-MA": ("103350119", "Massachusetts, United States"),
    "US-MI": ("101490689", "Michigan, United States"),
    "US-MN": ("103084673", "Minnesota, United States"),
    "US-MS": ("102568623", "Mississippi, United States"),
    "US-MO": ("106142749", "Missouri, United States"),
    "US-MT": ("103993828", "Montana, United States"),
    "US-NE": ("104612160", "Nebraska, United States"),
    "US-NV": ("106233675", "Nevada, United States"),
    "US-NH": ("101470634", "New Hampshire, United States"),
    "US-NJ": ("101651951", "New Jersey, United States"),
    "US-NM": ("103048791", "New Mexico, United States"),
    "US-NY": ("105080838", "New York, United States"),
    "US-NC": ("101935664", "North Carolina, United States"),
    "US-ND": ("100529486", "North Dakota, United States"),
    "US-OH": ("104977017", "Ohio, United States"),
    "US-OK": ("106069316", "Oklahoma, United States"),
    "US-OR": ("103736294", "Oregon, United States"),
    "US-PA": ("105191464", "Pennsylvania, United States"),
    "US-RI": ("103254187", "Rhode Island, United States"),
    "US-SC": ("105042118", "South Carolina, United States"),
    "US-SD": ("104577907", "South Dakota, United States"),
    "US-TN": ("101615840", "Tennessee, United States"),
    "US-TX": ("102748797", "Texas, United States"),
    "US-UT": ("106389834", "Utah, United States"),
    "US-VT": ("104934434", "Vermont, United States"),
    "US-VA": ("105763813", "Virginia, United States"),
    "US-WA": ("105668973", "Washington, United States"),
    "US-WV": ("100894051", "West Virginia, United States"),
    "US-WI": ("103924150", "Wisconsin, United States"),
    "US-WY": ("106096878", "Wyoming, United States"),
}

# Convenience region sets — pass to the TAM builder via config (region_set).
US_STATES = [c for c in REGION_IDS if c.startswith("US-")]          # all 50
CA_PROVINCES = [c for c in REGION_IDS if c.startswith("CA-")]        # 7
TAM_US = US_STATES
TAM_NORTH_AMERICA = US_STATES + CA_PROVINCES + ["MX"]
TAM_GLOBAL = TAM_NORTH_AMERICA + ["UK", "AU", "NZ", "DE", "FR", "IN", "SG", "AE"]
REGION_SETS = {"us": TAM_US, "north_america": TAM_NORTH_AMERICA, "global": TAM_GLOBAL}

# POSTED_ON_LINKEDIN filter (id=RPOL) restricts to people who posted recently —
# a strong "active account" signal, and the last-resort narrower for URLs over
# Vayne's 5K cap (typically cuts 70-90%). Wired below, no manual extract needed.
POSTED_ON_LINKEDIN_FILTER = ("RPOL", "Posted on LinkedIn")

SENIORITY_IDS = {
    "Training":            ("100", "Training"),
    "Entry":               ("110", "Entry"),
    "Senior":              ("120", "Senior"),
    "Strategic":           ("130", "Strategic"),
    "Entry Manager":       ("200", "Entry-level Manager"),
    "Experienced Manager": ("210", "Experienced Manager"),
    "Director":            ("220", "Director"),
    "VP":                  ("300", "Vice President"),
    "CXO":                 ("310", "CXO"),
    "Owner":               ("320", "Owner / Partner"),
}

HEADCOUNT_IDS = {
    "self":       ("A", "Self-employed"),
    "1-10":       ("B", "1-10"),
    "11-50":      ("C", "11-50"),
    "51-200":     ("D", "51-200"),
    "201-500":    ("E", "201-500"),
    "501-1000":   ("F", "501-1000"),
    "1001-5000":  ("G", "1001-5000"),
    "5001-10000": ("H", "5001-10000"),
    "10001+":     ("I", "10001+"),
}

FUNCTION_IDS = {
    "Accounting": ("1", "Accounting"),
    "Administrative": ("2", "Administrative"),
    "Arts and Design": ("3", "Arts and Design"),
    "Business Development": ("4", "Business Development"),
    "Community and Social Services": ("5", "Community and Social Services"),
    "Consulting": ("6", "Consulting"),
    "Education": ("7", "Education"),
    "Engineering": ("8", "Engineering"),
    "Entrepreneurship": ("9", "Entrepreneurship"),
    "Finance": ("10", "Finance"),
    "Healthcare Services": ("11", "Healthcare Services"),
    "Human Resources": ("12", "Human Resources"),
    "Information Technology": ("13", "Information Technology"),
    "Legal": ("14", "Legal"),
    "Marketing": ("15", "Marketing"),
    "Media and Communication": ("16", "Media and Communication"),
    "Military and Protective Services": ("17", "Military and Protective Services"),
    "Operations": ("18", "Operations"),
    "Product Management": ("19", "Product Management"),
    "Program and Project Management": ("20", "Program and Project Management"),
    "Purchasing": ("21", "Purchasing"),
    "Quality Assurance": ("22", "Quality Assurance"),
    "Real Estate": ("23", "Real Estate"),
    "Research": ("24", "Research"),
    "Sales": ("25", "Sales"),
    "Customer Success and Support": ("26", "Customer Success and Support"),
}


# ── URL Parser ──────────────────────────────────────────────────────────

def decode_sales_nav_url(url: str) -> dict:
    """Parse a Sales Nav URL into structured components."""
    decoded = unquote(unquote(url))
    result = {"keywords": None, "regions": [], "seniority": [], "headcount": [],
              "functions": [], "industries": [], "titles": [], "raw_filters": []}

    kw_match = re.search(r'keywords:(.+?)(?:\)|$)', decoded)
    if kw_match:
        result["keywords"] = re.sub(r'\)$', '', kw_match.group(1).strip()).strip()

    filter_pattern = r'\(type:(\w+),values:List\((.*?)\)\)'
    for match in re.finditer(filter_pattern, decoded):
        ftype = match.group(1)
        value_pattern = r'\(id:([^,]+),text:([^,]+),selectionType:(\w+)\)'
        values = [{"id": vm.group(1), "text": vm.group(2).strip(), "selectionType": vm.group(3)}
                  for vm in re.finditer(value_pattern, match.group(2))]
        result["raw_filters"].append({"type": ftype, "values": values})
        key = {"REGION": "regions", "SENIORITY_LEVEL": "seniority",
               "COMPANY_HEADCOUNT": "headcount", "FUNCTION": "functions",
               "CURRENT_TITLE": "titles", "INDUSTRY": "industries"}.get(ftype)
        if key:
            result[key] = values
    return result


# ── URL Builder ─────────────────────────────────────────────────────────

def build_filter(filter_type: str, values: list) -> str:
    vals = ",".join(f"(id:{vid},text:{vtext},selectionType:INCLUDED)" for vid, vtext in values)
    return f"(type:{filter_type},values:List({vals}))"


def encode_sales_nav_query(raw_query: str) -> str:
    """Encode a raw Sales Nav query to LinkedIn's exact URL format.

    Structure chars: colon -> %3A, comma -> %2C.
    Text chars: space -> %2520, quote -> %2522, slash -> %252F. Parens stay literal.
    """
    out = []
    for c in raw_query:
        out.append({":": "%3A", ",": "%2C", " ": "%2520", '"': "%2522", "/": "%252F"}.get(c, c))
    return "".join(out)


def build_sales_nav_url(
    keywords: str,
    regions: list | None = None,
    seniority: list | None = None,
    headcount: list | None = None,
    functions: list | None = None,
    titles: list | None = None,
    industries: list | None = None,
    revenue_min_max: tuple | None = None,
    is_account_search: bool = False,
    posted_on_linkedin: bool = False,
) -> str:
    """Build a complete Sales Nav search URL.

    is_account_search=True  -> /sales/search/company (returns accounts)
    is_account_search=False -> /sales/search/people  (returns leads, default)
    seniority/functions/titles are lead-only and ignored on account searches.
    revenue_min_max is (min, max) in millions USD (LinkedIn ANNUAL_REVENUE range).
    posted_on_linkedin=True adds the RPOL narrower for over-5K URLs.
    """
    filters = []

    if regions:
        vals = [REGION_IDS[r] for r in regions if r in REGION_IDS]
        for r in regions:
            if r not in REGION_IDS:
                print(f"  Warning: unknown region code {r} (skipping)")
        if vals:
            filters.append(build_filter("REGION", vals))

    if headcount:
        vals = [HEADCOUNT_IDS[h] for h in headcount if h in HEADCOUNT_IDS]
        if vals:
            filters.append(build_filter("COMPANY_HEADCOUNT", vals))

    if not is_account_search and seniority:
        vals = [SENIORITY_IDS[s] for s in seniority if s in SENIORITY_IDS]
        if vals:
            filters.append(build_filter("SENIORITY_LEVEL", vals))

    if not is_account_search and functions:
        vals = [FUNCTION_IDS[f] for f in functions if f in FUNCTION_IDS]
        if vals:
            filters.append(build_filter("FUNCTION", vals))

    if not is_account_search and titles:
        filters.append(build_filter("CURRENT_TITLE", [(t, t) for t in titles]))

    if industries:
        filters.append(build_filter("INDUSTRY", industries))

    if revenue_min_max:
        rev_min, rev_max = revenue_min_max
        filters.append(
            f"(type:ANNUAL_REVENUE,rangeValue:(min:{rev_min},max:{rev_max}),selectedSubFilter:USD)"
        )

    if posted_on_linkedin:
        filters.append(build_filter("POSTED_ON_LINKEDIN", [POSTED_ON_LINKEDIN_FILTER]))

    filters_str = ",".join(filters)
    raw_query = f"(spellCorrectionEnabled:true,filters:List({filters_str}),keywords:{keywords})"
    encoded = encode_sales_nav_query(raw_query)
    path = "/sales/search/company" if is_account_search else "/sales/search/people"
    return f"https://www.linkedin.com{path}?query={encoded}&viewAllFilters=true"


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]

    if cmd == "parse":
        if len(sys.argv) < 3:
            print("Usage: python3 url_builder.py parse '<url>'"); sys.exit(1)
        parsed = decode_sales_nav_url(sys.argv[2])
        print(f"\nKeywords: {parsed['keywords']}")
        for label, key in [("Regions", "regions"), ("Seniority", "seniority"),
                           ("Headcount", "headcount"), ("Functions", "functions"),
                           ("Titles", "titles")]:
            if parsed[key]:
                vals = ", ".join(v.get("text", "") if isinstance(v, dict) else str(v)
                                 for v in parsed[key])
                print(f"{label}: {vals}")

    elif cmd == "build":
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("_cmd")
        p.add_argument("--keywords", required=True)
        p.add_argument("--regions", default="US")
        p.add_argument("--seniority", default="Director,VP,CXO,Owner")
        p.add_argument("--headcount", default="11-50,51-200,201-500")
        p.add_argument("--revenue", default=None, help="min-max in millions, e.g. 5-30")
        p.add_argument("--account", action="store_true", help="account search instead of leads")
        a = p.parse_args()
        rev = tuple(int(x) for x in a.revenue.split("-")) if a.revenue else None
        url = build_sales_nav_url(
            keywords=a.keywords, regions=a.regions.split(","),
            seniority=a.seniority.split(","), headcount=a.headcount.split(","),
            revenue_min_max=rev, is_account_search=a.account,
        )
        print(f"\n{url}\n")

    elif cmd == "extract-filter":
        # Legacy helper: POSTED_ON_LINKEDIN is already wired (id=RPOL). This just
        # confirms the filter block a given URL uses, if LinkedIn ever changes it.
        if len(sys.argv) < 3:
            print("POSTED_ON_LINKEDIN is wired as", POSTED_ON_LINKEDIN_FILTER); sys.exit(0)
        parsed = decode_sales_nav_url(sys.argv[2])
        pol = [f for f in parsed["raw_filters"] if f["type"] == "POSTED_ON_LINKEDIN"]
        print(pol or "No POSTED_ON_LINKEDIN filter found in that URL.")

    else:
        print(f"Unknown command: {cmd}"); print(__doc__); sys.exit(1)


if __name__ == "__main__":
    main()
