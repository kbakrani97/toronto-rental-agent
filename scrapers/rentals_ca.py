"""
Scraper for Rentals.ca neighbourhood/search pages.

Two-step process:
1. The neighbourhood search page (e.g. rentals.ca/toronto/liberty-village)
   embeds a GraphQL-style summary JSON (`App.store.search = {response:{...}}`)
   with one entry per BUILDING — used only to find which buildings have a
   1-bedroom in range and to skip room-shares.
2. For each such building, its own page (e.g. rentals.ca/toronto/svnty)
   embeds a second JSON (`App.store.listing = {...}`) with a real per-UNIT
   breakdown: exact rent, sqft, furnished flag, den flag, availability date,
   and a stable unit id. That's what actually gets returned/emailed — the
   step-1 summary was previously (incorrectly) used as a single fake
   "building-level" listing with no sqft; this fixes that.

Both pages are fetched via headless Chromium (browser_fetch) since
rentals.ca blocks plain HTTP requests — confirmed during build.
"""
import json
from browser_fetch import BrowserSession

BASE_URL = "https://rentals.ca/{path}"

GYM_KEYWORDS = ["gym", "fitness"]
POOL_OUTDOOR_KEYWORDS = ["outdoor pool"]
POOL_INDOOR_KEYWORDS = ["indoor pool"]
FREE_RENT_AMENITY_KEYWORDS = ["free rent", "month free", "rent free"]


def _extract_embedded_json(html: str, var_name: str) -> dict:
    """Extract a `App.store.<var_name> = {...}` (or `= {response: {...}}`)
    JSON blob from inline <script> HTML using brace-balancing (regex alone
    can't reliably match nested braces here).
    """
    marker = f"App.store.{var_name}"
    idx = html.find(marker)
    if idx == -1:
        raise ValueError(f"Could not find App.store.{var_name} — rentals.ca may have changed its page structure")

    # Search-page payloads wrap the JSON in `response: {...}` inside the
    # outer object; listing-page payloads assign the JSON object directly.
    # Look for a `response:` key within a short window after the marker —
    # if present, start there; otherwise start at the `=`.
    response_idx = html.find("response:", idx, idx + 200)
    if response_idx != -1:
        start = html.find(":", response_idx) + 1
    else:
        start = html.find("=", idx) + 1
    while html[start] in " \t\n":
        start += 1

    depth = 0
    end = -1
    for i in range(start, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError(f"Unbalanced braces while extracting App.store.{var_name}")

    return json.loads(html[start:end])


def _candidate_building_paths(session: BrowserSession, search_path: str) -> list[dict]:
    """Step 1: find buildings on the neighbourhood search page whose beds
    range overlaps 1-2BR and which aren't room-shares. Returns lightweight
    dicts with just enough to fetch each building's own page next.
    """
    html = session.fetch_html(BASE_URL.format(path=search_path))
    payload = _extract_embedded_json(html, "search")
    edges = payload["data"]["edges"]

    out = []
    for edge in edges:
        node = edge["node"]
        if not (node.get("listingType") or "").startswith("residential:apartment"):
            continue
        beds_range = node.get("bedsRange") or [None, None]
        lo, hi = beds_range[0], (beds_range[1] or beds_range[0])
        if lo is None or hi < 1 or lo > 2:  # no overlap with 1-2BR
            continue
        out.append({"path": node.get("path"), "name": node.get("rentalListingName")})
    return out


def _amenity_names(listing_json: dict) -> list[str]:
    amenities = listing_json.get("amenities") or listing_json.get("raw_amenities") or []
    return [a.get("name", "").lower() for a in amenities if isinstance(a, dict)]


def scrape(site_config: dict) -> list[dict]:
    search_path = site_config["path"]

    # One Chromium instance reused for the search page AND every building
    # detail page, paced with a small delay between requests — a fresh
    # browser per request was slower and, we suspect, part of what was
    # tripping rentals.ca's rate limiter (repeated 429s observed in
    # production even though each request looked like a fresh session).
    with BrowserSession(request_delay_sec=2.0) as session:
        buildings = _candidate_building_paths(session, search_path)

        out = []
        for b in buildings:
            if not b["path"]:
                continue
            url = f"https://rentals.ca/{b['path']}"
            try:
                html = session.fetch_html(url)
                listing = _extract_embedded_json(html, "listing")
            except Exception as e:
                # One building's detail page failing shouldn't drop the rest —
                # log and move on. main.py's per-site error reporting is at the
                # search-page level, not per-building, so this is a print, not
                # a raised error.
                print(f"[warn] Rentals.ca building detail fetch failed for {url}: {e}")
                continue

            building_name = listing.get("name") or b["name"]
            address1 = listing.get("address1", "")
            city = listing.get("city_name", "")
            location = listing.get("location") or {}
            building_furnished_raw = listing.get("furnished")  # "yes" / "no" / None
            amenity_names = _amenity_names(listing)
            # The structured `amenities` list is a small fixed taxonomy (~11
            # generic tags) that misses marketing terms like "fitness studio" —
            # confirmed on SVNTY, which has a real gym per its description_text
            # ("...including a fitness studio...") but no matching structured
            # tag. Search both, not just the structured list.
            description_text = (listing.get("description_text") or "").lower()
            amenities_text = " ".join(amenity_names) + " " + description_text
            has_gym = any(k in amenities_text for k in GYM_KEYWORDS)
            has_outdoor_pool = any(k in amenities_text for k in POOL_OUTDOOR_KEYWORDS)
            has_indoor_pool = any(k in amenities_text for k in POOL_INDOOR_KEYWORDS)

            for unit in listing.get("units", []):
                if unit.get("beds") not in (1.0, 2.0):
                    continue

                unit_furnished_raw = unit.get("furnished") or building_furnished_raw
                furnished = {"yes": True, "no": False}.get(unit_furnished_raw, None)

                avail = (unit.get("availability") or {})
                avail_date = unit.get("date_available") or (avail.get("date") if not avail.get("immediate") else "immediate")

                out.append({
                    "site": f"Rentals.ca ({search_path})",
                    "building": building_name,
                    "address": f"{address1}, {city}".strip(", "),
                    "unit_or_layout": f"unit {unit.get('id')}",
                    "unit_id": unit.get("id"),  # stable per-unit id for precise dedup
                    "beds": int(unit.get("beds")),
                    "has_den": bool(unit.get("den")),
                    "baths": unit.get("baths"),
                    "sqft": unit.get("sqft") or unit.get("dimensions"),
                    "price": unit.get("rent") or unit.get("rent_min"),
                    "available_date": avail_date,
                    "url": url,
                    "amenities_text": amenities_text,
                    "furnished": furnished,
                    "gym": has_gym,
                    "outdoor_pool": has_outdoor_pool,
                    "indoor_pool": has_indoor_pool,
                    "free_rent_flag": any(k in amenities_text for k in FREE_RENT_AMENITY_KEYWORDS),
                    "free_rent_detail": "",
                    "raw_lat": location.get("lat"),
                    "raw_lng": location.get("lng"),
                })
    return out
