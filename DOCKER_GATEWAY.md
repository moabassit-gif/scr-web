# Docker And Gateway Client

## Run Locally Like A Server

Build and start:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
```

Open:

```text
http://127.0.0.1:8000
```

Stop:

```bash
docker compose down
```

View logs:

```bash
docker compose logs -f scr-web
```

## Environment

The container reads keys from `.env`:

```env
SERPER_API_KEYS=key1,key2,key3
SERPER_MONTHLY_LIMIT=2500
SERPER_REQUESTS_PER_SECOND=2
```

`.env` is not copied into the Docker image because `.dockerignore` excludes it. Docker Compose passes it at runtime.

## Gateway Client

Use `gateway_client.py` to call the gateway from Python/CLI.

Default base URL:

```text
http://127.0.0.1:8000
```

You can override it:

```bash
python gateway_client.py --base-url "https://scr-web.your-radar.workers.dev" usage
```

## Examples

Search links:

```bash
python gateway_client.py links "nursing home" --limit 10 --country us
```

Search and extract articles:

```bash
python gateway_client.py articles "nursing home" --limit 10 --country us
```

Scrape one URL:

```bash
python gateway_client.py scrape-url "https://www.bbc.com/sport/football/articles/cg74rzx582ko"
```

Raw Serper response:

```bash
python gateway_client.py serper-raw "nursing home" --limit 10 --country us
```

Usage:

```bash
python gateway_client.py usage
```

Print a request URL without calling it:

```bash
python gateway_client.py url articles "nursing home" --limit 10 --country us
```
