"""Local simulator for WhatsApp webhook commands. Edits watchlist.json directly."""

import json
import os
import sys

WATCHLIST_PATH = os.path.join(os.path.dirname(__file__), "watchlist.json")


def load():
    with open(WATCHLIST_PATH) as f:
        return json.load(f)


def save(watchlist):
    with open(WATCHLIST_PATH, "w") as f:
        json.dump(watchlist, f, indent=2)
        f.write("\n")


def handle(text):
    upper = text.strip().upper()

    if upper == "LIST":
        watchlist = load()
        if not watchlist:
            return "📋 Watchlist is empty."
        lines = [f"{i+1}. {c['name']} (NSE: {c['nse']}, BSE: {c['bse']})" for i, c in enumerate(watchlist)]
        return f"📋 Watchlist ({len(watchlist)} stocks)\n\n" + "\n".join(lines)

    if upper.startswith("ADD "):
        import re
        match = re.match(r"^ADD\s+(.+?)\s+NSE:(\S+)\s+BSE:(\S+)$", text.strip(), re.IGNORECASE)
        if not match:
            return "❌ Format: ADD <name> NSE:<ticker> BSE:<code>\nExample: ADD Tata Motors NSE:TATAMOTORS BSE:500570"
        name, nse, bse = match.group(1), match.group(2).upper(), match.group(3)
        watchlist = load()
        if any(c["nse"].upper() == nse for c in watchlist):
            return f"⚠️  {nse} is already in the watchlist."
        watchlist.append({"name": name.strip(), "nse": nse, "bse": bse})
        save(watchlist)
        return f"✅ Added {name.strip()} (NSE: {nse}, BSE: {bse})"

    if upper.startswith("REMOVE "):
        query = text.strip()[7:].strip().upper()
        watchlist = load()
        index = next((i for i, c in enumerate(watchlist)
                      if c["nse"].upper() == query or c["name"].upper() == query), -1)
        if index == -1:
            return f"❌ \"{text.strip()[7:].strip()}\" not found in watchlist."
        removed = watchlist.pop(index)
        save(watchlist)
        return f"✅ Removed {removed['name']}"

    return "🤖 Commands: LIST | ADD <name> NSE:<ticker> BSE:<code> | REMOVE <name or ticker>"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        print(handle(cmd))
    else:
        print("Interactive mode (Ctrl+C to exit)\n")
        while True:
            try:
                cmd = input("WhatsApp> ").strip()
                if cmd:
                    print(handle(cmd))
                    print()
            except (KeyboardInterrupt, EOFError):
                print("\nBye.")
                break
