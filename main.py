#!/usr/bin/env python3
"""
Daily orchestrator: scrape every configured site, apply hard filters,
dedupe against the persistent store, and email the digest.

No LLM calls happen anywhere in this file — every decision is plain code.
Run manually with:
    ./venv/bin/python3 main.py
"""
import importlib
import re
import sys
import traceback
from datetime import datetime

import config
import store
from emailer import send_digest

SCRAPER_MODULES = {
    "tricon": "scrapers.tricon",
    "rentals_ca": "scrapers.rentals_ca",
    "condos_ca": "scrapers.condos_ca",
    "condos_ca_area": "scrapers.condos_ca_area",
    "rentcafe": "scrapers.rentcafe",
}


def run_all_scrapers():
    """Run every site in config.SITES. Returns (candidates, errors).

    A failure in one site never aborts the others — sites marked
    "fragile" in config.py (currently RentCafe, due to Cloudflare) are
    expected to fail occasionally; any site failing is reported as a
    warning in the digest rather than crashing the whole run.
    """
    all_candidates = []
    errors = []

    for site in config.SITES:
        module_path = SCRAPER_MODULES[site["scraper"]]
        try:
            mod = importlib.import_module(module_path)
            results = mod.scrape(site)
            for r in results:
                r["source_name"] = site["name"]
                r["group"] = site.get("group", site["name"])
                r["always_in_area"] = site.get("always_in_area", False)
                r["allow_unfurnished"] = site.get("allow_unfurnished", False)
            all_candidates.extend(results)
            print(f"[ok] {site['name']}: {len(results)} raw candidates")
        except Exception as e:
            fragile = site.get("fragile", False)
            msg = f"{site['name']}: {e}"
            errors.append({"site": site["name"], "error": str(e), "fragile": fragile})
            print(f"[{'warn' if fragile else 'ERROR'}] {msg}")
            if not fragile:
                traceback.print_exc()

    return all_candidates, errors


def _parse_sqft(raw) -> "int | None":
    """Sqft shows up as an int, a float, a numeric string, or a range
    string like "500-599" depending on source. Returns the lower bound as
    an int, or None if unparseable/absent — unknown sqft is let through
    (same "don't drop on missing data" policy as furnished/gym), only a
    known value below MIN_SQFT excludes a listing.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    digits = re.findall(r"\d+", str(raw))
    return int(digits[0]) if digits else None


def passes_hard_filters(c: dict) -> bool:
    price = c.get("price")
    if price is None or price > config.MAX_RENT:
        return False

    beds = c.get("beds")
    if beds is None or not (config.MIN_BEDS <= beds <= config.MAX_BEDS):
        return False

    sqft = _parse_sqft(c.get("sqft"))
    if sqft is not None and sqft < config.MIN_SQFT:
        return False

    # Furnished: hard requirement, but many sources can't verify it from a
    # summary page. Policy: exclude only if EXPLICITLY not furnished;
    # unverified (None) is allowed through but flagged in the email.
    # Exception: sources marked allow_unfurnished (currently Rentals.ca,
    # whose standard inventory is essentially always unfurnished) show
    # unfurnished matches too, clearly labeled, rather than contributing
    # ~nothing — see config.py for why.
    if c.get("furnished") is False and not c.get("allow_unfurnished"):
        return False

    # Gym: same unverified-vs-explicitly-false policy as furnished.
    if c.get("gym") is False:
        return False

    return True


def area_matches(c: dict) -> bool:
    if c.get("always_in_area"):
        return True

    haystack = " ".join(str(c.get(k, "")) for k in ("address", "building", "site")).lower()
    if any(area in haystack for area in config.ALLOWED_AREAS):
        return True

    lat, lng = c.get("raw_lat"), c.get("raw_lng")
    if lat and lng:
        dist = _haversine_km(lat, lng, *config.SALESFORCE_TORONTO_LATLNG)
        if dist <= config.MAX_KM_FROM_SALESFORCE:
            return True

    return False


def _haversine_km(lat1, lng1, lat2, lng2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def annotate_soft_signals(c: dict) -> dict:
    text = (c.get("amenities_text") or "") + " " + (c.get("free_rent_detail") or "")
    text = text.lower()

    c["flag_free_rent"] = c.get("free_rent_flag") or any(k in text for k in config.FREE_RENT_KEYWORDS)
    c["flag_modern"] = any(k in text for k in config.MODERN_BUILDING_KEYWORDS)
    c["flag_outdoor_pool"] = c.get("outdoor_pool") or any(k in text for k in config.POOL_KEYWORDS_OUTDOOR)
    c["flag_indoor_pool"] = c.get("indoor_pool") or any(k in text for k in config.POOL_KEYWORDS_INDOOR)
    c["flag_furnished_unverified"] = c.get("furnished") is None
    c["flag_not_furnished"] = c.get("furnished") is False  # only reaches here if allow_unfurnished let it through
    c["flag_gym_unverified"] = c.get("gym") is None
    return c


def apply_known_amenities(c: dict) -> dict:
    known = config.KNOWN_BUILDING_AMENITIES.get(c.get("building"))
    if not known:
        return c
    for key in ("gym", "outdoor_pool", "indoor_pool"):
        if c.get(key) is None and key in known:
            c[key] = known[key]
    return c


def main():
    print(f"=== Rental digest run: {datetime.now().isoformat()} ===")

    candidates, errors = run_all_scrapers()
    print(f"Total raw candidates: {len(candidates)}")

    candidates = [apply_known_amenities(c) for c in candidates]
    filtered = [c for c in candidates if passes_hard_filters(c) and area_matches(c)]
    print(f"After hard filters + area match: {len(filtered)}")

    filtered = [annotate_soft_signals(c) for c in filtered]

    for c in filtered:
        c["listing_id"] = store.make_listing_id(
            c.get("site", ""), c.get("address", ""), c.get("unit_or_layout", "")
        )

    state = store.load_state()
    new_listings = store.filter_new(state, filtered)
    print(f"New (never-emailed) listings: {len(new_listings)}")

    sent_ids = send_digest(new_listings, errors)

    store.mark_emailed(state, sent_ids)
    store.save_state(state)
    print("State saved.")


if __name__ == "__main__":
    main()
