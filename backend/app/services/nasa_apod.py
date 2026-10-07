"""NASA APOD service for birthday greetings.

Fetches an Astronomy Picture of the Day corresponding to the user's birth month and day
from a random year, with automatic retries and a resilient SpacePoint curated fallback.

Uses the keyless science.nasa.gov WordPress endpoint (no API key, no quota):
  - Specific date: https://science.nasa.gov/wp-json/wp/v2/apod-basic/yyMMdd
    (two-digit year, no dashes; 2022-09-30 -> .../apod-basic/220930)
  - Latest: https://science.nasa.gov/wp-json/wp/v2/apod-basic?per_page=1

The old https://api.nasa.gov/planetary/apod endpoint now returns HTTP 200 with a
"NASA Science" placeholder for every date, so responses are explicitly validated
to fail loudly instead of silently serving the placeholder.
"""

import calendar
import html
import logging
import random
import re
from datetime import date, datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

APOD_BASE_URL = "https://science.nasa.gov/wp-json/wp/v2/apod-basic"

CURATED_FALLBACK_APOD = {
    "title": "Cosmic Cliffs in the Carina Nebula",
    "explanation": (
        "Captured by NASA's James Webb Space Telescope in infrared light, this spectacular landscape "
        "of 'mountains' and 'valleys' speckled with glittering stars reveals previously invisible "
        "areas of early star formation in the young stellar nursery NGC 3324."
    ),
    "image_url": "https://images-assets.nasa.gov/image/PIA25421/PIA25421~orig.jpg",
    "year": 2022,
}


def _is_leap_year(year: int) -> bool:
    return calendar.isleap(year)


def _strip_html(raw: str) -> str:
    """Strip HTML tags and unescape entities, collapsing whitespace."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_explanation(raw: str) -> str:
    """Strip HTML from the new API's explanation and drop leading 'Explanation:'."""
    text = _strip_html(raw or "")
    text = re.sub(r"^explanation\s*:\s*", "", text, flags=re.IGNORECASE)
    return text


def _is_placeholder_response(title: str | None, image_url: str | None) -> bool:
    """Detect the silent-breakage placeholder from the retired API.

    Rejects responses where the title is exactly "NASA Science" or the image
    URL contains "nasa-logo", so this kind of silent breakage gets noticed
    (logged as an error and retried) instead of emailed to users.
    """
    if (title or "").strip() == "NASA Science":
        return True
    if image_url and "nasa-logo" in image_url.lower():
        return True
    return False


async def get_nasa_birthday_picture(birth_date: date, api_key: str | None = None) -> dict[str, Any]:
    """Fetches a NASA APOD image for the given birth month and day from a random year.

    Uses the keyless science.nasa.gov endpoint — no API key is needed and none
    is sent. ``api_key`` is kept only for backwards compatibility and is ignored.
    Retries up to 3 candidate years (skipping videos, placeholders, and 404s)
    before falling back to a curated SpacePoint deep space image.
    """
    if api_key:
        logger.warning("api_key argument is deprecated and ignored; the new APOD endpoint needs no key.")

    current_year = datetime.now(timezone.utc).year

    # Valid APOD archive begins mid-1995; 1996 gives full 12 months.
    min_year = 1996
    max_year = max(min_year, current_year - 1)

    month = birth_date.month
    day = birth_date.day

    # Sample candidate years without duplicates
    candidate_pool = list(range(min_year, max_year + 1))
    random.shuffle(candidate_pool)

    max_attempts = 3
    attempts = 0

    async with httpx.AsyncClient(timeout=10.0) as client:
        for year in candidate_pool:
            if attempts >= max_attempts:
                break

            # Handle Feb 29 for non-leap years
            target_day = day
            if month == 2 and day == 29 and not _is_leap_year(year):
                target_day = 28

            date_str = f"{year:04d}-{month:02d}-{target_day:02d}"
            apod_code = f"{year % 100:02d}{month:02d}{target_day:02d}"
            url = f"{APOD_BASE_URL}/{apod_code}"
            attempts += 1

            try:
                logger.info(
                    "Fetching NASA APOD for date=%s (attempt %s/%s)",
                    date_str,
                    attempts,
                    max_attempts,
                )

                resp = await client.get(url)
                if resp.status_code != 200:
                    # Dates with no entry may 404; any non-200 is retried, not fatal.
                    logger.warning(
                        "NASA APOD date %s returned status %s: %s",
                        date_str,
                        resp.status_code,
                        resp.text[:200],
                    )
                    continue

                data = resp.json()
                if isinstance(data, list):
                    if not data:
                        logger.warning("NASA APOD date %s returned empty list, retrying...", date_str)
                        continue
                    data = data[0]

                media_type = data.get("media_type")

                # We want an image, not a video — retry another year.
                if media_type != "image":
                    logger.warning(
                        "NASA APOD date %s returned non-image media_type=%s, retrying another year...",
                        date_str,
                        media_type,
                    )
                    continue

                # Use hdurl for the image; url now points to the article page.
                img_url = data.get("hdurl")
                title = (data.get("title") or f"Cosmic Wonder ({year})").strip()

                # Fail loudly on the silent-breakage placeholder.
                if _is_placeholder_response(title, img_url):
                    logger.error(
                        "NASA APOD date %s returned placeholder content (title=%r img=%r); "
                        "rejecting so silent breakage is noticed.",
                        date_str,
                        title,
                        img_url,
                    )
                    continue

                if not img_url:
                    logger.warning("NASA APOD date %s returned no hdurl, retrying another year...", date_str)
                    continue

                explanation = _clean_explanation(data.get("explanation") or "")
                if not explanation:
                    explanation = "Astronomy Picture of the Day captured on your special day."
                apod_url = data.get("url") or data.get("permalink") or "https://science.nasa.gov/skywatching/apod/"
                entry_date = data.get("date") or date_str
                return {
                    "title": title,
                    "explanation": explanation,
                    "image_url": img_url,
                    "year": year,
                    "date": entry_date,
                    "apod_url": apod_url,
                }

            except Exception as exc:
                logger.warning("NASA APOD fetch failed for %s: %s", date_str, exc)

    logger.warning("All NASA APOD attempts failed. Using curated SpacePoint fallback.")
    fallback = dict(CURATED_FALLBACK_APOD)
    # Give the fallback a realistic year
    fallback["year"] = random.randint(min_year, max_year)
    fallback["apod_url"] = "https://apod.nasa.gov/apod/archivepix.html"
    return fallback
