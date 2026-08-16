import json
import math
import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from news_fetcher import EXCLUDE_KEYWORDS, strip_html

BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json",
}

# strCat takes BSE's literal category name (confirmed live), not a numeric ID
# or "-1" — those silently return zero rows when strScrip is blank. Picked
# for special-situation relevance: Corp. Action (buybacks/splits/schemes),
# AGM/EGM (special resolutions), Insider Trading / SAST (open offers,
# pledges), Board Meeting, and Company Update (BSE's catch-all bucket, where
# most capex/regulatory/business-win headlines actually land). "Result" is
# deliberately excluded — routine quarterly results aren't a special situation.
MARKET_WIDE_CATEGORIES = [
    "Corp. Action",
    "AGM/EGM",
    "Insider Trading / SAST",
    "Board Meeting",
    "Company Update",
]
PAGE_SIZE = 50
MAX_PAGES_PER_CATEGORY = 100  # safety cap (5000 rows/category) for wide test pulls

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
# Sonnet, not Haiku — this pass now includes a Buy/Avoid/Watch call, which
# carries more real-world weight than a category label or summary and is
# worth the extra cost/latency for stronger reasoning.
ANTHROPIC_MODEL = "claude-sonnet-5"
MAX_ENRICHMENT_SEARCHES = 15  # shared across the whole batch, not per-candidate — cost bound

# Event-type keyword buckets. Matched as whole phrases (word-boundary) against
# lowercased headlines. Short/ambiguous abbreviations (e.g. bare "COD", "EIR")
# are deliberately left out in favour of their full phrase to avoid false
# positives inside unrelated words.
CATEGORIES = {
    "Capacity & Capex": [
        "commercial operations date", "trial run completed",
        "commencement of commercial production", "commercial production",
        "debottlenecking", "phase-1 commissioned", "phase 1 commissioned",
        "environmental clearance", "commissioned", "commissioning",
        "greenfield plant", "greenfield project", "brownfield expansion",
        "capacity expansion", "commercial operations",
    ],
    "Demerger, M&A & PE": [
        "composite scheme of arrangement", "scheme of arrangement",
        "record date for demerger", "slump sale", "nclt approval",
        "in-principle approval", "preferential allotment",
        "promoter warrant conversion", "merger", "amalgamation",
        "demerger", "acquisition", "stake sale", "open offer",
        "delisting", "buyback", "qip", "rights issue", "spin-off",
        "spin off", "reverse merger", "reverse listing", "backdoor listing",
        "amalgamation with unlisted", "amalgamation of unlisted",
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

# Refined 3-way split within "Demerger, M&A & PE", by which keyword matched —
# BSE's own SUBCATNAME for this bucket is often unhelpfully generic ("General",
# "Outcome of Board Meeting"), so this overrides it for this one category only.
# Ambiguous calls (open offer/delisting/NCLT approval -> M&A; in-principle
# approval -> PE/Fundraising) are judgment calls, adjust if they read wrong.
MANDA_SUBCLASS_BY_KEYWORD = {
    "composite scheme of arrangement": "Demerger",
    "scheme of arrangement": "Demerger",
    "record date for demerger": "Demerger",
    "demerger": "Demerger",
    "spin-off": "Demerger",
    "spin off": "Demerger",

    "merger": "M&A",
    "amalgamation": "M&A",
    "acquisition": "M&A",
    "stake sale": "M&A",
    "slump sale": "M&A",
    "reverse merger": "M&A",
    "reverse listing": "M&A",
    "backdoor listing": "M&A",
    "amalgamation with unlisted": "M&A",
    "amalgamation of unlisted": "M&A",
    "open offer": "M&A",
    "delisting": "M&A",
    "nclt approval": "M&A",

    "preferential allotment": "PE / Fundraising",
    "promoter warrant conversion": "PE / Fundraising",
    "qip": "PE / Fundraising",
    "rights issue": "PE / Fundraising",
    "buyback": "PE / Fundraising",
    "in-principle approval": "PE / Fundraising",
}

_KEYWORD_PATTERNS = [
    (category, kw, re.compile(r"\b" + re.escape(kw) + r"\b"))
    for category, keywords in CATEGORIES.items()
    for kw in keywords
]


def classify(headline):
    """Returns (category, matched_keyword) or (None, None)."""
    headline_lower = headline.lower()
    for category, keyword, pattern in _KEYWORD_PATTERNS:
        if pattern.search(headline_lower):
            return category, keyword
    return None, None


def _fetch_page(category, pageno, from_date, to_date):
    params = {
        "pageno": pageno,
        "strCat": category,
        "strPrevDate": from_date,
        "strScrip": "",
        "strSearch": "P",
        "strToDate": to_date,
        "strType": "C",
        "subcategory": "-1",
    }
    response = None
    try:
        response = requests.get(BSE_API_URL, params=params, headers=HEADERS, timeout=20)
        data = response.json()
        return data.get("Table", []), data.get("Table1", [{}])
    except Exception as e:
        print(f"  [special_situations] '{category}' page {pageno} request failed: {e}")
        if response is not None:
            print(f"  [special_situations] status={response.status_code} body[:300]={response.text[:300]!r}")
        return [], None


def fetch_market_announcements(days_back=1, max_workers=10):
    """Market-wide (no scrip filter) BSE announcement query, one call per
    relevant category — confirmed live: strCat must be the literal category
    name (e.g. "Corp. Action"), not "-1"/numeric, when strScrip is blank.

    Page 1 of each category reports the true row count (Table1[0].ROWCNT),
    so remaining pages are fetched concurrently instead of one-by-one —
    sequential pagination made "Company Update" alone (~70+ pages/day) take
    several minutes.
    """
    today = datetime.now()
    from_date = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    to_date = today.strftime("%Y%m%d")

    announcements = []
    remaining_page_tasks = []  # (category, pageno)

    for category in MARKET_WIDE_CATEGORIES:
        page1_items, table1 = _fetch_page(category, 1, from_date, to_date)
        announcements.extend(page1_items)
        if not page1_items:
            continue

        rowcnt = (table1[0].get("ROWCNT") if table1 else None) or len(page1_items)
        total_pages = min(math.ceil(rowcnt / PAGE_SIZE), MAX_PAGES_PER_CATEGORY)
        if total_pages > MAX_PAGES_PER_CATEGORY:
            print(f"  [special_situations] '{category}' hit the {MAX_PAGES_PER_CATEGORY}-page safety cap, more may exist")
        for pageno in range(2, total_pages + 1):
            remaining_page_tasks.append((category, pageno))

    if remaining_page_tasks:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_fetch_page, category, pageno, from_date, to_date): (category, pageno)
                for category, pageno in remaining_page_tasks
            }
            for future in as_completed(futures):
                page_items, _ = future.result()
                announcements.extend(page_items)

    for category in MARKET_WIDE_CATEGORIES:
        count = sum(1 for a in announcements if a.get("CATEGORYNAME") == category)
        print(f"  [special_situations] '{category}': {count} announcements")

    print(f"  [special_situations] total raw announcements fetched: {len(announcements)}")
    return announcements


# Routine periodic shareholding-disclosure filings (SAST Reg 29/31 etc.) use
# this boilerplate wrapper phrase regardless of stake size — they dominate
# volume without being genuinely material. Real open offers/takeovers use
# different headline templates ("Open Offer", "Public Announcement") and
# aren't caught by this.
BOILERPLATE_EXCLUDE = [
    "the exchange has received the disclosure under regulation",
    "the exchange has received the revised disclosure under regulation",
]


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
        if any(kw in headline_lower for kw in BOILERPLATE_EXCLUDE):
            continue

        category, keyword = classify(headline)
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

        if category == "Demerger, M&A & PE":
            subcategory = MANDA_SUBCLASS_BY_KEYWORD.get(keyword, "Other")
        else:
            subcategory = ann.get("SUBCATNAME") or ann.get("CATEGORYNAME") or "General"

        candidates.append({
            "company": company,
            "category": category,
            "subcategory": subcategory,
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
        "Reply with ONLY a JSON array (no markdown fences, no commentary outside "
        "the array), one object per announcement you judge to be genuinely "
        "material. EVERY object MUST include ALL SIX of these keys — never omit "
        "\"view\" or \"view_reasoning\" even if you're short on search budget; "
        "fall back to \"Watch\" / \"Not researched in depth\" rather than leaving "
        "them out: \"company\", \"category\", \"summary\" (<=15 words, the "
        "concrete action), \"impact\", \"risk\" (<=12 words on the key "
        "risk/watch-item, or \"None apparent\"), \"view\", \"view_reasoning\".\n\n"
        "For \"impact\": if the event involves a monetary figure (capex amount, "
        "deal size, fundraise amount, order/contract value, buyback size, etc.) "
        "and the headline doesn't state it, use web search to find it, then also "
        "search for the company's most recent full-year revenue and express "
        "impact as a percentage of that revenue, e.g. \"~8% of FY25 revenue "
        "(₹40 Cr order vs ₹500 Cr revenue)\". If the event type has no "
        "transaction size at all (governance, regulatory, distress announcements "
        "with no deal figure), give a brief qualitative impact note instead — "
        "don't force a percentage that doesn't apply. If search turns up nothing "
        "usable, say \"Not stated\" rather than guessing or inventing a figure.\n\n"
        "For \"view\": one of \"Buy\", \"Avoid\", or \"Watch\" — your read on "
        "whether this event makes the stock more or less attractive right now, "
        "weighing the event's materiality against what you can find about the "
        "company's current valuation/fundamentals via web search. Many events "
        "(e.g. a routine board meeting notice, an auditor resignation with no "
        "other red flags) genuinely have no clear directional signal — use "
        "\"Watch\" with reasoning \"No clear directional signal\" rather than "
        "forcing a Buy/Avoid call. \"view_reasoning\" is <=20 words, specific and "
        "evidence-based (cite what you found), not generic. This is an "
        "AI-generated personal-reference read, not certified financial advice — "
        "be honest about uncertainty rather than confidently guessing."
    )


def _unenriched(candidates):
    return [{**c, "summary": None, "impact": None, "risk": None, "view": None, "view_reasoning": None} for c in candidates]


def enrich_candidates(candidates, max_items=5):
    if not candidates:
        return []
    if not ANTHROPIC_API_KEY:
        return _unenriched(candidates)

    # Only the first max_items go through the LLM screen (cost bound). Anything
    # beyond that still ships in the digest, just unenriched — never silently
    # dropped just because the batch was large.
    subset = candidates[:max_items]
    overflow = candidates[max_items:]
    if overflow:
        print(f"  [special_situations] {len(overflow)} candidates beyond the LLM batch cap, sending unenriched")

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
                "max_tokens": 8000,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [
                    {"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_ENRICHMENT_SEARCHES},
                ],
            },
            timeout=180,
        )
        response.raise_for_status()
        data = response.json()
        # Web search interleaves search-result blocks between text blocks, so
        # the final JSON array can land anywhere in content, not just index 0 —
        # concatenate every text block, then pull the array out of the result.
        block_types = [b.get("type") for b in data.get("content", [])]
        text_blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        full_text = "\n".join(text_blocks).strip()
        full_text = re.sub(r"^```(json)?|```$", "", full_text, flags=re.MULTILINE).strip()
        if not full_text:
            print(f"  [special_situations] enrichment produced no text content — stop_reason={data.get('stop_reason')}, blocks={block_types}")
        try:
            enriched = json.loads(full_text)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", full_text, re.DOTALL)
            if not match:
                raise
            enriched = json.loads(match.group(0))
    except Exception as e:
        print(f"LLM enrichment failed, falling back to raw headlines: {e}")
        return _unenriched(subset) + _unenriched(overflow)

    by_key = {(c["company"], c["category"]): c for c in subset}
    matched_keys = set()
    results = []
    for item in enriched:
        key = (item.get("company"), item.get("category"))
        base = by_key.get(key)
        if not base:
            continue
        matched_keys.add(key)
        results.append({
            **base,
            "summary": item.get("summary"),
            "impact": item.get("impact"),
            "risk": item.get("risk"),
            # The model doesn't always include view/view_reasoning even when
            # told they're mandatory — default rather than leave blank for an
            # item it otherwise did process.
            "view": item.get("view") or "Watch",
            "view_reasoning": item.get("view_reasoning") or "Not determined by the model for this item",
        })

    # Anything in the batch the model didn't return (ran out of budget partway
    # through, or silently filtered it) still ships unenriched rather than
    # vanishing without a trace — same rule already applied to overflow.
    unmatched = [c for c in subset if (c["company"], c["category"]) not in matched_keys]
    if unmatched:
        print(f"  [special_situations] {len(unmatched)} candidates in the LLM batch weren't returned by the model, sending unenriched")

    return results + _unenriched(unmatched) + _unenriched(overflow)


def fetch_all_special_situations(days_back=1):
    candidates = find_special_situations(days_back=days_back)
    return enrich_candidates(candidates)
