from __future__ import annotations

from app import extract_article, scrape_article_json, search_web, serper_raw_search


def scrape_url(url: str) -> dict:
    article = scrape_article_json(url)
    return article.model_dump()


def get_serper_raw(query: str, limit: int = 10, country: str | None = None) -> dict:
    return serper_raw_search(query, limit, country)


def get_links(query: str, limit: int = 10, country: str | None = None) -> list[dict]:
    results, cached, provider = search_web(query, limit, country)
    return [
        {
            "title": result.title,
            "link": result.link,
            "snippet": result.snippet,
            "provider": provider,
            "cached": cached,
        }
        for result in results
    ]


def get_articles(query: str, limit: int = 10, country: str | None = None) -> list[dict]:
    articles = []
    results, cached, provider = search_web(query, limit, country)

    for result in results:
        try:
            article = extract_article(result.link)
        except Exception:
            continue
        articles.append(
            {
                "author": article.author,
                "title": article.title,
                "content": article.content,
                "website_url": article.website_url,
                "source_url": result.link,
                "provider": provider,
                "cached": cached,
            }
        )

    return articles
