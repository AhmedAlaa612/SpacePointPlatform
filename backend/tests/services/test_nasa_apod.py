from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
import httpx

from app.services.nasa_apod import CURATED_FALLBACK_APOD, get_nasa_birthday_picture
from app.services.email import send_birthday_greeting_email


@pytest.mark.asyncio
async def test_nasa_apod_successful_image():
    mock_response = httpx.Response(
        200,
        json={
            "date": "2015-09-30",
            "explanation": "A stunning view of the Orion Nebula.",
            "hdurl": "https://apod.nasa.gov/apod/image/1509/orion_hd.jpg",
            "media_type": "image",
            "title": "The Great Orion Nebula",
            "url": "https://apod.nasa.gov/apod/image/1509/orion.jpg",
        },
        request=httpx.Request("GET", "https://api.nasa.gov/planetary/apod"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        data = await get_nasa_birthday_picture(date(2000, 9, 30))

        assert data["title"] == "The Great Orion Nebula"
        assert "orion" in data["image_url"]
        assert data["explanation"] == "A stunning view of the Orion Nebula."
        assert 1996 <= data["year"] <= 2026


@pytest.mark.asyncio
async def test_nasa_apod_retry_on_video_then_fallback():
    # If API returns video or 500 repeatedly, it retries and falls back
    video_response = httpx.Response(
        200,
        json={
            "media_type": "video",
            "url": "https://www.youtube.com/watch?v=123",
            "title": "A Video of the Moon",
        },
        request=httpx.Request("GET", "https://api.nasa.gov/planetary/apod"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = video_response

        data = await get_nasa_birthday_picture(date(1998, 5, 12))

        # Should fall back to curated SpacePoint fallback
        assert data["title"] == CURATED_FALLBACK_APOD["title"]
        assert data["image_url"] == CURATED_FALLBACK_APOD["image_url"]
        assert mock_get.call_count == 3


@pytest.mark.asyncio
async def test_nasa_apod_fallback_on_network_or_api_error():
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Network unreachable")):
        data = await get_nasa_birthday_picture(date(1995, 1, 1), api_key="INVALID_KEY")

        assert data["title"] == CURATED_FALLBACK_APOD["title"]
        assert data["image_url"] == CURATED_FALLBACK_APOD["image_url"]
        assert 1996 <= data["year"] <= 2026


@pytest.mark.asyncio
async def test_nasa_apod_leap_year_handling():
    # Feb 29 birthdate on non-leap years should safely adjust to Feb 28 without crashing
    mock_response = httpx.Response(
        200,
        json={
            "media_type": "image",
            "hdurl": "https://apod.nasa.gov/leap_hd.jpg",
            "url": "https://science.nasa.gov/apod/leap/",
            "title": "Leap Day Wonder",
            "explanation": "Cosmic view",
        },
        request=httpx.Request("GET", "https://science.nasa.gov/wp-json/wp/v2/apod-basic/220228"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        data = await get_nasa_birthday_picture(date(2000, 2, 29))
        assert data["title"] == "Leap Day Wonder"
        assert data["image_url"] == "https://apod.nasa.gov/leap_hd.jpg"


@pytest.mark.asyncio
async def test_send_birthday_greeting_email_format():
    with patch("app.services.email.try_send_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        apod_data = {
            "title": "Pillars of Creation",
            "explanation": "Dust and gas in the Eagle Nebula.",
            "image_url": "https://example.com/pillars.jpg",
            "year": 2014,
        }

        success = await send_birthday_greeting_email(
            to_email="student@spacepoint.ae",
            full_name="Fatima Al-Nuaimi",
            apod_data=apod_data,
        )

        assert success is True
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert kwargs["to"] == "student@spacepoint.ae"
        assert kwargs["subject"] == "SpacePoint - Your Birthday Cosmic View"
        assert "Fatima" in kwargs["body"]
        assert kwargs["html"] is True
        assert "Pillars of Creation" in kwargs["body"]
        assert "2014" in kwargs["body"]
        assert "https://example.com/pillars.jpg" in kwargs["body"]
        assert "Open SpacePoint Portal" not in kwargs["body"]
        assert "A view captured from space on your" in kwargs["body"]
        assert "Happy Orbit Completion, Fatima!" in kwargs["body"]


@pytest.mark.asyncio
async def test_nasa_apod_uses_real_key_first_and_falls_back_to_demo_key():
    # Service now uses the keyless science.nasa.gov endpoint (ignoring any legacy api_key arg),
    # retries another year on non-200 / placeholder responses, and returns hdurl when available.
    rate_limited_response = httpx.Response(
        429,
        json={"error": {"code": "OVER_RATE_LIMIT", "message": "Limit exceeded"}},
        request=httpx.Request("GET", "https://science.nasa.gov/wp-json/wp/v2/apod-basic/990310"),
    )
    success_response = httpx.Response(
        200,
        json={
            "media_type": "image",
            "hdurl": "https://apod.nasa.gov/demo_success.jpg",
            "url": "https://science.nasa.gov/apod/990310/",
            "title": "Fallback Demo Nebula",
            "explanation": "Loaded after retry without needing API key",
        },
        request=httpx.Request("GET", "https://science.nasa.gov/wp-json/wp/v2/apod-basic/000310"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [rate_limited_response, success_response]

        data = await get_nasa_birthday_picture(date(1999, 3, 10), api_key="MY_REAL_SECRET_KEY")

        assert data["title"] == "Fallback Demo Nebula"
        assert data["image_url"] == "https://apod.nasa.gov/demo_success.jpg"
        assert mock_get.call_count == 2
        # Confirm keyless calls do not send api_key query params
        for call in mock_get.call_args_list:
            assert "params" not in call.kwargs or "api_key" not in (call.kwargs.get("params") or {})


