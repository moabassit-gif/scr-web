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

## Setup

```bash
pip install -r requirements.txt
uvicorn app:app --reload
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
http://127.0.0.1:8000/search-usage
```

Then search and optionally extract articles:

```text
http://127.0.0.1:8000/search?q=site:bbc.com world cup article&limit=1&extract=true
```

If `SERPER_API_KEY` is missing, the app falls back to Google Custom Search if `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` are set.
