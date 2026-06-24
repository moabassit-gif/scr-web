# Article JSON Extractor

A small Python API that accepts article URLs and returns JSON:

```json
{
  "author": "Author name",
  "title": "Article title",
  "content": "Article body text",
  "website_url": "https://example.com"
}
```

## Local Setup

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

## Docker Server Setup

Create `.env` from `.env.example`, add your Serper keys, and set the public URL users will call:

```env
SERPER_API_KEYS=key1,key2,key3
SERPER_MONTHLY_LIMIT=2500
SERPER_REQUESTS_PER_SECOND=2
PUBLIC_BASE_URL=http://YOUR_SERVER_IP:8000
```

Run:

```bash
docker compose up -d --build
```

From another machine, call:

```text
http://YOUR_SERVER_IP:8000/articles?q=nursing%20home&limit=10&country=us
```

The Python gateway client defaults to the Cloudflare Worker:

```bash
python gateway_client.py articles "nursing home" --limit 10 --country us
```

To call your Docker server instead:

```bash
python gateway_client.py --base-url "http://YOUR_SERVER_IP:8000" articles "nursing home" --limit 10 --country us
```

## Extract One URL

```text
http://127.0.0.1:8000/extract?url=https://example.com/article
```

## Search With Serper

Create a `.env` file:

```env
SERPER_API_KEY=your_serper_api_key_here
```

Or use multiple Serper keys for failover:

```env
SERPER_API_KEYS=first_serper_key,second_serper_key
SERPER_MONTHLY_LIMIT=2500
SERPER_REQUESTS_PER_SECOND=2
```

Check local monthly usage:

```text
http://YOUR_SERVER_IP:8000/search-usage
```

Then search and optionally extract articles:

```text
http://YOUR_SERVER_IP:8000/articles?q=nursing%20home&limit=10&country=us
```

If `SERPER_API_KEY` is missing, the app falls back to Google Custom Search if `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` are set.
