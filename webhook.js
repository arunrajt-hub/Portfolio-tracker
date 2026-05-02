// Cloudflare Worker — WhatsApp command handler
// Env vars to set in Cloudflare dashboard:
//   WHAPI_TOKEN, WHAPI_URL, WHATSAPP_NUMBER,
//   GITHUB_TOKEN, GITHUB_REPO (e.g. "username/portfolio-news-tracker"), WEBHOOK_SECRET

const WATCHLIST_PATH = "watchlist.json";

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("OK", { status: 200 });

    // Verify secret token to block unknown callers
    const secret = request.headers.get("X-Webhook-Secret");
    if (secret !== env.WEBHOOK_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

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

  // ADD <name> NSE:<ticker> BSE:<code>
  if (upper.startsWith("ADD ")) {
    const match = text.match(/^ADD\s+(.+?)\s+NSE:(\S+)\s+BSE:(\S+)$/i);
    if (!match) {
      return "❌ Format: ADD <name> NSE:<ticker> BSE:<code>\nExample: ADD Tata Motors NSE:TATAMOTORS BSE:500570";
    }
    const [, name, nse, bse] = match;
    const watchlist = await getWatchlist(env);
    const exists = watchlist.find((c) => c.nse.toUpperCase() === nse.toUpperCase());
    if (exists) return `⚠️ ${exists.name} is already in the watchlist.`;

    watchlist.push({ name: name.trim(), nse: nse.toUpperCase(), bse: bse.trim() });
    await saveWatchlist(watchlist, env, `Add ${name.trim()} to watchlist`);
    return `✅ Added *${name.trim()}* (NSE: ${nse.toUpperCase()}, BSE: ${bse}) to watchlist.`;
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
