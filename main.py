from dotenv import load_dotenv
load_dotenv()

import os
from special_situations import fetch_all_special_situations
from ipo_tracker import find_fallen_ipos, TRACK_MONTHS, FALL_THRESHOLD_PCT
from archive import write_daily_record
from whatsapp_sender import send_in_chunks
from datetime import datetime


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
            subcat = f" _({s['subcategory']})_" if s.get("subcategory") else ""
            lines.append(f"\n🏢 *{s['company']}*{subcat}")
            lines.append(f"• {s.get('summary') or s['headline']}")
            if s.get("impact"):
                lines.append(f"  💰 {s['impact']}")
            if s.get("risk"):
                lines.append(f"  ⚠️ {s['risk']}")
            lines.append(f"  {s['link']}")

    return "\n".join(lines)


def build_fallen_ipos_message(fallen):
    now = datetime.now().strftime("%d %b %Y")
    lines = [
        f"📉 *FALLEN IPOs — {now}*",
        f"_Listed within {TRACK_MONTHS} months, now ≤{FALL_THRESHOLD_PCT}% of day-1 close_",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if not fallen:
        lines.append(f"\nNo recent IPO has fallen to {FALL_THRESHOLD_PCT}% or below its listing-day close.")
        return "\n".join(lines)

    for f in fallen:
        drop_pct = 100 - f["pct_of_day1"]
        lines.append(f"\n🏢 *{f['company']}* ({f['symbol']})")
        lines.append(f"• Listed {f['listed_on']} at issue price ₹{f['issue_price']:,.2f}")
        lines.append(f"• Day-1 close ₹{f['day1_close']:,.2f} → now ₹{f['current_price']:,.2f} ({drop_pct:.0f}% below day-1 close)")

    return "\n".join(lines)


def main():
    days_back = int(os.environ.get("SPECIAL_SITUATIONS_DAYS_BACK", "1"))
    print(f"Scanning market-wide special situations (last {days_back} day(s))...")
    situations = fetch_all_special_situations(days_back=days_back)

    print("Checking recent IPOs for post-listing crashes...")
    fallen_ipos = find_fallen_ipos()

    write_daily_record(situations, fallen_ipos)

    msg1 = build_special_situations_message(situations)
    msg2 = build_fallen_ipos_message(fallen_ipos)

    print("\n--- Sending 2 messages ---")
    send_in_chunks(msg1)
    send_in_chunks(msg2)
    print("Done.")


if __name__ == "__main__":
    main()
