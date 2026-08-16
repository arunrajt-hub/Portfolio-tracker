import json
import os
import re
import requests
from datetime import datetime, timedelta

from news_fetcher import EXCLUDE_KEYWORDS, strip_html

BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json",
}

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

# Event-type keyword buckets. Matched as whole phrases (word-boundary) against
# lowercased headlines. Short/ambiguous abbreviations (e.g. bare "COD", "EIR")
# are deliberately left out in favour of their full phrase to avoid false
# positives inside unrelated words.
CATEGORIES = {
    "Capacity & Capex": [
        "commercial operations date", "trial run completed",
        "commencement of commercial production", "debottlenecking",
        "phase-1 commissioned", "phase 1 commissioned",
        "environmental clearance",
    ],
    "Demerger, M&A & PE": [
        "composite scheme of arrangement", "scheme of arrangement",
        "record date for demerger", "slump sale", "nclt approval",
        "in-principle approval", "preferential allotment",
        "promoter warrant conversion", "merger", "amalgamation",
        "demerger", "acquisition", "stake sale", "open offer",
        "delisting", "buyback", "qip", "rights issue", "spin-off",
        "spin off",
    ],
    "Regulatory & Legal Cleansing": [
        "form 483", "establishment inspection report", "settlement order",
        "closure of inspection", "quashed by hc", "quashed by high court",
        "stay order granted", "regularization of export authorization",
    ],
    "Business Wins & Revenue Triggers": [
        "master services agreement", "exclusive manufacturing rights",
        "binding term sheet", "patent grant", "letter of award",
    ],
    "Red Flags & Governance": [
        "resignation of statutory auditor", "resignation of cfo",
        "forensic audit", "sebi show cause notice", "search and seizure",
        "invoking pledge", "invocation of pledge",
    ],
    "Distress / Insolvency": [
        "nclt", "insolvency", "resolution plan",
        "corporate insolvency resolution process", "cirp",
        "default in payment", "restructuring", "arbitration award",
        "litigation settlement",
    ],
}

_KEYWORD_PATTERNS = [
    (category, re.compile(r"\b" + re.escape(kw) + r"\b"))
    for category, keywords in CATEGORIES.items()
    for kw in keywords
]


def classify(headline):
    headline_lower = headline.lower()
    for category, pattern in _KEYWORD_PATTERNS:
        if pattern.search(headline_lower):
            return category
    return None


def fetch_market_announcements(days_back=1, max_pages=20):
    """Best-effort market-wide (no scrip filter) BSE announcement query.

    NOT verified live — BSE/exchange APIs appear to block dev-sandbox egress
    IPs outright (same class of issue this repo already hit with NSE price
    data). Verify strScrip/pagination against a real GitHub Actions run and
    adjust if the shape is wrong — the diagnostic prints below show whether
    zero results means "API blocked/wrong params" (0 raw announcements) vs
    "genuinely nothing matched" (raw count > 0, candidates == 0).
    """
    today = datetime.now()
    from_date = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    to_date = today.strftime("%Y%m%d")

    announcements = []
    for pageno in range(1, max_pages + 1):
        params = {
            "pageno": pageno,
            "strCat": "-1",
            "strPrevDate": from_date,
            "strScrip": "",
            "strSearch": "P",
            "strToDate": to_date,
            "strType": "C",
            "subcategory": "-1",
        }
        response = None
        try:
            response = requests.get(BSE_API_URL, params=params, headers=HEADERS, timeout=15)
            data = response.json()
            page_items = data.get("Table", [])
        except Exception as e:
            print(f"  [special_situations] page {pageno} request failed: {e}")
            if response is not None:
                print(f"  [special_situations] status={response.status_code} body[:300]={response.text[:300]!r}")
            break

        print(f"  [special_situations] page {pageno}: {len(page_items)} announcements")
        if not page_items:
            break
        announcements.extend(page_items)
        if len(page_items) < 50:
            break

    print(f"  [special_situations] total raw announcements fetched: {len(announcements)}")
    return announcements


def find_special_situations(days_back=1):
    announcements = fetch_market_announcements(days_back=days_back)

    seen = set()
    candidates = []
    for ann in announcements:
        headline = strip_html(ann.get("HEADLINE", "")).strip()
        if not headline or len(headline) > 400:
            continue

        headline_lower = headline.lower()
        if any(kw in headline_lower for kw in EXCLUDE_KEYWORDS):
            continue

        category = classify(headline)
        if not category:
            continue

        company = ann.get("SLONGNAME") or ann.get("SCRIP_CD", "Unknown")
        dedupe_key = (company, headline)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        scrip = ann.get("SCRIP_CD", "")
        filename = ann.get("ATTACHMENTNAME", "")
        if filename:
            link = f"https://www.bseindia.com/xml-data/corpfiling/AttachHis/{filename}"
        else:
            link = f"https://www.bseindia.com/corporates/ann.html?scrip_cd={scrip}"

        candidates.append({
            "company": company,
            "category": category,
            "headline": headline,
            "link": link,
        })

    print(f"  [special_situations] candidates after keyword filter: {len(candidates)}")
    return candidates


def _build_enrichment_prompt(candidates):
    items = [
        {"company": c["company"], "category": c["category"], "headline": c["headline"]}
        for c in candidates
    ]
    return (
        "You are screening Indian stock exchange corporate announcements for "
        "genuinely material special-situation events (capex/capacity triggers, "
        "M&A/demergers, regulatory or legal resolution, major business wins, "
        "governance red flags, distress/insolvency).\n\n"
        "Below is a JSON list of candidate announcements that already passed a "
        "keyword filter. Some may still be routine boilerplate — drop those.\n\n"
        f"{json.dumps(items, indent=2)}\n\n"
        "Reply with ONLY a JSON array (no markdown fences, no commentary), one "
        "object per announcement you judge to be genuinely material, each with "
        "exactly these keys: \"company\", \"category\", \"summary\" (<=15 words, "
        "the concrete action), \"impact\" (<=12 words on likely financial "
        "impact, or \"Not stated\" if the headline doesn't say), \"risk\" "
        "(<=12 words on the key risk/watch-item, or \"None apparent\"). Do not "
        "invent figures that aren't in the headline."
    )


def enrich_candidates(candidates, max_items=40):
    if not candidates:
        return []
    if not ANTHROPIC_API_KEY:
        return [{**c, "summary": None, "impact": None, "risk": None} for c in candidates]

    subset = candidates[:max_items]
    prompt = _build_enrichment_prompt(subset)

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
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        response.raise_for_status()
        text = response.json()["content"][0]["text"].strip()
        text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        enriched = json.loads(text)
    except Exception as e:
        print(f"LLM enrichment failed, falling back to raw headlines: {e}")
        return [{**c, "summary": None, "impact": None, "risk": None} for c in subset]

    by_key = {(c["company"], c["category"]): c for c in subset}
    results = []
    for item in enriched:
        key = (item.get("company"), item.get("category"))
        base = by_key.get(key)
        if not base:
            continue
        results.append({
            **base,
            "summary": item.get("summary"),
            "impact": item.get("impact"),
            "risk": item.get("risk"),
        })
    return results


def fetch_all_special_situations(days_back=1):
    candidates = find_special_situations(days_back=days_back)
    return enrich_candidates(candidates)
