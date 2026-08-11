# Toronto Rental Digest

Scrapes a handful of Toronto rental sources daily, filters for 1BR / 1BR+den
matching your criteria, dedupes against everything already emailed, and
sends you a digest. No LLM calls happen in the daily run — it's plain
Python, so the recurring cost is effectively $0.

## What it checks

- ≤ $3,800/mo
- 1 bedroom or 1 bedroom + den
- Furnished (hard requirement — see caveat below)
- Building gym (hard requirement — see caveat below)
- Liberty Village / Fort York / King West, or within 3km of the Salesforce
  Toronto office
- Move-in Nov 1–30, 2026
- Flags (doesn't exclude): free-rent incentives, "modern" building language,
  outdoor/indoor pool

**Furnished/gym caveat:** several sources don't reliably expose per-unit
furnished status or a clean "gym" tag on their summary pages. A listing is
only *excluded* if a source explicitly says "not furnished" or lacks a gym
— when it's simply not stated, the listing is included but marked
"⚠️ unverified" in the email so you can double-check before applying.

## Sources

| Source | Method |
|---|---|
| The Taylor (Tricon) | Public JSON API |
| Rentals.ca (Liberty Village, King St W) | Headless-browser fetch, parses embedded JSON |
| Condos.ca (Ten York) | Headless-browser fetch, parses page text |
| FourFifty The Well (RentCafe) | Headless-browser fetch, parses page text — **most fragile source**, sits behind Cloudflare |

Rentals.ca and RentCafe block plain HTTP requests (confirmed during build);
all headless-browser fetches go through `browser_fetch.py`, which retries
transient failures twice before giving up. A source failing outright is
reported as a warning inside the digest email, not a silent skip or a
crash.

## One-time setup

```bash
cd rental_agent
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python3 -m playwright install chromium --with-deps
```

### Gmail app password

1. Go to https://myaccount.google.com/apppasswords and generate a new app
   password (requires 2-factor auth enabled on the account).
2. **Never put it in any file in this repo.** Set it as an environment
   variable when running locally:
   ```bash
   export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
   ```
3. For the GitHub Actions version, add it as a repo secret instead (Settings
   → Secrets and variables → Actions → New repository secret, name
   `GMAIL_APP_PASSWORD`) — GitHub injects it at run time, it's never
   visible in the code or logs.

## Running manually

```bash
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
./venv/bin/python3 main.py
```

## Adding a new site later

1. Add a scraper module in `scrapers/` with a `scrape(site_config) -> list[dict]`
   function returning the same fields as the existing scrapers.
2. Add one entry to `SITES` in `config.py`.
That's it — `main.py` picks it up automatically.

## Tuning filters

Everything adjustable (price, areas, dates, keywords) lives at the top of
`config.py` — no other file should need touching for a simple change.

## Dedupe policy

Once a listing has been emailed, it's never re-sent — even if its price
later drops (per your call). State lives in `state/seen_listings.json`.
