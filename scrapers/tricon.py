"""
Scraper for Tricon-managed buildings (currently: The Taylor).

Tricon exposes a clean public JSON API at
    https://triconliving.com/api/v1/apartments/<slug>
which includes a full per-unit breakdown (beds, sqft, rent, floor,
availability date, amenities, concessions) — no browser rendering needed.
"""
import requests

API_URL = "https://triconliving.com/api/v1/apartments/{slug}"


def scrape(site_config: dict) -> list[dict]:
    slug = site_config["slug"]
    resp = requests.get(API_URL.format(slug=slug), timeout=20)
    resp.raise_for_status()
    data = resp.json()

    building_name = data.get("name", slug)
    address = data.get("address", {})
    full_address = f"{address.get('street_address', '')}, {address.get('city', '')}"
    building_amenities = [a.lower() for a in data.get("amenities", [])]
    building_concessions = data.get("concessions", [])
    listing_url = data.get("path", f"https://triconliving.com/apartment/{slug}/")

    out = []
    for unit in data.get("units", []):
        if unit.get("beds") is None:
            continue

        rent = unit.get("min_rent") or unit.get("max_rent")
        avail = (unit.get("availability") or {}).get("date")

        out.append({
            "site": "The Taylor (Tricon)",
            "building": building_name,
            "address": full_address,
            "unit_or_layout": unit.get("unit_code") or unit.get("unit_type_code"),
            "beds": unit.get("beds"),
            "baths": unit.get("baths"),
            "sqft": unit.get("sqft"),
            "price": rent,
            "available_date": avail,
            "url": listing_url,
            "amenities_text": " ".join(building_amenities),
            # NOTE: The Taylor's API doesn't tag furnished status per-unit —
            # "furnished suite packages" are advertised as an optional add-on
            # for the building overall, not a per-listing field. main.py's
            # furnished filter can't verify this reliably for Tricon
            # buildings; these listings are flagged "furnished: unverified"
            # rather than silently assumed true or excluded.
            "furnished": None,
            "free_rent_flag": bool(building_concessions),
            "free_rent_detail": "; ".join(c.get("headline", "") for c in building_concessions),
            "raw_lat": data.get("lat"),
            "raw_lng": data.get("lng"),
        })
    return out
