# Google Analytics MCP (Cloud Run)

A remote MCP server that lets Claude read Google Analytics 4 data. It runs Google's
**official** server, [`analytics-mcp`](https://github.com/googleanalytics/google-analytics-mcp)
(pinned to 1.1.0, read-only), behind a small gateway that adds the same shared-secret
auth as the Meta Ads MCP.

**Endpoint:** `https://<cloud-run-url>/mcp?key=<MCP_SECRET>`

Full step-by-step setup: **[docs/SETUP.md](docs/SETUP.md)**

Another business (separate service, service account and secret): **[docs/KANDY.md](docs/KANDY.md)**

## How it works

```
Claude ──?key=──► Cloud Run: ga_mcp_gateway ──► official analytics-mcp tools ──► GA4 Data / Admin API
                  (checks key, strips it)        (read-only)                     (as the service account)
```

- Google API calls use the Cloud Run **service account**. No key file and no Google login
  in Claude.
- Access to GA data is limited to what that service account can see. Add it as **Viewer**
  on the Iranama property only.
- The gateway refuses to start if `ANALYTICS_MCP_ALLOW_WRITE` is set. Every tool is
  read-only.
- `GET /healthz` is open and returns `{"ok": true}`. Every other path except `/mcp`
  returns 404.

## Tools (from the official server)

| Tool | What it answers |
|---|---|
| `get_account_summaries` | Which GA accounts and properties the service account can see |
| `get_property_details` | Property settings: timezone, currency, industry |
| `list_google_ads_links` | Linked Google Ads accounts |
| `list_property_annotations` | Notes on the timeline (launches, outages) |
| `list_key_events` | Which events count as key events (conversions) |
| `get_custom_dimensions_and_metrics` | Custom dimensions and metrics you can report on |
| `run_report` | Any GA4 report: dimensions, metrics, date ranges, filters, ordering |
| `run_realtime_report` | Last 30 minutes |
| `run_funnel_report` | Step-by-step funnel drop-off |
| `run_conversions_report` | Key events and conversions by source, campaign, etc. |

## Environment

| Key | Required | Notes |
|---|---|---|
| `MCP_SECRET` | yes | Mounted from Secret Manager (`ga-mcp-secret`) by `scripts/deploy.sh` |
| `PORT` | set by Cloud Run | Default 8080 |

The secret is accepted as `?key=`, `Authorization: Bearer`, or `X-MCP-Key`, and compared in
constant time. It's removed before the request reaches the official server, which would
otherwise treat a Bearer header as a Google token.

## Deploy

```bash
PROJECT_ID=<your-project> ./scripts/deploy.sh
```

## Local development

```bash
uv venv .venv -p 3.12
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest -q
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/analytics.readonly,https://www.googleapis.com/auth/cloud-platform
MCP_SECRET=dev .venv/bin/uvicorn ga_mcp_gateway.app:app --port 8080
# http://localhost:8080/mcp?key=dev
```

## Updating the official server

Change the version in `requirements.txt`, run the tests, and deploy. Read Google's
changelog first: the gateway relies on `analytics_mcp.coordinator.create_server(...)`.
