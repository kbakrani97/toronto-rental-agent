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
MIN_BEDS = 1          # 1BR or 1BR+den only (den doesn't count as a 2nd bed
                       # on most sites, so max_beds stays 1 too)
MAX_BEDS = 1
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
SITES = [
    {
        "name": "The Taylor (Tricon)",
        "scraper": "tricon",
        "slug": "the-taylor",
    },
    {
        "name": "Rentals.ca - Liberty Village",
        "scraper": "rentals_ca",
        "path": "toronto/liberty-village",
        "fragile": True,  # observed intermittent 403s from rentals.ca's bot detection during build
    },
    {
        "name": "Rentals.ca - King Street West",
        "scraper": "rentals_ca",
        "path": "toronto/king-street-west",
        "fragile": True,
    },
    {
        "name": "Condos.ca - Ten York",
        "scraper": "condos_ca",
        "path": "toronto/ten-york-10-york-st",
        # Named building you asked for explicitly — skip the generic
        # neighbourhood-keyword area check (its address text won't say
        # "Liberty Village"/"King West").
        "always_in_area": True,
    },
    {
        "name": "FourFifty The Well (RentCafe)",
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
