import requests
from datetime import datetime

BSE_IPO_URL = "https://api.bseindia.com/BseIndiaAPI/api/MoreCompanyN/w"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json",
}

TRACK_MONTHS = 7
FALL_THRESHOLD_PCT = 50  # flag when current price <= this % of listing-day close


def _months_ago(months):
    today = datetime.now()
    year, month = today.year, today.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(today.day, 28)
    return datetime(year, month, day)


def _fetch_year(year):
    try:
        response = requests.get(
            BSE_IPO_URL,
            params={"Fromdt": year, "company": "", "flag": 1, "type": 2},
            headers=HEADERS,
            timeout=15,
        )
        return response.json().get("Table", [])
    except Exception as e:
        print(f"  [ipo_tracker] fetch failed for year {year}: {e}")
        return []


def fetch_recent_ipos(months=TRACK_MONTHS):
    today = datetime.now()
    cutoff = _months_ago(months)

    rows = _fetch_year(today.year)
    if today.year != cutoff.year:
        rows += _fetch_year(cutoff.year)

    seen = set()
    recent = []
    for r in rows:
        listed_on_raw = r.get("ListedOn")
        if not listed_on_raw:
            continue
        try:
            listed_on = datetime.strptime(listed_on_raw[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if listed_on < cutoff:
            continue

        key = (r.get("Company_Short_Name"), listed_on_raw)
        if key in seen:
            continue
        seen.add(key)
        recent.append({**r, "_listed_on": listed_on})

    print(f"  [ipo_tracker] {len(recent)} IPOs listed in the last {months} months (of {len(rows)} fetched)")
    return recent


def find_fallen_ipos(months=TRACK_MONTHS, threshold_pct=FALL_THRESHOLD_PCT):
    recent = fetch_recent_ipos(months=months)

    fallen = []
    for r in recent:
        day1_close = r.get("ListingDayClose")
        current = r.get("CurrentPrice")
        if not day1_close or current is None:
            continue

        pct_of_day1 = (current / day1_close) * 100
        if pct_of_day1 > threshold_pct:
            continue

        issue_price = r.get("IssuePrice")
        pct_of_issue = (current / issue_price) * 100 if issue_price else None

        fallen.append({
            "company": r.get("CompanyName", "").strip(),
            "symbol": r.get("Company_Short_Name"),
            "listed_on": r["_listed_on"].strftime("%d %b %Y"),
            "issue_price": issue_price,
            "day1_close": day1_close,
            "current_price": current,
            "pct_of_day1": pct_of_day1,
            "pct_of_issue": pct_of_issue,
        })

    fallen.sort(key=lambda x: x["pct_of_day1"])
    print(f"  [ipo_tracker] {len(fallen)} IPO(s) at or below {threshold_pct}% of day-1 close")
    return fallen
