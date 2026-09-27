"""NASA APOD service for birthday greetings.

Fetches an Astronomy Picture of the Day corresponding to the user's birth month and day
from a random year, with automatic retries and a resilient SpacePoint curated fallback.
"""

import calendar
import logging
import random
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

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


async def get_nasa_birthday_picture(birth_date: date, api_key: str | None = None) -> dict[str, Any]:
    """Fetches a NASA APOD image for the given birth month and day from a random year.

    Retries up to 2 other random years if the result is not an image or fails.
    Falls back to a curated SpacePoint deep space image if all requests fail.
    """
    key = api_key or settings.NASA_API_KEY or "DEMO_KEY"
    current_year = datetime.now(timezone.utc).year

    # Valid APOD archive begins mid-1995; 1996 gives full 12 months.
    min_year = 1996
    max_year = max(min_year, current_year - 1)

    month = birth_date.month
    day = birth_date.day

    # Sample candidate years without duplicates
    candidate_pool = list(range(min_year, max_year + 1))
    random.shuffle(candidate_pool)

    attempts = 0
    max_attempts = 3

    async with httpx.AsyncClient(timeout=10.0) as client:
        for year in candidate_pool:
            if attempts >= max_attempts:
                break

            # Handle Feb 29 for non-leap years
            target_day = day
            if month == 2 and day == 29 and not _is_leap_year(year):
                target_day = 28

            date_str = f"{year:04d}-{month:02d}-{target_day:02d}"
            attempts += 1

            try:
                url = "https://api.nasa.gov/planetary/apod"
                params = {"api_key": key, "date": date_str}
                logger.info("Fetching NASA APOD for date=%s (attempt %s/%s)", date_str, attempts, max_attempts)

                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    media_type = data.get("media_type")

                    # We want an image, not a youtube video or audio
                    if media_type == "image":
                        img_url = data.get("hdurl") or data.get("url")
                        if img_url:
                            title = data.get("title", f"Cosmic Wonder ({year})")
                            explanation = data.get("explanation", "Astronomy Picture of the Day captured on your special day.")
                            return {
                                "title": title,
                                "explanation": explanation,
                                "image_url": img_url,
                                "year": year,
                            }
                    logger.warning("NASA APOD date %s returned non-image media_type=%s, retrying another year...", date_str, media_type)
                else:
                    logger.warning("NASA APOD date %s returned status %s: %s", date_str, resp.status_code, resp.text[:200])

            except Exception as exc:
                logger.warning("NASA APOD fetch failed for %s: %s", date_str, exc)

    logger.warning("All NASA APOD attempts failed or rate-limited. Using curated SpacePoint fallback.")
    fallback = dict(CURATED_FALLBACK_APOD)
    # Give the fallback a realistic year
    fallback["year"] = random.randint(min_year, max_year)
    return fallback
