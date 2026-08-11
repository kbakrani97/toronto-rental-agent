"""
Scraper for Condos.ca building pages (e.g. Ten York).

Condos.ca doesn't expose a clean JSON API like Tricon or embed one like
Rentals.ca — both "For Sale" and "For Rent" listings are rendered as plain
text in the page's <main> element, so we render with headless Chromium and
parse the text with regex. Structure verified against the live Ten York
page during build:

    Amenities
    View available facilities at Ten York
    Concierge
    Guest Suites
    Gym
    Outdoor Pool
    Party Room
    Building Details
    ...
    For Rent
    There are currently 3 condos for rent at 10 York St, Toronto
    1/12
    $2,400
    3002 - 10 York Street
    1BD1BA0 Parking500-599 sqft
    MLS#: C13537662
    CENTURY 21 HERITAGE GROUP LTD.
    Compare
    33 days

Beds are written as "1BD" (one bedroom) or "1+1BD" (one bedroom + den) —
the "+1" is exactly a den, which is what we're filtering for.

CAVEAT: furnished status isn't shown on this summary page. It would need a
follow-up fetch of each unit's own listing page (cheap here since a
building rarely has more than a handful of rentals) — left as a TODO to
keep the first version's request count low; furnished is reported as
"unverified" for this source until that's added.
"""
import re
from browser_fetch import fetch_html_text

BASE_URL = "https://condos.ca/{path}"

AMENITIES_BLOCK_RE = re.compile(
    r"Amenities\nView available facilities at [^\n]+\n(.*?)\nBuilding Details",
    re.DOTALL,
)

RENT_SECTION_RE = re.compile(
    r"For Rent\nThere are currently \d+ condos? for rent[^\n]*\n(.*?)(?:\nExplore |\nSimilar Buildings|\nNearby Listings|\Z)",
    re.DOTALL,
)

LISTING_RE = re.compile(
    r"\$(?P<price>[\d,]+)\n"
    r"(?P<unit>[\w]+) - (?P<street>[^\n]+)\n"
    r"(?P<beds>\d(?:\+\d)?)BD(?P<baths>\d)BA\d+ Parking(?P<sqft>[\d,]+-[\d,]+) sqft\n"
    r"MLS#: (?P<mls>\S+)\n"
    r"(?P<brokerage>[^\n]+)\n"
    r"Compare\n"
)


def scrape(site_config: dict) -> list[dict]:
    path = site_config["path"]
    url = BASE_URL.format(path=path)
    text = fetch_html_text(url, main_selector="main")

    name_match = re.search(r"\n([^\n]+)\nBuilder: ", text)
    building_name = name_match.group(1) if name_match else path.split("/")[-1].replace("-", " ").title()

    amenities_match = AMENITIES_BLOCK_RE.search(text)
    amenities = []
    if amenities_match:
        amenities = [line.strip() for line in amenities_match.group(1).split("\n") if line.strip()]
    amenities_lower = [a.lower() for a in amenities]
    has_gym = any("gym" in a or "fitness" in a for a in amenities_lower)
    has_outdoor_pool = any("outdoor pool" in a for a in amenities_lower)
    has_indoor_pool = any("indoor pool" in a for a in amenities_lower)

    rent_section = RENT_SECTION_RE.search(text)
    out = []
    if not rent_section:
        return out

    for m in LISTING_RE.finditer(rent_section.group(1)):
        beds_raw = m.group("beds")  # "1" or "1+1"
        beds = int(beds_raw.split("+")[0])
        has_den = "+" in beds_raw

        if beds != 1:
            continue  # only want 1BR (with or without den)

        out.append({
            "site": f"Condos.ca ({building_name})",
            "building": building_name,
            "address": f"{m.group('unit')} - {m.group('street')}",
            "unit_or_layout": m.group("unit"),
            "beds": beds,
            "has_den": has_den,
            "baths": int(m.group("baths")),
            "sqft": m.group("sqft"),
            "price": float(m.group("price").replace(",", "")),
            "available_date": None,  # not shown on this view
            "url": f"{url}#{m.group('mls')}",
            "amenities_text": " ".join(amenities_lower),
            "furnished": None,  # unverified at this level, see module docstring
            "gym": has_gym,
            "outdoor_pool": has_outdoor_pool,
            "indoor_pool": has_indoor_pool,
            "free_rent_flag": False,
            "free_rent_detail": "",
        })
    return out
