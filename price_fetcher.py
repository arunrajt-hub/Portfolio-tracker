import yfinance as yf
from config import COMPANIES


def fetch_prices():
    prices = []
    for company in COMPANIES:
        if not company.get("nse"):
            prices.append({"name": company["name"], "ticker": "N/A", "price": None, "change_pct": None})
            continue
        try:
            ticker = yf.Ticker(f"{company['nse']}.NS")
            info = ticker.fast_info
            latest = info.last_price
            prev = info.previous_close
            if latest is None or prev is None:
                raise ValueError("No price data")
            change_pct = ((latest - prev) / prev) * 100
            prices.append({
                "name": company["name"],
                "ticker": company["nse"],
                "price": latest,
                "change_pct": change_pct,
            })
        except Exception:
            prices.append({
                "name": company["name"],
                "ticker": company["nse"],
                "price": None,
                "change_pct": None,
            })

    return prices


def format_price_table(prices):
    lines = []
    sorted_prices = sorted(
        prices,
        key=lambda x: x["change_pct"] if x["change_pct"] is not None else float("-inf"),
        reverse=True,
    )
    for p in sorted_prices:
        if p["price"] is not None:
            emoji = "📈" if p["change_pct"] >= 0 else "📉"
            sign = "+" if p["change_pct"] >= 0 else ""
            lines.append(f"{emoji} *{p['ticker']}*: ₹{p['price']:,.0f}  ({sign}{p['change_pct']:.1f}%)")
        elif p["ticker"] != "N/A":
            lines.append(f"⬜ *{p['ticker']}*: N/A")
    return "\n".join(lines)
