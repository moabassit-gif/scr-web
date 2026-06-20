# API Endpoints

Base URLs:

```text
Local:      http://127.0.0.1:8000
Cloudflare: https://scr-web.your-radar.workers.dev
```

Use the Cloudflare URL in production, and the local URL while developing on your machine.

## 1. Search Links

Returns search result links only. This uses Serper.

```http
GET /links?q=iphone%2017%20pro%20max&limit=10&country=eg
```

Curl:

```bash
curl "https://scr-web.your-radar.workers.dev/links?q=iphone%2017%20pro%20max&limit=10&country=eg"
```

Query params:

```text
q        Required. Search keyword.
limit    Optional. 1 to 10. Default 10.
country  Optional. Two-letter country code, like eg, us, sa.
```

Response:

```json
{
  "query": "iphone 17 pro max",
  "provider": "serper",
  "cached": false,
  "results": [
    {
      "title": "Result title",
      "link": "https://example.com/page",
      "snippet": "Short search result text"
    }
  ],
  "articles": null
}
```

Notes:

```text
One request to /links costs one Serper search request.
limit=10 still costs one Serper request.
```

## 2. Search And Extract Articles

Searches by keyword, gets links, then scrapes article content from each link.

```http
GET /articles?q=iphone%2017%20pro%20max&limit=10&country=eg
```

Curl:

```bash
curl "https://scr-web.your-radar.workers.dev/articles?q=iphone%2017%20pro%20max&limit=10&country=eg"
```

Response:

```json
{
  "query": "iphone 17 pro max",
  "provider": "serper",
  "cached": false,
  "results": [
    {
      "title": "Result title",
      "link": "https://example.com/article",
      "snippet": "Short search result text"
    }
  ],
  "articles": [
    {
      "url": "https://example.com/article",
      "content": "Full extracted article text...",
      "keyword": ["keyword1", "keyword2"],
      "author": "Author name",
      "published_date": "2026-06-18T10:00:00Z",
      "keys": {
        "month": "2026-06",
        "provider": "serper",
        "keys": [
          {
            "index": 1,
            "key": "396214...4ce5",
            "used": "2/2500",
            "remaining": "2498/2500"
          }
        ]
      }
    }
  ]
}
```

Notes:

```text
Serper is only used to get the links.
Scraping the article pages does not consume Serper.
Some websites may block scraping or return limited content.
```

## 3. Scrape One Article URL

Use this when you already have the article link and only want the JSON content.

```http
GET /scrape-url?url=https%3A%2F%2Fexample.com%2Farticle
```

Curl:

```bash
curl "https://scr-web.your-radar.workers.dev/scrape-url?url=https%3A%2F%2Fwww.bbc.com%2Fsport%2Ffootball%2Farticles%2Fcg74rzx582ko"
```

Response:

```json
{
  "url": "https://example.com/article",
  "content": "Full extracted article text...",
  "keyword": ["keyword1", "keyword2"],
  "author": "Author name",
  "published_date": "2026-06-18T10:00:00Z",
  "keys": [
    {
      "index": 1,
      "key": "396214...4ce5",
      "used": "2/2500",
      "remaining": "2498/2500"
    }
  ]
}
```

Notes:

```text
/scrape-url does not use Serper.
It only fetches the URL you provide and extracts article metadata/content.
```

## 4. Raw Serper Response

Returns the original Serper response with no filtering.

```http
GET /serper-raw?q=iphone%2017%20pro%20max&limit=10&country=eg
```

Curl:

```bash
curl "https://scr-web.your-radar.workers.dev/serper-raw?q=iphone%2017%20pro%20max&limit=10&country=eg"
```

Response:

```json
{
  "searchParameters": {
    "q": "iphone 17 pro max",
    "gl": "eg",
    "type": "search",
    "num": 10,
    "engine": "google"
  },
  "organic": [
    {
      "title": "Result title",
      "link": "https://example.com/page",
      "snippet": "Search snippet",
      "position": 1
    }
  ],
  "credits": 1
}
```

Notes:

```text
Use this endpoint when you want to inspect exactly what Serper returns.
This costs one Serper search request.
```

## 5. Search Usage

Returns local tracked usage for Serper keys.

```http
GET /search-usage
```

Curl:

```bash
curl "https://scr-web.your-radar.workers.dev/search-usage"
```

Response:

```json
{
  "month": "2026-06",
  "provider": "serper",
  "keys": [
    {
      "index": 1,
      "key": "396214...4ce5",
      "used": "2/2500",
      "remaining": "2498/2500"
    },
    {
      "index": 2,
      "key": "a91ae9...9d6e",
      "used": "0/2500",
      "remaining": "2500/2500"
    }
  ]
}
```

Notes:

```text
This is local app tracking, not a live Serper billing API.
It increments after successful Serper search requests.
```

## 6. Root

Shows available examples.

```http
GET /
```

Curl:

```bash
curl "https://scr-web.your-radar.workers.dev/"
```

Response:

```json
{
  "links": "/links?q=iphone%2017%20pro%20max&limit=10&country=eg",
  "articles": "/articles?q=iphone%2017%20pro%20max&limit=10&country=eg",
  "scrape_url": "/scrape-url?url=https://example.com/article",
  "serper_raw": "/serper-raw?q=iphone%2017%20pro%20max&limit=10&country=eg",
  "search_usage": "/search-usage"
}
```

## Country Examples

```text
eg  Egypt
us  United States
sa  Saudi Arabia
ae  United Arab Emirates
gb  United Kingdom
```

## Python Tools

Local Python helpers are in:

```text
C:\Users\HP\Documents\scr-web\tools.py
```

Usage:

```python
from tools import get_links, get_articles, scrape_url, get_serper_raw

links = get_links("iphone 17 pro max", limit=10, country="eg")
articles = get_articles("iphone 17 pro max", limit=10, country="eg")
article = scrape_url("https://www.bbc.com/sport/football/articles/cg74rzx582ko")
raw = get_serper_raw("iphone 17 pro max", limit=10, country="eg")
```
