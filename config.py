"""
Central configuration for the Toronto rental-hunting agent.
Edit this file to tune filters or add/remove sites — nothing else should
need to change for simple tweaks.
"""
from datetime import date

# ---------------------------------------------------------------------------
# Hard filters — a listing that fails ANY of these is dropped silently.
# ---------------------------------------------------------------------------
MAX_RENT = 3800
MIN_BEDS = 1           # 1BR through 2BR, each optionally +den (den doesn't
MAX_BEDS = 2           # add to the beds count, e.g. "1.5 bed" = 1BR+den)
MIN_SQFT = 600         # excludes a listing only when sqft is known and
                       # below this; unknown sqft is let through unfiltered
                       # (same "don't drop on missing data" policy as furnished)
REQUIRE_FURNISHED = True
REQUIRE_GYM = True

MOVE_IN_WINDOW = (date(2026, 11, 1), date(2026, 11, 30))

# Neighbourhoods / areas that count as a match. Matching is done as a
# case-insensitive substring check against the listing's address/area text,
# OR by lat/lng radius for sources that give coordinates (see geo below).
ALLOWED_AREAS = [
    "liberty village",
    "fort york",
    "king west",
    "king st w",
    "king street w",
    "fashion district",  # The Taylor's neighbourhood, near King West
    "waterfront",        # Ten York
    "harbourfront",
]

# Fallback: straight-line distance (km) from the Salesforce Toronto office
# (RBC WaterPark Place, 181 Bay St) used only when a listing has coordinates
# but no clean neighbourhood name to match against.
SALESFORCE_TORONTO_LATLNG = (43.6435, -79.3791)
MAX_KM_FROM_SALESFORCE = 3.0

# ---------------------------------------------------------------------------
# Soft signals — never exclude a listing, just annotate it in the email.
# ---------------------------------------------------------------------------
FREE_RENT_KEYWORDS = [
    "free rent", "month free", "months free", "rent free", "incentive",
    "look and lease", "limited time offer", "% off",
]
MODERN_BUILDING_KEYWORDS = [
    "brand new", "newly built", "new construction", "just completed",
    "recently completed", "state-of-the-art",
]
POOL_KEYWORDS_OUTDOOR = ["outdoor pool", "rooftop pool"]
POOL_KEYWORDS_INDOOR = ["indoor pool"]

# ---------------------------------------------------------------------------
# Sites. Each entry names the scraper module (in scrapers/) and any args
# it needs. Add a new site by adding one dict here + one scraper module.
# ---------------------------------------------------------------------------
# The order below also controls the order sections appear in the email.
SITES = [
    {
        "name": "The Taylor (Tricon)",
        "group": "The Taylor",
        "scraper": "tricon",
        "slug": "the-taylor",
    },
    {
        "name": "Rentals.ca - Liberty Village",
        "group": "Rentals.ca",
        "scraper": "rentals_ca",
        "path": "toronto/liberty-village",
        "fragile": True,  # observed intermittent 403s from rentals.ca's bot detection during build
        # Rentals.ca's standard inventory is essentially always unfurnished
        # (confirmed during build — 100% of a 28-unit sample). A hard
        # furnished requirement would make this source contribute ~nothing,
        # so per your call: show unfurnished matches too, clearly labeled,
        # instead of hard-excluding them.
        "allow_unfurnished": True,
    },
    {
        "name": "Rentals.ca - King Street West",
        "group": "Rentals.ca",
        "scraper": "rentals_ca",
        "path": "toronto/king-street-west",
        "fragile": True,
        "allow_unfurnished": True,
    },
    {
        "name": "Condos.ca - Ten York",
        "group": "Condos.ca",
        "scraper": "condos_ca",
        "path": "toronto/ten-york-10-york-st",
        # Named building you asked for explicitly — skip the generic
        # neighbourhood-keyword area check (its address text won't say
        # "Liberty Village"/"King West").
        "always_in_area": True,
        # Same policy as Rentals.ca (per your call): individually-owned
        # condo rentals are frequently unfurnished, so hard-requiring
        # furnished would silently drop real matches — show them labeled
        # instead of excluding.
        "allow_unfurnished": True,
    },
    {
        "name": "Condos.ca - Downtown area",
        "group": "Condos.ca",
        "scraper": "condos_ca_area",
        "path": "toronto/downtown/condos-for-rent",
        # Covers King West, Fort York, The Waterfront (and other Downtown
        # neighbourhoods filtered out downstream) — see module docstring
        # for the page-1-only coverage caveat.
        "allow_unfurnished": True,
    },
    {
        "name": "Condos.ca - West End area",
        "group": "Condos.ca",
        "scraper": "condos_ca_area",
        "path": "toronto/west-end/condos-for-rent",
        # Covers Liberty Village.
        "allow_unfurnished": True,
    },
    {
        "name": "FourFifty The Well (RentCafe)",
        "group": "FourFifty The Well",
        "scraper": "rentcafe",
        "path": "on/toronto/fourfifty-the-well",
        "fragile": True,  # Cloudflare-protected; failures here should warn, not crash the run
        "always_in_area": True,  # named building, King West/Front St W
    },
]

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_TO = "kbakrani97@gmail.com"
EMAIL_FROM = "kbakrani97@gmail.com"          # Gmail account sending the digest
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
# The app password is read from the GMAIL_APP_PASSWORD environment variable
# at send time — it is never stored in this repo. See README.md.

# ---------------------------------------------------------------------------
# Known building facts — manually verified during build, used to fill in
# gym/pool info that a given site's scraper can't reliably detect on its
# own (e.g. The Taylor's own site names its gym "Club Apex", which no
# generic "gym" keyword search would catch).
# ---------------------------------------------------------------------------
KNOWN_BUILDING_AMENITIES = {
    "The Taylor": {"gym": True, "outdoor_pool": True, "indoor_pool": False},
}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
STATE_PATH = "state/seen_listings.json"
