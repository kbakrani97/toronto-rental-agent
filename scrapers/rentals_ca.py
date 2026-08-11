"""
Scraper for Rentals.ca neighbourhood/search pages.

Rentals.ca server-renders a full GraphQL-style JSON payload inline in the
page HTML (assigned to `App.store.search = { response: {...} }` inside a
<script> tag). We fetch the plain HTML with `requests` and extract that
JSON with a brace-balancing scan — no headless browser required.

CAVEAT: this gives building-level summaries (rentRange, bedsRange) from the
search/neighbourhood page, not a definitive per-unit list. For a precise
per-unit price you'd follow `path` into the building's own page, which
embeds the same kind of payload with a per-floorplan breakdown. Not wired
up yet — see TODO at bottom.
"""
import json
from browser_fetch import fetch_html

BASE_URL = "https://rentals.ca/{path}"


def _extract_search_json(html: str) -> dict:
    marker = "App.store.search = {"
    idx = html.find(marker)
    if idx == -1:
        raise ValueError("Could not find embedded search data — rentals.ca may have changed its page structure")

    start = html.find("response:", idx) + len("response:")
    # skip whitespace
    while html[start] in " \t\n":
        start += 1

    depth = 0
    i = start
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
        raise ValueError("Unbalanced braces while extracting rentals.ca search JSON")

    return json.loads(html[start:end])


def scrape(site_config: dict) -> list[dict]:
    path = site_config["path"]
    html = fetch_html(BASE_URL.format(path=path))

    payload = _extract_search_json(html)
    edges = payload["data"]["edges"]

    out = []
    for edge in edges:
        node = edge["node"]
        beds_range = node.get("bedsRange") or [None, None]
        rent_range = node.get("rentRange") or [None, None]
        address = node.get("address", {})
        street = address.get("street", "")
        city = (address.get("city") or {}).get("cityName", "")

        # Skip room-shares (residential:room:*) — we only want whole apartments.
        if not (node.get("listingType") or "").startswith("residential:apartment"):
            continue

        # Only keep buildings whose beds range includes a 1-bedroom.
        if not (beds_range[0] is not None and beds_range[0] <= 1 <= (beds_range[1] or beds_range[0])):
            continue

        out.append({
            "site": f"Rentals.ca ({path})",
            "building": node.get("rentalListingName") or street,
            "address": f"{street}, {city}",
            "unit_or_layout": "building-level (see listing page for specific unit)",
            "beds": 1,
            "baths": None,
            "sqft": None,
            "price": rent_range[0],  # starting price; real unit price may differ
            "price_max": rent_range[1],
            "available_date": None,  # not in the summary payload
            "url": f"https://rentals.ca/{node.get('path')}",
            "amenities_text": "",
            "furnished": None,  # not available at summary level
            "free_rent_flag": False,
            "free_rent_detail": "",
            "raw_lat": (node.get("rentalListingLocation") or [None, None])[1],
            "raw_lng": (node.get("rentalListingLocation") or [None, None])[0],
        })
    return out

# TODO (future improvement): fetch node["path"] individually and extract the
# same App.store.search-style payload from the building's own page to get
# real per-unit prices/availability/furnished status instead of the
# building-level range. Left out of v1 to keep the request count low.
