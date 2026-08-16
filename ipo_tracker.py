import json
import os
import re
import requests
from datetime import datetime

BSE_IPO_URL = "https://api.bseindia.com/BseIndiaAPI/api/MoreCompanyN/w"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json",
}

TRACK_MONTHS = 8
DROP_PCT_TRIGGER = 40  # flag when current price has fallen this much (or more) from listing-day close
FALL_THRESHOLD_PCT = 100 - DROP_PCT_TRIGGER  # equivalent "current <= X% of day-1 close" form used in the price check below

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-5"
MAX_IPO_VIEW_SEARCHES = 15  # shared across the whole batch, not per-stock — cost bound


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


def _build_ipo_view_prompt(fallen):
    items = [
        {
            "company": f["company"], "symbol": f["symbol"], "listed_on": f["listed_on"],
            "issue_price": f["issue_price"], "day1_close": f["day1_close"],
            "current_price": f["current_price"],
        }
        for f in fallen
    ]
    return (
        "You are assessing recently-listed Indian stocks that have fallen sharply "
        "since their first trading day. For each one below, use web search to "
        "understand why it fell — a company-specific problem (weak results, "
        "governance issue, promoter pledge, regulatory action) vs sector-wide or "
        "broad-market weakness that dragged it down along with peers — and check "
        "whether the underlying business fundamentals still look intact. Weigh "
        "that against the current price as a potential entry point.\n\n"
        f"{json.dumps(items, indent=2)}\n\n"
        "Reply with ONLY a JSON array (no markdown fences, no commentary outside "
        "the array), one object per stock, with exactly these keys: \"company\", "
        "\"symbol\", \"view\" (one of \"Buy\", \"Avoid\", \"Watch\"), "
        "\"view_reasoning\" (<=25 words, specific and evidence-based — cite what "
        "you actually found, e.g. \"Weak Q1 margins, no sector-wide fall\" or "
        "\"Fell with broader small-cap correction, no company-specific issue "
        "found\"). If search turns up nothing meaningful for a stock, use "
        "\"Watch\" with reasoning \"Insufficient information found\" rather than "
        "guessing. This is an AI-generated personal-reference read, not "
        "certified financial advice — be honest about uncertainty."
    )


def enrich_fallen_ipos(fallen):
    if not fallen:
        return []
    if not ANTHROPIC_API_KEY:
        return [{**f, "view": None, "view_reasoning": None} for f in fallen]

    prompt = _build_ipo_view_prompt(fallen)

    try:
        response = requests.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 3000,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [
                    {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_IPO_VIEW_SEARCHES},
                ],
            },
            timeout=150,
        )
        response.raise_for_status()
        # Web search interleaves search-result blocks between text blocks, so
        # the final JSON array can land anywhere in content, not just index 0.
        text_blocks = [b.get("text", "") for b in response.json().get("content", []) if b.get("type") == "text"]
        full_text = "\n".join(text_blocks).strip()
        full_text = re.sub(r"^```(json)?|```$", "", full_text, flags=re.MULTILINE).strip()
        try:
            views = json.loads(full_text)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", full_text, re.DOTALL)
            if not match:
                raise
            views = json.loads(match.group(0))
    except Exception as e:
        print(f"  [ipo_tracker] view enrichment failed, shipping without recommendations: {e}")
        return [{**f, "view": None, "view_reasoning": None} for f in fallen]

    by_symbol = {f["symbol"]: f for f in fallen}
    results = []
    returned_symbols = set()
    for item in views:
        symbol = item.get("symbol")
        base = by_symbol.get(symbol)
        if not base:
            continue
        returned_symbols.add(symbol)
        results.append({
            **base,
            "view": item.get("view"),
            "view_reasoning": item.get("view_reasoning"),
        })

    # Never silently drop a stock just because the model's reply skipped it.
    for f in fallen:
        if f["symbol"] not in returned_symbols:
            results.append({**f, "view": None, "view_reasoning": None})

    return results
