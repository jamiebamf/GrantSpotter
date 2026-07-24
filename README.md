# GrantSpotter Crawler V1

This package is the first operational grant-ingestion service for GrantSpotter. It monitors GOV.UK Find a Grant, stores source pages, extracts structured grant information, scores confidence, sends uncertain records to review, and publishes approved grants into the existing PHP website.

## What is included

- GOV.UK listing and detail-page crawler
- HTML cleaning and content hashing
- Deterministic extraction plus optional OpenAI Structured Outputs
- Supabase/PostgreSQL schema
- Duplicate fingerprinting
- Confidence scoring and review queue
- Daily scheduler
- Admin API for crawling, approval and publishing
- Secure PHP website import endpoint
- Docker and Render deployment configuration

## 1. Create the Supabase tables

Open Supabase > SQL Editor, paste the complete contents of `sql/schema.sql`, and run it once.

Use the **service role key only on the crawler server**. Never put it in public PHP, JavaScript or a browser.

## 2. Add the website import endpoint

Copy:

`website-integration/api/import-approved-grants.php`

into:

`public_html/api/import-approved-grants.php`

Edit `IMPORT_SECRET` in that file and use the same value for `WEBSITE_IMPORT_SECRET` on the crawler server.

The endpoint creates or updates records in the website's existing `data/grants.json` file using the crawler's Supabase grant UUID as `external_id`.

## 3. Deploy the crawler

Recommended: Render, Railway, Fly.io, or a small VPS. Shared Hostinger PHP hosting is not appropriate for a continuous Python worker.

### Render

1. Create a new Git repository containing this folder.
2. In Render, choose **New > Blueprint** and select the repository.
3. Add all secret environment variables from `.env.example`.
4. Deploy.

### Docker/VPS

```bash
docker build -t grantspotter-crawler .
docker run --env-file .env -p 8000:8000 grantspotter-crawler
```

## 4. Run the first crawl

```bash
curl -X POST "https://YOUR-CRAWLER/admin/crawl/govuk" \
  -H "X-Admin-Key: YOUR_ADMIN_API_KEY"
```

The service also runs daily at the configured UTC hour.

## 5. Review records

List records needing review:

```bash
curl "https://YOUR-CRAWLER/admin/grants?status=review" \
  -H "X-Admin-Key: YOUR_ADMIN_API_KEY"
```

Approve one:

```bash
curl -X POST "https://YOUR-CRAWLER/admin/grants/GRANT_UUID/review" \
  -H "X-Admin-Key: YOUR_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action":"approve","notes":"Checked against official page"}'
```

Publish it to the PHP website:

```bash
curl -X POST "https://YOUR-CRAWLER/admin/grants/GRANT_UUID/publish" \
  -H "X-Admin-Key: YOUR_ADMIN_API_KEY"
```

## Important launch rule

Keep automatic publishing disabled in practice until the crawler has been tested against a meaningful batch. Set `AUTO_PUBLISH_MIN_SCORE=101` during initial testing so every record requires approval. Once extraction accuracy is proven, reduce it carefully for trusted official sources.

## Current scope

V1 deliberately supports one trusted source: GOV.UK Find a Grant. The adapter architecture allows National Lottery, community foundations and council sources to be added next without changing the database or publishing workflow.
