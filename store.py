"""
Persistent dedupe store. One JSON file, one row per listing_id.

Policy (per user decision): once a listing has been emailed, it is never
emailed again — even if its price later changes.
"""
import json
import hashlib
import os
from datetime import date, datetime

import config


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def make_listing_id(site: str, address: str, unit_or_layout: str, price) -> str:
    """Stable ID for dedupe: hash of site + normalized address + unit/layout + price bucket.

    Price is intentionally included so a *new* unit at a *different* price in
    the same building is treated as a distinct listing, while re-scraping the
    exact same still-listed unit each day produces the same id.
    """
    raw = f"{_normalize(site)}|{_normalize(address)}|{_normalize(unit_or_layout)}|{price}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def load_state(path: str = config.STATE_PATH) -> dict:
    if not os.path.exists(path):
        return {"listings": {}}
    with open(path, "r") as f:
        return json.load(f)


def save_state(state: dict, path: str = config.STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, path)


def filter_new(state: dict, candidates: list[dict]) -> list[dict]:
    """Given today's scraped candidates (each a dict with a 'listing_id' key
    already set), return only the ones never emailed before, and mark
    everything (new or not) with first_seen/last_seen bookkeeping.
    """
    today = date.today().isoformat()
    new_ones = []
    listings = state.setdefault("listings", {})

    for c in candidates:
        lid = c["listing_id"]
        if lid not in listings:
            listings[lid] = {
                "first_seen": today,
                "last_seen": today,
                "emailed": False,
                "url": c.get("url"),
                "site": c.get("site"),
            }
        else:
            listings[lid]["last_seen"] = today

        if not listings[lid]["emailed"]:
            new_ones.append(c)

    return new_ones


def mark_emailed(state: dict, sent_listing_ids: list[str]) -> None:
    listings = state.get("listings", {})
    for lid in sent_listing_ids:
        if lid in listings:
            listings[lid]["emailed"] = True
