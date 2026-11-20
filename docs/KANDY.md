# Second business: Google Analytics MCP for Kandy Selection

Kandy (kandyselection.lk) gets its **own** Cloud Run service from this same code, with its
own service account and its own secret. The Iranama connector never sees Kandy's data,
and the other way round.

| | Iranama (existing) | Kandy (new) |
|---|---|---|
| Cloud Run service | `ga-mcp` | `kandy-ga-mcp` |
| Service account | `ga-mcp@…` | `kandy-ga-mcp@…` |
| Secret | `ga-mcp-secret` | `kandy-ga-mcp-secret` |
| GA4 access | Iranama property only | Kandy property only |

There's no code change. You run the deploy script again with different names.

## 1. Find Kandy's GA4 property ID

1. Open <https://analytics.google.com> and switch to the Kandy property (top-left picker).
   The site sends data with the measurement ID in `NEXT_PUBLIC_GA_ID` (`G-…`).
2. **Admin** → **Property details**. Copy the **Property ID** (digits only, e.g.
   `412345678`). This is a different number from the `G-…` measurement ID.

If you can't see the property, ask whoever owns the Kandy GA account to make you an
**Administrator** on that property first.

## 2. Deploy the Kandy service

Use the same Google Cloud project as Iranama (simplest), or a separate one. In Cloud Shell:

```bash
cd ga-mcp && git pull
```

```bash
PROJECT_ID=iranama-analytics-123456 SERVICE=kandy-ga-mcp SA_NAME=kandy-ga-mcp SECRET_NAME=kandy-ga-mcp-secret ./scripts/deploy.sh
```

Replace the project ID with yours. Answer **y** to "Allow unauthenticated invocations?".
At the end it prints the **service URL** and `kandy-ga-mcp@<project>.iam.gserviceaccount.com`.

## 3. Give the Kandy service account read access

1. GA4 → Kandy property → **Admin** → **Property access management** → **+** → **Add users**.
2. Email: `kandy-ga-mcp@<project>.iam.gserviceaccount.com`.
3. Untick "Notify new users by email". Role: **Viewer**. **Add**.

Add it on the **Kandy property only**. Don't add the Iranama service account here.

## 4. Get the secret and test

```bash
gcloud secrets versions access latest --secret=kandy-ga-mcp-secret; echo
```

```bash
curl -s https://KANDY_URL/healthz
```

```bash
curl -s -X POST "https://KANDY_URL/mcp?key=SECRET" -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_account_summaries","arguments":{}}}'
```

The second call should list only the Kandy property. Access can take a few minutes to apply.

## 5. Connect it to Claude

Claude → **Settings** → **Connectors** → **Add custom connector**:

- Name: `Google Analytics (Kandy)`
- URL: `https://<kandy-service-url>/mcp?key=<kandy secret>`

**Claude Code:**

```bash
claude mcp add --transport http kandy-ga4 "https://<kandy-service-url>/mcp?key=<kandy secret>"
```

## 6. Make the GA data useful

GA4 → Kandy property:

1. The Kandy site currently sends page views only (gtag in `app/(site)/layout.js`), no
   `purchase` / `add_to_cart` events. GA reports traffic, landing pages and sources, but
   not revenue. Revenue comes from the Kandy platform MCP until ecommerce events are added.
2. **Admin** → **Data retention** → **14 months**.
3. **Admin** → **Product links**: link Google Ads and Search Console if you use them.

## Day two

Same as Iranama ([SETUP.md section K](SETUP.md#k-day-two-tasks)), with the Kandy names:

```bash
openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add kandy-ga-mcp-secret --data-file=-
```

```bash
gcloud run services update kandy-ga-mcp --region asia-south1 --set-secrets MCP_SECRET=kandy-ga-mcp-secret:latest
```

To update both services after `git pull`, run the deploy command for each.
