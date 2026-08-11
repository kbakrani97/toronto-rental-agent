"""
Scraper for Condos.ca building pages (e.g. Ten York).

Two-step process, mirroring rentals_ca.py:
1. The building page (e.g. condos.ca/toronto/ten-york-10-york-st) renders
   "For Rent" listings as plain text — regex-parsed to find which units
   (MLS numbers) are currently listed. This page does NOT expose furnished
   status.
2. Each unit's own detail page (e.g.
   condos.ca/toronto/ten-york-10-york-st/unit-3002-C13537662) embeds a rich
   structured JSON object (`window.__INITIAL_STATE__` → ...→ "data": {...})
   with ground-truth furnished ("Yes"/"No"/"Part"), a structured amenities
   list (e.g. [{"name": "Outdoor Pool"}, {"name": "Gym"}]), sqft, and more.
   Confirmed during build against a real Ten York listing — this is the
   same backing data condos.ca's own "Furnished" search filter uses.

A building rarely has more than a handful of active rentals, so the extra
per-unit fetch is cheap (Ten York currently has 1).
"""
from __future__ import annotations
import json
import re
from browser_fetch import fetch_html, fetch_html_text

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

FURNISHED_MAP = {"Yes": True, "No": False, "Part": False}  # "Part" (partly furnished) treated as not-furnished for the hard filter


def _fetch_unit_detail(unit_url: str) -> dict | None:
    """Fetch a unit's own listing page and extract its ground-truth
    structured data. Returns None (not a hard failure) if the page's
    structure doesn't match what we expect — callers fall back to
    building-level amenities in that case rather than crashing the source.
    """
    try:
        html = fetch_html(unit_url)
        idx = html.find('"asking_price"')
        if idx == -1:
            return None
        data_key_pos = html.rfind('"data":{', 0, idx)
        if data_key_pos == -1:
            return None
        start = data_key_pos + len('"data":')
        depth, end = 0, -1
        for i in range(start, len(html)):
            if html[i] == "{":
                depth += 1
            elif html[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end == -1:
            return None
        return json.loads(html[start:end])
    except Exception as e:
        print(f"[warn] Condos.ca unit detail fetch failed for {unit_url}: {e}")
        return None


def scrape(site_config: dict) -> list[dict]:
    path = site_config["path"]
    url = BASE_URL.format(path=path)
    text = fetch_html_text(url, main_selector="main")

    name_match = re.search(r"\n([^\n]+)\nBuilder: ", text)
    building_name = name_match.group(1) if name_match else path.split("/")[-1].replace("-", " ").title()

    amenities_match = AMENITIES_BLOCK_RE.search(text)
    building_amenities = []
    if amenities_match:
        building_amenities = [line.strip() for line in amenities_match.group(1).split("\n") if line.strip()]
    building_amenities_lower = [a.lower() for a in building_amenities]

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

        unit_url = f"{url}/unit-{m.group('unit')}-{m.group('mls')}"
        detail = _fetch_unit_detail(unit_url)

        if detail is not None:
            furnished = FURNISHED_MAP.get(detail.get("furnished"))
            # Per-unit amenities are agent-submitted (via MLS) and often
            # incomplete — confirmed on Ten York's own listing, which is
            # missing "Gym" despite the building's own (condos.ca-curated)
            # profile clearly listing it. Union both rather than trusting
            # the unit list exclusively, so a real amenity isn't missed
            # just because an agent under-tagged their listing.
            unit_amenities = [a.get("name", "") for a in (detail.get("amenities") or [])]
            amenities_lower = list({a.lower() for a in unit_amenities} | set(building_amenities_lower))
            sqft = detail.get("sqft") or m.group("sqft")
            available_date = detail.get("date_available")
        else:
            # Fall back to building-level amenities and unverified furnished
            # status if the per-unit fetch fails — degrade gracefully
            # rather than dropping the listing.
            furnished = None
            amenities_lower = building_amenities_lower
            sqft = m.group("sqft")
            available_date = None

        has_gym = any("gym" in a or "fitness" in a for a in amenities_lower)
        has_outdoor_pool = any("outdoor pool" in a for a in amenities_lower)
        has_indoor_pool = any("indoor pool" in a for a in amenities_lower)

        out.append({
            "site": f"Condos.ca ({building_name})",
            "building": building_name,
            "address": f"{m.group('unit')} - {m.group('street')}",
            "unit_or_layout": m.group("unit"),
            "beds": beds,
            "has_den": has_den,
            "baths": int(m.group("baths")),
            "sqft": sqft,
            "price": float(m.group("price").replace(",", "")),
            "available_date": available_date,
            "url": unit_url,
            "amenities_text": " ".join(amenities_lower),
            "furnished": furnished,
            "gym": has_gym,
            "outdoor_pool": has_outdoor_pool,
            "indoor_pool": has_indoor_pool,
            "free_rent_flag": False,
            "free_rent_detail": "",
        })
    return out
