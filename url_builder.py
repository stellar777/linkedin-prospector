#!/usr/bin/env python3
"""
Sales Navigator URL Builder — constructs encoded Sales Nav search URLs.

Standalone module. No external dependencies.

Usage:
    from url_builder import build_sales_nav_url, decode_sales_nav_url

    url = build_sales_nav_url(
        keywords='"B2B SaaS" AND ("HRIS" OR "HR software")',
        regions=["US"],
        seniority=["Director", "VP", "CXO", "Owner"],
        headcount=["11-50", "51-200", "201-500"],
    )
"""

import re
from urllib.parse import unquote


REGION_IDS = {
    "US": ("103644278", "United States"),
    "AU": ("101452733", "Australia"),
    "CA": ("101174742", "Canada"),
    "UK": ("101165590", "United Kingdom"),
    "DE": ("101282230", "Germany"),
    "FR": ("105015875", "France"),
    "IN": ("102713980", "India"),
    "SG": ("102454443", "Singapore"),
    "AE": ("104305776", "United Arab Emirates"),
    "NZ": ("105490917", "New Zealand"),
    "US-CA": ("102095887", "California, United States"),
    "US-TX": ("102748797", "Texas, United States"),
    "US-NY": ("105080838", "New York, United States"),
    "US-FL": ("101318387", "Florida, United States"),
    "US-IL": ("101768227", "Illinois, United States"),
    "US-PA": ("105191464", "Pennsylvania, United States"),
    "US-OH": ("104977017", "Ohio, United States"),
    "US-GA": ("103588929", "Georgia, United States"),
    "US-NC": ("101935664", "North Carolina, United States"),
    "US-MI": ("101490689", "Michigan, United States"),
    "US-NJ": ("101651951", "New Jersey, United States"),
    "US-VA": ("105763813", "Virginia, United States"),
    "US-WA": ("105668973", "Washington, United States"),
    "US-AZ": ("104937023", "Arizona, United States"),
    "US-MA": ("103350119", "Massachusetts, United States"),
    "US-CO": ("105763343", "Colorado, United States"),
    "US-SF": ("90000084", "San Francisco Bay Area"),
    "US-NYC": ("90000070", "New York City Metropolitan Area"),
    "US-LA": ("90000049", "Los Angeles Metropolitan Area"),
    "US-CHI": ("90000015", "Chicago Metropolitan Area"),
    "US-DFW": ("90000018", "Dallas-Fort Worth Metroplex"),
    "US-HOU": ("90000042", "Greater Houston"),
    "US-ATL": ("90000004", "Greater Atlanta Area"),
    "US-BOS": ("90000009", "Greater Boston"),
    "US-SEA": ("90000081", "Greater Seattle Area"),
    "US-DEN": ("90000019", "Greater Denver Area"),
    "US-PHX": ("90000074", "Greater Phoenix Area"),
}

SENIORITY_IDS = {
    "Entry":               ("110", "Entry"),
    "Senior":              ("120", "Senior"),
    "Experienced Manager": ("210", "Experienced Manager"),
    "Director":            ("220", "Director"),
    "VP":                  ("300", "Vice President"),
    "CXO":                 ("310", "CXO"),
    "Owner":               ("320", "Owner / Partner"),
}

HEADCOUNT_IDS = {
    "self":      ("A", "Self-employed"),
    "1-10":      ("B", "1-10"),
    "11-50":     ("C", "11-50"),
    "51-200":    ("D", "51-200"),
    "201-500":   ("E", "201-500"),
    "501-1000":  ("F", "501-1000"),
    "1001-5000": ("G", "1001-5000"),
    "5001-10000":("H", "5001-10000"),
    "10001+":    ("I", "10001+"),
}

FUNCTION_IDS = {
    "Accounting":                    ("1", "Accounting"),
    "Administrative":                ("2", "Administrative"),
    "Arts and Design":               ("3", "Arts and Design"),
    "Business Development":          ("4", "Business Development"),
    "Community and Social Services": ("5", "Community and Social Services"),
    "Consulting":                    ("6", "Consulting"),
    "Education":                     ("7", "Education"),
    "Engineering":                   ("8", "Engineering"),
    "Entrepreneurship":              ("9", "Entrepreneurship"),
    "Finance":                       ("10", "Finance"),
    "Healthcare Services":           ("11", "Healthcare Services"),
    "Human Resources":               ("12", "Human Resources"),
    "Information Technology":        ("13", "Information Technology"),
    "Legal":                         ("14", "Legal"),
    "Marketing":                     ("15", "Marketing"),
    "Media and Communication":       ("16", "Media and Communication"),
    "Military and Protective Services": ("17", "Military and Protective Services"),
    "Operations":                    ("18", "Operations"),
    "Product Management":            ("19", "Product Management"),
    "Program and Project Management":("20", "Program and Project Management"),
    "Purchasing":                    ("21", "Purchasing"),
    "Quality Assurance":             ("22", "Quality Assurance"),
    "Real Estate":                   ("23", "Real Estate"),
    "Research":                      ("24", "Research"),
    "Sales":                         ("25", "Sales"),
    "Customer Success and Support":  ("26", "Customer Success and Support"),
}


def encode_sales_nav_query(raw_query: str) -> str:
    result = []
    for c in raw_query:
        if c == ':':
            result.append("%3A")
        elif c == ',':
            result.append("%2C")
        elif c == ' ':
            result.append("%2520")
        elif c == '"':
            result.append("%2522")
        elif c == '/':
            result.append("%252F")
        else:
            result.append(c)
    return "".join(result)


def build_filter(filter_type: str, values: list[tuple[str, str]]) -> str:
    vals = ",".join(
        f"(id:{vid},text:{vtext},selectionType:INCLUDED)"
        for vid, vtext in values
    )
    return f"(type:{filter_type},values:List({vals}))"


def build_sales_nav_url(
    keywords: str,
    regions: list[str] = None,
    seniority: list[str] = None,
    headcount: list[str] = None,
    functions: list[str] = None,
    titles: list[str] = None,
) -> str:
    filters = []

    if regions:
        vals = []
        for r in regions:
            if r in REGION_IDS:
                rid, rtext = REGION_IDS[r]
                vals.append((rid, rtext))
        if vals:
            filters.append(build_filter("REGION", vals))

    if seniority:
        vals = []
        for s in seniority:
            if s in SENIORITY_IDS:
                sid, stext = SENIORITY_IDS[s]
                vals.append((sid, stext))
        if vals:
            filters.append(build_filter("SENIORITY_LEVEL", vals))

    if headcount:
        vals = []
        for h in headcount:
            if h in HEADCOUNT_IDS:
                hid, htext = HEADCOUNT_IDS[h]
                vals.append((hid, htext))
        if vals:
            filters.append(build_filter("COMPANY_HEADCOUNT", vals))

    if functions:
        vals = []
        for f in functions:
            if f in FUNCTION_IDS:
                fid, ftext = FUNCTION_IDS[f]
                vals.append((fid, ftext))
        if vals:
            filters.append(build_filter("FUNCTION", vals))

    if titles:
        vals = [(t, t) for t in titles]
        filters.append(build_filter("CURRENT_TITLE", vals))

    filters_str = ",".join(filters)
    raw_query = f"(spellCorrectionEnabled:true,filters:List({filters_str}),keywords:{keywords})"
    encoded_query = encode_sales_nav_query(raw_query)

    return f"https://www.linkedin.com/sales/search/people?query={encoded_query}&viewAllFilters=true"


def decode_sales_nav_url(url: str) -> dict:
    decoded = unquote(unquote(url))
    result = {"keywords": None, "regions": [], "seniority": [], "headcount": [], "functions": [], "titles": []}

    kw_match = re.search(r'keywords:(.+?)(?:\)|$)', decoded)
    if kw_match:
        kw = kw_match.group(1).strip()
        kw = re.sub(r'\)$', '', kw).strip()
        result["keywords"] = kw

    filter_pattern = r'\(type:(\w+),values:List\((.*?)\)\)'
    for match in re.finditer(filter_pattern, decoded):
        filter_type = match.group(1)
        values_str = match.group(2)
        value_pattern = r'\(id:([^,]+),text:([^,]+),selectionType:(\w+)\)'
        values = []
        for vm in re.finditer(value_pattern, values_str):
            values.append({"id": vm.group(1), "text": vm.group(2).strip()})

        mapping = {
            "REGION": "regions", "SENIORITY_LEVEL": "seniority",
            "COMPANY_HEADCOUNT": "headcount", "FUNCTION": "functions",
            "CURRENT_TITLE": "titles",
        }
        if filter_type in mapping:
            result[mapping[filter_type]] = values

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 url_builder.py build --keywords '\"B2B SaaS\"' --regions US --headcount 11-50,51-200")
        print("  python3 url_builder.py decode '<sales_nav_url>'")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "build":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("_cmd")
        parser.add_argument("--keywords", required=True)
        parser.add_argument("--regions", default="US")
        parser.add_argument("--seniority", default="Director,VP,CXO,Owner")
        parser.add_argument("--headcount", default="11-50,51-200,201-500")
        parser.add_argument("--functions", default=None)
        parser.add_argument("--titles", default=None)
        args = parser.parse_args()
        url = build_sales_nav_url(
            keywords=args.keywords,
            regions=args.regions.split(","),
            seniority=args.seniority.split(","),
            headcount=args.headcount.split(","),
            functions=args.functions.split(",") if args.functions else None,
            titles=args.titles.split(",") if args.titles else None,
        )
        print(f"\nGenerated URL:\n{url}\n")
    elif cmd == "decode":
        if len(sys.argv) < 3:
            print("Usage: python3 url_builder.py decode '<url>'")
            sys.exit(1)
        import json
        parsed = decode_sales_nav_url(sys.argv[2])
        print(json.dumps(parsed, indent=2))
