# Google Analytics MCP: setup guide, A to Z

When you finish, Claude can read Iranama's Google Analytics 4 data (sessions, sources,
campaigns, landing pages, funnels, purchases) through a connector, the same way it uses
the Meta Ads MCP.

You need about 30–45 minutes. Everything runs in your browser. You don't need to install
anything on your computer.

**You need:**

- **Admin** on the Iranama GA4 property (to add a user)
- A Google account that can create a Google Cloud project with **billing** turned on.
  Cloud Run's free tier covers this server's normal use, but billing must be on.
- Your GitHub login (to clone the private `ga-mcp` repo)

---

## A. Find your GA4 property ID

1. Open <https://analytics.google.com> and choose the Iranama property.
2. Go to **Admin** (gear icon, bottom left) → **Property** → **Property details**.
3. Copy the **Property ID**, a number like `412345678`. You'll use it when asking Claude
   questions.

## B. Create (or choose) a Google Cloud project

1. Open <https://console.cloud.google.com>.
2. Top bar → project picker → **New project**. Name it `iranama-analytics` (any name
   works). Click **Create** and switch to it.
3. Note the **Project ID** shown under the name (for example `iranama-analytics-123456`).
   It's not always the same as the name.
4. Go to **Billing** → link a billing account to this project.

## C. Open Cloud Shell and get the code

1. In the Cloud Console, click the **Activate Cloud Shell** icon (`>_`, top right). A
   terminal opens at the bottom, already logged in to your Google account.
2. Create a GitHub token for the private repo:
   1. On GitHub: **Settings** → **Developer settings** → **Personal access tokens** →
      **Fine-grained tokens** → **Generate new token**.
   2. Repository access: **Only select repositories** → `matheesha-bpo/ga-mcp`.
   3. Permissions: **Contents: Read-only**. Generate it and copy the token.
3. In Cloud Shell, clone the repo. Paste the token when asked for a password:

   ```bash
   git clone https://github.com/matheesha-bpo/ga-mcp.git
   ```

   ```bash
   cd ga-mcp
   ```

## D. Deploy

Run this, replacing the value with your **Project ID** from step B:

```bash
PROJECT_ID=iranama-analytics-123456 ./scripts/deploy.sh
```

The script:

1. Enables the Cloud Run, Cloud Build, Artifact Registry, Secret Manager, GA Data and GA
   Admin APIs.
2. Creates the service account `ga-mcp@<project>.iam.gserviceaccount.com`. No key file is
   ever created.
3. Generates a random 64-character secret and stores it in Secret Manager as
   `ga-mcp-secret`.
4. Builds the container and deploys it to Cloud Run in `asia-south1` (Mumbai, closest to
   Sri Lanka). It scales to zero when unused.

The first run can ask *"Allow unauthenticated invocations?"*: answer **y**. Cloud Run
itself stays open so Claude can reach it, and the gateway refuses every request without
the secret. This is the same model as the Meta Ads MCP on Vercel.

At the end it prints the **service URL** and the **service account email**. Keep both.
If something fails, see [Troubleshooting](#j-troubleshooting).

## E. Give the service account read access to GA4

1. GA4 → **Admin** → **Property** → **Property access management**.
2. Click **+** → **Add users**.
3. Email: the service account from step D, for example
   `ga-mcp@iranama-analytics-123456.iam.gserviceaccount.com`.
4. Untick "Notify new users by email".
5. Role: **Viewer**. Don't give it any higher role. Click **Add**.

Add it at the **property** level, not the account level, so it sees only Iranama.

## F. Get the secret and test the server

In Cloud Shell:

```bash
gcloud secrets versions access latest --secret=ga-mcp-secret; echo
```

Copy the value. This is your `MCP_SECRET`, so treat it like a password. Then test the
server, replacing `URL` and `SECRET` with your values:

```bash
curl -s https://URL/healthz
```

That should print `{"ok": true}`.

```bash
curl -s -X POST "https://URL/mcp?key=SECRET" -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_account_summaries","arguments":{}}}'
```

That should list your GA account with the Iranama property. An empty list means step E
isn't done yet; it can also take a few minutes to apply.

## G. Connect it to Claude

Do this the same way the Meta Ads MCP is connected:

1. Claude → **Settings** → **Connectors** → **Add custom connector**.
2. Name: `Google Analytics (Iranama)`.
3. URL: `https://<service-url>/mcp?key=<MCP_SECRET>`.
4. Save. Then, in a chat, open the connector menu and make sure it's switched on.

**Claude Code (terminal):**

```bash
claude mcp add --transport http google-analytics "https://<service-url>/mcp?key=<MCP_SECRET>"
```

## H. Make sure GA has the data Claude needs

The website sends events to Google Tag Manager (GTM). GTM must forward them to GA4.

1. **GTM** (<https://tagmanager.google.com>) → the container from Iranama's admin settings
   → **Tags**. You should have:
   - a **Google tag** (GA4 configuration) with your Measurement ID (`G-…`), firing on
     **All Pages**
   - a **GA4 Event** tag for `page_view`, triggered by the Custom Event `page_view`. The
     site sends this on every in-app navigation.
   - GA4 Event tags for `add_to_cart`, `purchase` and `generate_lead`, each triggered by a
     Custom Event with the same name. Tick **Send Ecommerce data** → Data source: **Data
     Layer**, so `transaction_id`, `value`, `currency` and `items` reach GA.
2. If a tag is missing, create it, then click **Submit** → **Publish**.
3. **GA4** → **Admin** → **Events** (or **Key events**): mark `purchase` and
   `generate_lead` as **key events**.
4. Check it: GA4 → **Reports** → **Realtime**. Open the site in another tab and click
   around; you should see yourself within about 30 seconds.

`transaction_id` is the order number (astrology `order_no`, shop `order_number`). It lets
Claude match GA purchases to real orders through the platform data MCP.

## I. Try it

Ask Claude, for example:

- "Using GA property 412345678, show sessions, users and purchases by source / medium for
  the last 28 days."
- "Which landing pages brought the most `generate_lead` events last week?"
- "Run a funnel: page_view → add_to_cart → purchase for the last 30 days."
- "Compare utm_campaign performance in GA with Meta spend for the same campaigns."

## J. Troubleshooting

| What you see | Fix |
|---|---|
| Deploy fails with `PERMISSION_DENIED` from Cloud Build or storage | Newer projects build with the Compute Engine default service account. Run the two commands below this table. |
| `FAILED_PRECONDITION: ... allUsers` or "domain restricted sharing" | An organization policy blocks public Cloud Run. Ask your Google Workspace admin to allow `allUsers` on this project (policy `iam.allowedPolicyMemberDomains`), or create the project outside the organization. |
| `401 unauthorized` | Wrong or missing `?key=`. Copy the secret again (step F), and make sure it isn't cut off or URL-encoded wrongly. |
| `get_account_summaries` returns nothing, or `403 ... does not have sufficient permissions` | Step E: add the service account as Viewer on the property, then wait a few minutes. |
| `... has not been used in project ... or it is disabled` | Re-run `deploy.sh`; it enables the GA Data and Admin APIs. |
| Realtime shows nothing | GTM isn't published, or the GA4 Google tag is missing (step H). |

Commands for the first row (Cloud Build `PERMISSION_DENIED`):

```bash
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
```

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" --role="roles/cloudbuild.builds.builder"
```

## K. Day-two tasks

**Update the server:** in Cloud Shell, run `cd ga-mcp`, then `git pull`, then re-run
`deploy.sh`.

**Rotate the secret** (if it ever leaks):

```bash
openssl rand -hex 32 | tr -d '\n' | gcloud secrets versions add ga-mcp-secret --data-file=-
```

```bash
gcloud run services update ga-mcp --region asia-south1 --set-secrets MCP_SECRET=ga-mcp-secret:latest
```

Then update the connector URL in Claude.

**Remove access:** delete the service account from GA4 property access, or delete the
Cloud Run service:

```bash
gcloud run services delete ga-mcp --region asia-south1
```

**Logs:** Cloud Console → **Cloud Run** → `ga-mcp` → **Logs**. Cloud Run's request log
records full URLs, including `?key=`. Restrict who can view logs in this project, or
connect with an `Authorization: Bearer <secret>` header in clients that support custom
headers.

**Cost:** with min-instances 0, an idle server costs nothing. Normal use by one team
stays within Cloud Run's free tier. Secret Manager costs a few cents a month.
