import os
import requests
from datetime import datetime, timedelta, timezone


YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

_trendlyne_channel_id = None


def _get_trendlyne_channel_id():
    global _trendlyne_channel_id
    if _trendlyne_channel_id:
        return _trendlyne_channel_id
    try:
        resp = requests.get(
            YOUTUBE_CHANNELS_URL,
            params={"part": "id", "forHandle": "trendlyne", "key": YOUTUBE_API_KEY},
            timeout=10,
        )
        items = resp.json().get("items", [])
        if items:
            _trendlyne_channel_id = items[0]["id"]
    except Exception:
        pass
    return _trendlyne_channel_id


def fetch_trendlyne_earnings_call(company, days_back=180):
    if not YOUTUBE_API_KEY:
        return None
    channel_id = _get_trendlyne_channel_id()
    if not channel_id:
        return None

    published_after = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    params = {
        "part": "snippet",
        "q": company["name"],
        "channelId": channel_id,
        "type": "video",
        "order": "date",
        "publishedAfter": published_after,
        "maxResults": 1,
        "key": YOUTUBE_API_KEY,
    }
    try:
        data = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=10).json()
        items = data.get("items", [])
        if not items:
            return None
        item = items[0]
        return {
            "title": item["snippet"]["title"],
            "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
        }
    except Exception:
        return None


def fetch_all_trendlyne_calls(companies):
    results = {}
    for company in companies:
        video = fetch_trendlyne_earnings_call(company)
        if video:
            results[company["name"]] = video
    return results


def fetch_earnings_call(company, days_back=90):
    if not YOUTUBE_API_KEY:
        return None

    query = f"{company['name']} earnings call quarterly results"
    published_after = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "date",
        "publishedAfter": published_after,
        "maxResults": 1,
        "key": YOUTUBE_API_KEY,
    }

    try:
        response = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=10)
        data = response.json()
        items = data.get("items", [])
        if not items:
            return None

        item = items[0]
        video_id = item["id"]["videoId"]
        title = item["snippet"]["title"]
        return {
            "title": title,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }
    except Exception:
        return None


def fetch_all_earnings_calls(companies):
    results = {}
    for company in companies:
        video = fetch_earnings_call(company)
        if video:
            results[company["name"]] = video
    return results
