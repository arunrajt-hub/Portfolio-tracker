from dotenv import load_dotenv
load_dotenv()

import os
from special_situations import fetch_all_special_situations
from ipo_tracker import find_fallen_ipos, enrich_fallen_ipos, TRACK_MONTHS, DROP_PCT_TRIGGER
from archive import write_daily_record
from email_sender import send_email
from datetime import datetime


VIEW_EMOJI = {"Buy": "✅", "Avoid": "🚫", "Watch": "👀"}


def build_special_situations_message(situations):
    now = datetime.now().strftime("%d %b %Y")
    lines = [
        f"🎯 *SPECIAL SITUATIONS — {now}*",
        "_Market-wide, not limited to your watchlist_",
        "_Buy/Avoid/Watch views are AI-generated for personal reference, not certified financial advice_",
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
            subcat = f" _({s['subcategory']})_" if s.get("subcategory") else ""
            lines.append(f"\n🏢 *{s['company']}*{subcat}")
            lines.append(f"• {s.get('summary') or s['headline']}")
            if s.get("impact"):
                lines.append(f"  💰 {s['impact']}")
            if s.get("risk"):
                lines.append(f"  ⚠️ {s['risk']}")
            if s.get("view"):
                emoji = VIEW_EMOJI.get(s["view"], "")
                lines.append(f"  {emoji} *{s['view']}* — {s.get('view_reasoning', '')}")
            lines.append(f"  {s['link']}")

    return "\n".join(lines)


def build_fallen_ipos_message(fallen):
    now = datetime.now().strftime("%d %b %Y")
    lines = [
        f"📉 *FALLEN IPOs — {now}*",
        f"_Listed within {TRACK_MONTHS} months, now down {DROP_PCT_TRIGGER}%+ from day-1 close_",
        "_Buy/Avoid/Watch views are AI-generated for personal reference, not certified financial advice_",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if not fallen:
        lines.append(f"\nNo recent IPO has fallen {DROP_PCT_TRIGGER}% or more from its listing-day close.")
        return "\n".join(lines)

    for f in fallen:
        drop_pct_day1 = 100 - f["pct_of_day1"]
        lines.append(f"\n🏢 *{f['company']}* ({f['symbol']})")
        lines.append(f"• Listed {f['listed_on']} at issue price ₹{f['issue_price']:,.2f}")
        lines.append(f"• Day-1 close ₹{f['day1_close']:,.2f} → now ₹{f['current_price']:,.2f} ({drop_pct_day1:.0f}% below day-1 close)")
        if f.get("pct_of_issue") is not None:
            drop_pct_issue = 100 - f["pct_of_issue"]
            lines.append(f"• {drop_pct_issue:.0f}% below issue price")
        if f.get("view"):
            emoji = VIEW_EMOJI.get(f["view"], "")
            lines.append(f"• {emoji} *{f['view']}* — {f.get('view_reasoning', '')}")

    return "\n".join(lines)


def main():
    days_back = int(os.environ.get("SPECIAL_SITUATIONS_DAYS_BACK", "2"))
    max_enrich = int(os.environ.get("SPECIAL_SITUATIONS_MAX_ENRICH", "10"))
    print(f"Scanning market-wide special situations (last {days_back} day(s), enriching up to {max_enrich})...")
    situations = fetch_all_special_situations(days_back=days_back, max_enrich=max_enrich)

    print("Checking recent IPOs for post-listing crashes...")
    fallen_ipos = find_fallen_ipos()
    fallen_ipos = enrich_fallen_ipos(fallen_ipos)

    write_daily_record(situations, fallen_ipos)

    msg1 = build_special_situations_message(situations)
    msg2 = build_fallen_ipos_message(fallen_ipos)

    today = datetime.now().strftime('%d %b %Y')

    print("\n--- Sending 2 emails ---")
    send_email(f"Special Situations — {today}", msg1)
    send_email(f"Fallen IPOs — {today}", msg2)
    print("Done.")


if __name__ == "__main__":
    main()
