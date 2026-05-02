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
| `YOUTUBE_API_KEY` | Your YouTube Data API v3 key |
| `WHAPI_TOKEN` | Your WHAPI bearer token |
| `WHAPI_URL` | e.g. `https://gate.whapi.cloud` |
| `WHATSAPP_NUMBER` | e.g. `919500055366` |

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
