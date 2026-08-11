"""
Builds and sends the daily digest email over Gmail SMTP.

The app password is read from the GMAIL_APP_PASSWORD environment variable
only — never hardcoded, never logged. See README.md for how to set it
(locally via a .env-style export, or as a GitHub Actions secret).
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config


def _format_listing_html(c: dict) -> str:
    flags = []
    if c.get("flag_free_rent"):
        flags.append("💸 possible free-rent incentive")
    if c.get("flag_modern"):
        flags.append("✨ described as new/modern")
    if c.get("flag_outdoor_pool"):
        flags.append("🏊 outdoor pool")
    if c.get("flag_indoor_pool"):
        flags.append("🏊 indoor pool")
    if c.get("flag_furnished_unverified"):
        flags.append("⚠️ furnished status unverified — confirm before applying")
    if c.get("flag_not_furnished"):
        flags.append("❌ NOT furnished (shown anyway — Rentals.ca inventory is rarely furnished)")
    if c.get("flag_gym_unverified"):
        flags.append("⚠️ gym unverified — confirm before applying")
    if c.get("has_den"):
        flags.append("➕ has den")

    flags_html = "".join(f'<li style="margin:2px 0;">{f}</li>' for f in flags)
    price = c.get("price")
    price_str = f"${price:,.0f}/mo" if price else "price n/a"

    return f"""
    <div style="border:1px solid #ddd; border-radius:8px; padding:14px; margin-bottom:12px;">
      <div style="font-size:16px; font-weight:600;">{c.get('building', 'Unknown building')} — {price_str}</div>
      <div style="color:#555; font-size:14px;">{c.get('address', '')}</div>
      <div style="color:#555; font-size:14px;">{c.get('unit_or_layout', '')} · {c.get('sqft', 'sqft n/a')} sqft · via {c.get('source_name', c.get('site'))}</div>
      {'<ul style="padding-left:18px; margin:8px 0 0 0; font-size:13px;">' + flags_html + '</ul>' if flags else ''}
      <div style="margin-top:8px;"><a href="{c.get('url', '#')}" style="color:#1a73e8;">View listing →</a></div>
    </div>
    """


def _format_errors_html(errors: list[dict]) -> str:
    if not errors:
        return ""
    rows = "".join(
        f'<li><b>{e["site"]}</b>: {e["error"]}{" (known-fragile source)" if e["fragile"] else " ⚠️ UNEXPECTED FAILURE"}</li>'
        for e in errors
    )
    return f"""
    <div style="margin-top:20px; padding:12px; background:#fff8e1; border-radius:8px; font-size:13px;">
      <b>Sources that failed to scrape today:</b>
      <ul>{rows}</ul>
    </div>
    """


def _group_listings(new_listings: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group listings by their 'group' field (e.g. "The Taylor", "Rentals.ca"),
    preserving config.SITES order, with each group's listings sorted by price.
    """
    order = []
    seen = set()
    for site in config.SITES:
        g = site.get("group", site["name"])
        if g not in seen:
            seen.add(g)
            order.append(g)

    by_group: dict = {}
    for c in new_listings:
        by_group.setdefault(c.get("group", c.get("source_name", "Other")), []).append(c)

    for listings in by_group.values():
        listings.sort(key=lambda c: (c.get("price") is None, c.get("price")))

    return [(g, by_group[g]) for g in order if g in by_group]


def _format_group_html(group_name: str, listings: list[dict]) -> str:
    cards = "".join(_format_listing_html(c) for c in listings)
    return f"""
    <div style="margin-bottom:24px;">
      <div style="font-size:15px; font-weight:700; text-transform:uppercase; letter-spacing:0.03em;
                  color:#333; border-bottom:2px solid #333; padding-bottom:4px; margin-bottom:10px;">
        {group_name} <span style="font-weight:400; color:#888; text-transform:none;">({len(listings)})</span>
      </div>
      {cards}
    </div>
    """


def build_email_html(new_listings: list[dict], errors: list[dict]) -> str:
    if not new_listings:
        body = "<p>No new listings matched your filters today.</p>"
    else:
        body = "".join(_format_group_html(g, listings) for g, listings in _group_listings(new_listings))

    return f"""
    <html><body style="font-family: -apple-system, Arial, sans-serif; max-width:600px; margin:0 auto;">
      <h2>Toronto 1BR/1BR+Den Digest</h2>
      <p style="color:#666; font-size:13px;">
        Filters: ≤${config.MAX_RENT:,}/mo · furnished · gym · Liberty Village / Fort York / King West area ·
        move-in Nov 1–30
      </p>
      {body}
      {_format_errors_html(errors)}
    </body></html>
    """


def send_digest(new_listings: list[dict], errors: list[dict]) -> list[str]:
    """Sends the digest email. Returns the list of listing_ids that were
    successfully included in a sent email (used by main.py to mark them
    as emailed in the store — nothing gets marked emailed if sending
    fails, so a failed send safely retries the same listings next run).
    """
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not password:
        raise RuntimeError(
            "GMAIL_APP_PASSWORD environment variable is not set. "
            "See README.md for how to configure it — never hardcode it in this repo."
        )

    subject = (
        f"🏠 {len(new_listings)} new Toronto rental match(es)"
        if new_listings
        else "🏠 No new Toronto rental matches today"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO
    msg.attach(MIMEText(build_email_html(new_listings, errors), "html"))

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.EMAIL_FROM, password)
        server.sendmail(config.EMAIL_FROM, [config.EMAIL_TO], msg.as_string())

    print(f"Sent digest: {subject}")
    return [c["listing_id"] for c in new_listings]
