from dotenv import load_dotenv
load_dotenv()

import os
from config import COMPANIES
from news_fetcher import fetch_all_news
from quarterly_results import fetch_all_quarterly_results
from special_situations import fetch_all_special_situations
from whatsapp_sender import send_in_chunks
from datetime import datetime


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


def build_quarterly_message(news, quarterly):
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

    if not has_content:
        lines.append("\nNo quarterly updates today.")

    return "\n".join(lines)


def build_special_situations_message(situations):
    now = datetime.now().strftime("%d %b %Y")
    lines = [
        f"🎯 *SPECIAL SITUATIONS — {now}*",
        "_Market-wide, not limited to your watchlist_",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if not situations:
        lines.append("\nNo special-situation events flagged today.")
        return "\n".join(lines)

    by_category = {}
    for s in situations:
        by_category.setdefault(s["category"], []).append(s)

    for category, items in by_category.items():
        lines.append(f"\n*{category}*")
        for s in items:
            lines.append(f"\n🏢 *{s['company']}*")
            lines.append(f"• {s.get('summary') or s['headline']}")
            if s.get("impact"):
                lines.append(f"  💰 {s['impact']}")
            if s.get("risk"):
                lines.append(f"  ⚠️ {s['risk']}")
            lines.append(f"  {s['link']}")

    return "\n".join(lines)


def main():
    print("Fetching news...")
    news = fetch_all_news(COMPANIES)

    print("Fetching quarterly results...")
    quarterly = fetch_all_quarterly_results(COMPANIES)

    days_back = int(os.environ.get("SPECIAL_SITUATIONS_DAYS_BACK", "1"))
    print(f"Scanning market-wide special situations (last {days_back} day(s))...")
    situations = fetch_all_special_situations(days_back=days_back)

    msg2 = build_news_message(news)
    msg3 = build_quarterly_message(news, quarterly)
    msg4 = build_special_situations_message(situations)

    print("\n--- Sending 3 messages ---")
    send_in_chunks(msg2)
    send_in_chunks(msg3)
    send_in_chunks(msg4)
    print("Done.")


if __name__ == "__main__":
    main()
