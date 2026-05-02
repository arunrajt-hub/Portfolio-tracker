import requests
import re
from datetime import datetime, timedelta, timezone

BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json",
}

def strip_html(text):
    return re.sub(r"<[^>]+>", "", text).strip()


EXCLUDE_KEYWORDS = [
    "buy", "sell", "target price", "rating", "rated", "outperform",
    "underperform", "overweight", "underweight", "hold", "reduce",
    "strong buy", "accumulate", "brokerage", "analyst",
    "nav as on", "investor complaints", "scheme nav", "debt scheme",
    "isif nav", "mf nav", "mutual fund nav",
]


def fetch_bse_announcements(company, days_back=1):
    today = datetime.now()
    from_date = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    to_date = today.strftime("%Y%m%d")

    params = {
        "strCat": "-1",
        "strPrevDate": from_date,
        "strScrip": company["bse"],
        "strSearch": "P",
        "strToDate": to_date,
        "strType": "C",
        "subcategory": "-1",
    }

    try:
        response = requests.get(BSE_API_URL, params=params, headers=HEADERS, timeout=10)
        data = response.json()
        announcements = data.get("Table", [])
    except Exception:
        return []

    items = []
    for ann in announcements[:10]:
        headline = strip_html(ann.get("HEADLINE", "")).strip()
        if not headline or len(headline) > 400:
            continue

        # Skip irrelevant or analyst call announcements
        headline_lower = headline.lower()
        if any(kw in headline_lower for kw in EXCLUDE_KEYWORDS):
            continue

        scrip = ann.get("SCRIP_CD", company["bse"])
        filename = ann.get("ATTACHMENTNAME", "")
        if filename:
            link = f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{filename}"
        else:
            link = f"https://www.bseindia.com/corporates/ann.html?scrip_cd={scrip}"

        items.append({
            "title": headline,
            "link": link,
            "source": "BSE",
        })

        if len(items) >= 3:
            break

    return items


def fetch_all_news(companies):
    results = {}
    for company in companies:
        results[company["name"]] = fetch_bse_announcements(company)
    return results
