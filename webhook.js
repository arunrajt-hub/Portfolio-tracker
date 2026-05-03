// Cloudflare Worker — WhatsApp command handler
// Env vars to set in Cloudflare dashboard:
//   WHAPI_TOKEN, WHAPI_URL, WHATSAPP_NUMBER,
//   GITHUB_TOKEN, GITHUB_REPO (e.g. "username/portfolio-news-tracker"), WEBHOOK_SECRET

const WATCHLIST_PATH = "watchlist.json";

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("OK", { status: 200 });

    let body;
    try {
      body = await request.json();
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    const message = body?.messages?.[0];
    if (!message || message.type !== "text") return new Response("OK");

    const from = message.from?.replace(/[^0-9]/g, "");
    const allowed = env.WHATSAPP_NUMBER.replace(/[^0-9]/g, "");
    if (!from.endsWith(allowed) && !allowed.endsWith(from)) {
      return new Response("OK"); // ignore messages from other numbers
    }

    const text = (message.text?.body || "").trim();
    const reply = await handleCommand(text, env);
    await sendWhatsApp(reply, env);

    return new Response("OK");
  },
};

async function handleCommand(text, env) {
  const upper = text.toUpperCase();

  if (upper === "LIST") {
    const watchlist = await getWatchlist(env);
    if (!watchlist.length) return "📋 Watchlist is empty.";
    const lines = watchlist.map((c, i) => `${i + 1}. ${c.name} (NSE: ${c.nse}, BSE: ${c.bse})`);
    return `📋 *Watchlist (${watchlist.length} stocks)*\n\n${lines.join("\n")}`;
  }

  // ADD BSE:<code> [NSE:<ticker>]
  if (upper.startsWith("ADD ")) {
    const bseMatch = text.match(/BSE:(\d+)/i);
    if (!bseMatch) {
      return "❌ Format: ADD BSE:<code> [NSE:<ticker>]\nExample: ADD BSE:500570\nExample: ADD BSE:500570 NSE:TATAMOTORS";
    }
    const bse = bseMatch[1];
    const nseMatch = text.match(/NSE:(\S+)/i);
    const nse = nseMatch ? nseMatch[1].toUpperCase() : "";

    const watchlist = await getWatchlist(env);
    if (watchlist.find((c) => c.bse === bse)) {
      return `⚠️ BSE:${bse} is already in the watchlist.`;
    }

    // Auto-fetch company name from BSE
    let name = `BSE:${bse}`;
    try {
      const resp = await fetch(
        `https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?Debtflag=&scripcode=${bse}&seriesid=`,
        { headers: { "User-Agent": "Mozilla/5.0", "Referer": "https://www.bseindia.com/" } }
      );
      const data = await resp.json();
      name = data?.Cmpname?.SeriesN || data?.Cmpname?.FullN || name;
    } catch {}

    watchlist.push({ name: name.trim(), nse, bse });
    await saveWatchlist(watchlist, env, `Add ${name.trim()} to watchlist`);
    const nseNote = nse ? `, NSE: ${nse}` : " (no NSE ticker — prices won't show)";
    return `✅ Added *${name.trim()}* (BSE: ${bse}${nseNote})`;
  }

  // REMOVE <name or ticker>
  if (upper.startsWith("REMOVE ")) {
    const query = text.slice(7).trim().toUpperCase();
    const watchlist = await getWatchlist(env);
    const index = watchlist.findIndex(
      (c) => c.nse.toUpperCase() === query || c.name.toUpperCase() === query
    );
    if (index === -1) return `❌ "${text.slice(7).trim()}" not found in watchlist.`;
    const removed = watchlist.splice(index, 1)[0];
    await saveWatchlist(watchlist, env, `Remove ${removed.name} from watchlist`);
    return `✅ Removed *${removed.name}* from watchlist.`;
  }

  return `🤖 *Commands:*\n• LIST\n• ADD <name> NSE:<ticker> BSE:<code>\n• REMOVE <name or ticker>`;
}

async function getWatchlist(env) {
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}/contents/${WATCHLIST_PATH}`;
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "portfolio-tracker-worker",
    },
  });
  const data = await res.json();
  const content = atob(data.content.replace(/\n/g, ""));
  return JSON.parse(content);
}

async function saveWatchlist(watchlist, env, message) {
  // Get current SHA (required for update)
  const url = `https://api.github.com/repos/${env.GITHUB_REPO}/contents/${WATCHLIST_PATH}`;
  const current = await fetch(url, {
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "portfolio-tracker-worker",
    },
  });
  const { sha } = await current.json();

  const content = btoa(JSON.stringify(watchlist, null, 2) + "\n");
  await fetch(url, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "portfolio-tracker-worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message, content, sha }),
  });
}

async function sendWhatsApp(text, env) {
  await fetch(`${env.WHAPI_URL}/messages/text`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.WHAPI_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ to: env.WHATSAPP_NUMBER, body: text }),
  });
}
