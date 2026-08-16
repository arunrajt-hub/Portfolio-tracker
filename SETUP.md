# Setup Guide

## 1. Push to GitHub

Create a new GitHub repo and push this folder to it.

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/portfolio-news-tracker.git
git push -u origin main
```

## 2. Add GitHub Actions Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret

| Secret | Value |
|---|---|
| `WHAPI_TOKEN` | Your WHAPI bearer token |
| `WHAPI_URL` | e.g. `https://gate.whapi.cloud` |
| `WHATSAPP_NUMBER` | e.g. `919500055366` |
| `ANTHROPIC_API_KEY` | Your Anthropic API key — powers the special-situations summary/impact enrichment (`special_situations.py`). Optional: without it, that message still sends but with raw headlines and no impact/risk lines. |

The tracker will now run automatically every day at 8:00 PM IST.
You can also trigger it manually from Actions → Portfolio News Tracker → Run workflow.

## 3. Deploy Cloudflare Worker

### One-time setup
1. Sign up at https://workers.cloudflare.com (free)
2. Install Wrangler CLI: `npm install -g wrangler`
3. Login: `wrangler login`

### Deploy
```bash
wrangler deploy webhook.js --name portfolio-webhook --compatibility-date 2024-01-01
```

Your worker URL will be: `https://portfolio-webhook.YOUR_SUBDOMAIN.workers.dev`

### Set Worker environment variables
In Cloudflare Dashboard → Workers → portfolio-webhook → Settings → Variables:

| Variable | Value |
|---|---|
| `WHAPI_TOKEN` | Your WHAPI bearer token |
| `WHAPI_URL` | e.g. `https://gate.whapi.cloud` |
| `WHATSAPP_NUMBER` | e.g. `919500055366` |
| `GITHUB_TOKEN` | GitHub Personal Access Token (with `repo` scope) |
| `GITHUB_REPO` | e.g. `yourusername/portfolio-news-tracker` |
| `WEBHOOK_SECRET` | Any random string, e.g. `mysecret123` |

### Create GitHub Personal Access Token
Go to GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
- Repository access: your portfolio repo
- Permissions: Contents → Read and Write

## 4. Configure WHAPI Webhook

In your WHAPI dashboard:
- Webhook URL: `https://portfolio-webhook.YOUR_SUBDOMAIN.workers.dev`
- Add header: `X-Webhook-Secret: <your WEBHOOK_SECRET>`
- Enable: incoming messages

## 5. WhatsApp Commands

Send these messages from your WhatsApp number:

```
LIST
ADD Tata Motors NSE:TATAMOTORS BSE:500570
REMOVE Tata Motors
REMOVE TATAMOTORS
```

## 6. Dashboard (Cloudflare Pages + Access)

Every run writes `docs/data/<date>.json` + `docs/data/index.json` and the
workflow commits/pushes them automatically — the dashboard at `docs/index.html`
reads those files client-side (no backend, no database).

### One-time setup
1. Cloudflare Dashboard → **Workers & Pages** → **Create application** → **Pages**
   → **Connect to Git** → select this repo (`Portfolio-tracker`).
2. Build settings: **Build command** = *(leave empty)*, **Build output directory**
   = `docs`. Deploy.
3. You'll get a URL like `https://portfolio-tracker.pages.dev` — it redeploys
   automatically every time the daily job pushes new data.

### Password-gate it (Cloudflare Access)
1. Cloudflare Dashboard → **Zero Trust** → **Access** → **Applications** →
   **Add an application** → **Self-hosted**.
2. Application domain: your `*.pages.dev` URL from above.
3. Add a policy: **Action** = Allow, **Include** = *Emails* → your email address.
4. Save. Now visiting the dashboard prompts for a one-time PIN sent to your
   email — nobody else can view it even if the URL leaks.

### Enable "Ask Claude" chat on findings
Each row has a **💬 Ask Claude** button that opens a chat scoped to that one
finding. It's powered by `functions/api/chat.js`, a Cloudflare Pages Function
that holds the Anthropic key server-side — it's never sent to the browser.

1. Cloudflare Dashboard → your Pages project → **Settings** → **Environment
   variables** → add `ANTHROPIC_API_KEY` (same value as the GitHub Actions
   secret — Cloudflare Pages can't read GitHub's secrets, so it needs adding
   here too).
2. Redeploy (or just wait for the next automatic redeploy) for the variable
   to take effect.
3. Without this set, the chat button still works but replies with a
   configuration error instead of an answer.
