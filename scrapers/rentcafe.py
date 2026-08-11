"""
Scraper for RentCafe-hosted buildings (currently: FourFifty The Well).

RentCafe sits behind a Cloudflare bot-challenge (confirmed during build —
see browser_fetch.py's docstring). A plain headless Chromium page load
passed the challenge when tested, but this is the most fragile source in
the pipeline: Cloudflare configs change, and a scraping pattern that works
today can start failing without warning. main.py treats this source as
"fragile" (per config.py) — a failure here is reported in the digest email
as a warning, not allowed to crash the whole run.

Page renders floor plans as plain text blocks, e.g.:

    The Bond VII
    1 Bed / 1 Bath / 530 Sqft
    $2,675
    Floor plan details
    Unit	Base rent	Availability
    2904	$2,675
    Oct 10

    View
    Apply now

Multiple units can appear under one floor plan name.
"""
import re
from browser_fetch import fetch_html_text

FP_RE = re.compile(
    r"(?P<name>[^\n]+)\n"
    # Beds AND baths both pluralize independently ("1 Bed / 1 Bath" vs
    # "2 Beds / 2 Baths") — confirmed missing "s?" on Bath silently dropped
    # every 2-bed (2-bath) floor plan from matching at all.
    r"(?:Studio|(?P<beds>\d+) Bed)s?(?P<den>\s*\+\s*Den)? / (?P<baths>[\d.]+) Baths? / (?P<sqft>[\d,]+) Sqft\n"
    r"[^\n]*\n"
    r"Floor plan details\n"
    r"Unit\tBase rent\tAvailability\t\n"
    r"(?P<block>.*?)(?=\n[^\n]+\n(?:Studio|\d+ Beds?) ?/ |\Z)",
    re.DOTALL,
)
UNIT_RE = re.compile(
    r"(?P<unit>[\w-]+)\t\$(?P<price>[\d,]+)\t\n(?P<avail>[^\n\t]+)\n\t\nView\nApply now"
)


def scrape(site_config: dict) -> list[dict]:
    path = site_config["path"]
    url = f"https://www.rentcafe.com/apartments/{path}/default.aspx"
    text = fetch_html_text(url, main_selector="body", timeout_ms=45000)

    name_match = re.search(r"\n([^\n]+)\n[^\n]+, Toronto, ON\n", text)
    building_name = name_match.group(1) if name_match else path.split("/")[-1].replace("-", " ").title()

    text_lower = text.lower()
    has_gym = "gym" in text_lower or "fitness" in text_lower
    has_outdoor_pool = "outdoor pool" in text_lower
    has_indoor_pool = "indoor pool" in text_lower

    out = []
    for fp in FP_RE.finditer(text):
        if fp.group("beds") not in ("1", "2"):
            continue
        has_den = bool(fp.group("den"))

        for um in UNIT_RE.finditer(fp.group("block")):
            out.append({
                "site": f"RentCafe ({building_name})",
                "building": building_name,
                "address": f"{um.group('unit')} - {building_name}",
                "unit_or_layout": f"{fp.group('name')} ({um.group('unit')})",
                "beds": int(fp.group("beds")),
                "has_den": has_den,
                "baths": float(fp.group("baths")),
                "sqft": fp.group("sqft"),
                "price": float(um.group("price").replace(",", "")),
                "available_date": um.group("avail"),
                "url": url,
                "amenities_text": text_lower,
                "furnished": None,  # not indicated on this page; unverified
                "gym": has_gym,
                "outdoor_pool": has_outdoor_pool,
                "indoor_pool": has_indoor_pool,
                # Deliberately not scanning `text_lower` for a bare "free" —
                # that matched unrelated phrases like "smoke-free community"
                # on every listing. main.py's annotate_soft_signals() already
                # checks amenities_text against config.FREE_RENT_KEYWORDS
                # (specific phrases like "month free"), so this is left False
                # here and let that shared, more precise check own it.
                "free_rent_flag": False,
                "free_rent_detail": "",
            })
    return out
