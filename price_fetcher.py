import requests
import time
from config import COMPANIES

NSE_QUOTE_URL = "https://www.nseindia.com/api/quote-equity?symbol="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def get_nse_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get("https://www.nseindia.com", timeout=10)
    return session


def fetch_prices():
    try:
        session = get_nse_session()
    except Exception:
        return [{"name": c["name"], "price": None, "change_pct": None, "arrow": "-"} for c in COMPANIES]

    prices = []
    for company in COMPANIES:
        if not company.get("nse"):
            prices.append({"name": company["name"], "ticker": "N/A", "price": None, "change_pct": None, "arrow": "-"})
            continue
        try:
            url = f"{NSE_QUOTE_URL}{company['nse']}"
            resp = session.get(url, timeout=10)
            data = resp.json()
            price_data = data["priceInfo"]
            latest = float(price_data["lastPrice"])
            prev = float(price_data["previousClose"])
            change_pct = ((latest - prev) / prev) * 100
            arrow = "▲" if change_pct >= 0 else "▼"
            prices.append({
                "name": company["name"],
                "ticker": company["nse"],
                "price": latest,
                "change_pct": change_pct,
                "arrow": arrow,
            })
        except Exception:
            prices.append({
                "name": company["name"],
                "ticker": company["nse"],
                "price": None,
                "change_pct": None,
                "arrow": "-",
            })
        time.sleep(0.5)

    return prices


def format_price_table(prices):
    lines = []
    sorted_prices = sorted(prices, key=lambda x: x["change_pct"] if x["change_pct"] is not None else float('-inf'), reverse=True)
    for p in sorted_prices:
        if p["price"] is not None:
            emoji = "📈" if p["change_pct"] >= 0 else "📉"
            sign = "+" if p["change_pct"] >= 0 else "-"
            lines.append(f"{emoji} *{p['ticker']}*: ₹{p['price']:,.0f}  ({sign}{abs(p['change_pct']):.1f}%)")
        elif p["ticker"] != "N/A":
            lines.append(f"⬜ *{p['ticker']}*: N/A")
    return "\n".join(lines)
