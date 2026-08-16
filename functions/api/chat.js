// Cloudflare Pages Function — POST /api/chat
// Proxies chat about a single dashboard finding to Claude. The Anthropic key
// lives only in this server-side env var (Cloudflare Pages project settings),
// never sent to the browser. Scoped intentionally to one finding at a time —
// keeps context small/cheap and answers focused. Web search is enabled so
// Claude can pull current info about the company/action instead of being
// limited to just the finding's own JSON.

const MODEL = "claude-haiku-4-5-20251001";
const MAX_HISTORY_TURNS = 12;
const MAX_WEB_SEARCHES_PER_TURN = 5;

export async function onRequestPost(context) {
  const { request, env } = context;

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid JSON body" }, 400);
  }

  const { finding, question, history } = body || {};
  if (!finding || typeof question !== "string" || !question.trim()) {
    return json({ error: "Missing 'finding' or 'question'" }, 400);
  }

  const apiKey = env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return json({ error: "ANTHROPIC_API_KEY is not configured on this Pages project" }, 500);
  }

  const systemPrompt =
    "You are helping a retail investor understand one flagged item from their " +
    "personal portfolio-tracking dashboard (Indian equities, BSE-sourced data). " +
    "The finding below is your starting context — use web search freely to pull " +
    "current information about the company, the specific action, and how similar " +
    "actions have historically affected share price/business fundamentals, so you " +
    "can give a grounded view on likely impact, not just restate the filing. Cite " +
    "what you find. If web search doesn't turn up enough to answer confidently, " +
    "say so rather than guessing.\n\n" +
    "Finding:\n" + JSON.stringify(finding, null, 2);

  const trimmedHistory = Array.isArray(history) ? history.slice(-MAX_HISTORY_TURNS) : [];
  const messages = [
    ...trimmedHistory
      .filter(h => h && (h.role === "user" || h.role === "assistant") && typeof h.content === "string")
      .map(h => ({ role: h.role, content: h.content })),
    { role: "user", content: question },
  ];

  let anthropicRes;
  try {
    anthropicRes = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 1536,
        system: systemPrompt,
        messages,
        tools: [
          { type: "web_search_20250305", name: "web_search", max_uses: MAX_WEB_SEARCHES_PER_TURN },
        ],
      }),
    });
  } catch (e) {
    return json({ error: `Could not reach Anthropic API: ${e.message}` }, 502);
  }

  if (!anthropicRes.ok) {
    const errText = await anthropicRes.text();
    return json({ error: `Anthropic API error (${anthropicRes.status}): ${errText}` }, 502);
  }

  const data = await anthropicRes.json();
  // With web search, content interleaves text blocks with server_tool_use /
  // web_search_tool_result blocks — concatenate every text block in order,
  // not just the first, or multi-search answers get truncated to the intro.
  const reply = (data.content || [])
    .filter(b => b.type === "text")
    .map(b => b.text)
    .join("\n\n") || "";

  return json({ reply });
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json" },
  });
}
