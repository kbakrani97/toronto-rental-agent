"""
Scraper for Condos.ca's general "for rent" search, scoped to broad areas
(e.g. Downtown, West End) rather than one specific building.

Unlike condos_ca.py (which scrapes a single named building's page and
needs a follow-up per-unit fetch for furnished/amenities), this source's
page embeds a full structured JSON array directly —
`window.__INITIAL_STATE__` → `"searchAlogliaList": [...]` — one object per
listing, already including furnished ("Yes"/"No"/"Part"), a plain-string
amenities list, sqft, price, and neighbourhood_name/sublocality_name.
Confirmed during build against the live Downtown search page. No per-unit
follow-up fetch needed here.

CAVEAT: this fetches only the first page (~54 listings, newest-first) of
a broad area — e.g. "Downtown" covers many neighbourhoods beyond King
West/Fort York/Waterfront, and a specific building's only active listing
can be pushed past page 1 by newer listings elsewhere in the same broad
area (confirmed: Ten York's own listing didn't appear in Downtown's page
1, which is why it stays a dedicated build in condos_ca.py). Area
filtering (config.ALLOWED_AREAS) happens downstream in main.py — this
scraper just tags each listing with its real neighbourhood name so that
filter can do its job; it does not pre-filter by area itself.
"""
from __future__ import annotations
import json
from browser_fetch import fetch_html

BASE_URL = "https://condos.ca/{path}"

FURNISHED_MAP = {"Yes": True, "No": False, "Part": False}  # "Part" (partly furnished) treated as not-furnished for the hard filter
GYM_KEYWORDS = ["gym", "fitness"]
POOL_OUTDOOR_KEYWORDS = ["outdoor pool"]
POOL_INDOOR_KEYWORDS = ["indoor pool"]


def _extract_listings(html: str) -> list[dict]:
    key = '"searchAlogliaList":'
    idx = html.find(key)
    if idx == -1:
        raise ValueError("Could not find searchAlogliaList — condos.ca may have changed its page structure")
    start = idx + len(key)
    while html[start] in " \t\n":
        start += 1
    depth, end = 0, -1
    for i in range(start, len(html)):
        if html[i] == "[":
            depth += 1
        elif html[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("Unbalanced brackets while extracting searchAlogliaList")
    return json.loads(html[start:end])


def scrape(site_config: dict) -> list[dict]:
    path = site_config["path"]
    url = BASE_URL.format(path=path)
    html = fetch_html(url)
    listings = _extract_listings(html)

    out = []
    for l in listings:
        beds = l.get("bedrooms")
        if beds not in (1, 2):
            continue

        furnished = FURNISHED_MAP.get(l.get("furnished"))
        amenities = l.get("amenities") or []  # list of plain strings, e.g. ["Gym", "Outdoor Pool", ...]
        amenities_lower = [str(a).lower() for a in amenities]
        amenities_text = " ".join(amenities_lower)
        has_gym = any(k in amenities_text for k in GYM_KEYWORDS)
        has_outdoor_pool = any(k in amenities_text for k in POOL_OUTDOOR_KEYWORDS)
        has_indoor_pool = any(k in amenities_text for k in POOL_INDOOR_KEYWORDS)

        neighbourhood = l.get("neighbourhood_name") or ""
        sublocality = l.get("sublocality_name") or ""
        street = l.get("title") or ""

        lat = lng = None
        try:
            lat = float(l["latitude"]) if l.get("latitude") else None
            lng = float(l["longitude"]) if l.get("longitude") else None
        except (TypeError, ValueError):
            pass

        listing_url = l.get("url")
        full_url = f"https://condos.ca/{listing_url}" if listing_url else url

        out.append({
            "site": f"Condos.ca (area: {path})",
            "building": street,
            # neighbourhood/sublocality folded into address so the
            # downstream keyword area filter (config.ALLOWED_AREAS) can
            # actually match on it — e.g. "King West", "Fort York",
            # "The Waterfront", "Liberty Village" all show up here.
            "address": f"{street}, {neighbourhood}, {sublocality}".strip(", "),
            "unit_or_layout": l.get("unit_number") or l.get("unit_name") or str(l.get("id", "")),
            "beds": beds,
            "has_den": bool(l.get("bedrooms_plus")),
            "baths": l.get("bathrooms"),
            "sqft": l.get("sqft") or l.get("sqft_min"),
            "price": l.get("asking_price"),
            "available_date": l.get("date_available"),
            "url": full_url,
            "amenities_text": amenities_text,
            "furnished": furnished,
            "gym": has_gym,
            "outdoor_pool": has_outdoor_pool,
            "indoor_pool": has_indoor_pool,
            "free_rent_flag": False,
            "free_rent_detail": "",
            "raw_lat": lat,
            "raw_lng": lng,
            # Same policy as the other Condos.ca/Rentals.ca sources: this
            # market is frequently unfurnished, so show labeled rather than
            # hard-exclude. Set via config's allow_unfurnished per-site flag,
            # applied in main.py — not hardcoded here.
        })
    return out
