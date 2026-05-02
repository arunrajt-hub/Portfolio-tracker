from dotenv import load_dotenv
load_dotenv()

from config import COMPANIES
from news_fetcher import fetch_all_news
from quarterly_results import fetch_all_quarterly_results
from youtube_fetcher import fetch_all_earnings_calls, fetch_all_trendlyne_calls
from price_fetcher import fetch_prices, format_price_table
from whatsapp_sender import send_in_chunks
from datetime import datetime


def build_price_message(prices):
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    lines = [
        f"💹 *PORTFOLIO PRICES*",
        f"_{now} IST_",
        "━━━━━━━━━━━━━━━━━━━━",
        format_price_table(prices),
    ]
    return "\n".join(lines)


def build_news_message(news):
    now = datetime.now().strftime("%d %b %Y")
    lines = [
        f"📰 *NEWS FEED — {now}*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    has_news = False
    for company_name, items in news.items():
        if not items:
            continue
        has_news = True
        lines.append(f"\n🏢 *{company_name}*")
        for item in items:
            lines.append(f"• {item['title']}")

    if not has_news:
        lines.append("\nNo new BSE announcements today.")

    return "\n".join(lines)


def build_quarterly_message(news, quarterly, earnings, trendlyne=None):
    now = datetime.now().strftime("%d %b %Y")
    lines = [
        f"📋 *QUARTERLY UPDATES — {now}*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    has_content = False

    # Deduplicate quarterly vs news
    shown_titles = {item["title"] for items in news.values() for item in items}
    filtered_quarterly = {
        co: [i for i in items if i["title"] not in shown_titles]
        for co, items in quarterly.items()
    }
    filtered_quarterly = {co: items for co, items in filtered_quarterly.items() if items}

    if filtered_quarterly:
        has_content = True
        lines.append("\n*Results & Board Meetings*")
        for company_name, items in filtered_quarterly.items():
            lines.append(f"\n🏢 *{company_name}*")
            for item in items:
                lines.append(f"• {item['title']}")

    if earnings:
        has_content = True
        lines.append("\n*Earnings Calls (YouTube)*")
        for company_name, video in earnings.items():
            lines.append(f"\n🏢 *{company_name}*")
            lines.append(f"• {video['title']}")
            lines.append(f"  {video['url']}")

    if trendlyne:
        has_content = True
        lines.append("\n*Trendlyne Earnings Transcripts*")
        for company_name, video in trendlyne.items():
            lines.append(f"\n🏢 *{company_name}*")
            lines.append(f"• {video['title']}")
            lines.append(f"  {video['url']}")

    if not has_content:
        lines.append("\nNo quarterly updates today.")

    return "\n".join(lines)


def main():
    print("Fetching market prices...")
    prices = fetch_prices()

    print("Fetching news...")
    news = fetch_all_news(COMPANIES)

    print("Fetching quarterly results...")
    quarterly = fetch_all_quarterly_results(COMPANIES)

    print("Fetching earnings calls...")
    earnings = fetch_all_earnings_calls(COMPANIES)

    print("Fetching Trendlyne earnings transcripts...")
    trendlyne = fetch_all_trendlyne_calls(COMPANIES)

    msg1 = build_price_message(prices)
    msg2 = build_news_message(news)
    msg3 = build_quarterly_message(news, quarterly, earnings, trendlyne)

    print("\n--- Sending 3 messages ---")
    send_in_chunks(msg1)
    send_in_chunks(msg2)
    send_in_chunks(msg3)
    print("Done.")


if __name__ == "__main__":
    main()
