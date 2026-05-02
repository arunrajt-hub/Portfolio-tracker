import requests
from datetime import datetime, timedelta

BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json",
}

RESULT_KEYWORDS = [
    "financial results", "quarterly results", "q1", "q2", "q3", "q4",
    "unaudited results", "audited results", "standalone", "consolidated results",
    "half year", "annual results"
]


def fetch_bse_results(company, days_back=1):
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
    for ann in announcements:
        headline = ann.get("HEADLINE", "").strip()
        if not headline:
            continue

        if not any(kw in headline.lower() for kw in RESULT_KEYWORDS):
            continue

        filename = ann.get("ATTACHMENTNAME", "")
        scrip = ann.get("SCRIP_CD", company["bse"])
        if filename:
            link = f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{filename}"
        else:
            link = f"https://www.bseindia.com/corporates/ann.html?scrip_cd={scrip}"

        items.append({
            "title": headline,
            "link": link,
            "source": "BSE",
        })

    return items


def fetch_all_quarterly_results(companies):
    results = {}
    for company in companies:
        items = fetch_bse_results(company)
        if items:
            results[company["name"]] = items
    return results
