const SERPER_SEARCH_URL = "https://google.serper.dev/search";

const state = {
  lastRequestAt: 0,
  nextKeyIndex: 0,
  usage: {},
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "access-control-allow-origin": "*",
    },
  });
}

function getSerperKeys(env) {
  const keys = env.SERPER_API_KEYS || env.SERPER_API_KEY || "";
  return keys.split(",").map((key) => key.trim()).filter(Boolean);
}

function maskKey(key) {
  if (key.length <= 10) return "*".repeat(key.length);
  return `${key.slice(0, 6)}...${key.slice(-4)}`;
}

async function keyId(key) {
  const data = new TextEncoder().encode(key);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function currentMonth() {
  return new Date().toISOString().slice(0, 7);
}

async function waitForRateLimit(env) {
  const requestsPerSecond = Number(env.SERPER_REQUESTS_PER_SECOND || "2");
  if (!requestsPerSecond || requestsPerSecond <= 0) return;

  const minInterval = 1000 / requestsPerSecond;
  const now = Date.now();
  const waitFor = state.lastRequestAt + minInterval - now;
  if (waitFor > 0) await new Promise((resolve) => setTimeout(resolve, waitFor));
  state.lastRequestAt = Date.now();
}

async function loadUsage(env) {
  if (!env.SEARCH_KV) return { month: currentMonth(), keys: state.usage };
  const usage = await env.SEARCH_KV.get("serper_usage", "json");
  if (!usage || usage.month !== currentMonth()) return { month: currentMonth(), keys: {} };
  usage.keys ||= {};
  return usage;
}

async function saveUsage(env, usage) {
  if (!env.SEARCH_KV) {
    state.usage = usage.keys || {};
    return;
  }
  await env.SEARCH_KV.put("serper_usage", JSON.stringify(usage));
}

async function getKeyUsed(env, key) {
  const usage = await loadUsage(env);
  const id = await keyId(key);
  return Number(usage.keys[id]?.used || 0);
}

async function incrementKeyUsage(env, key) {
  const usage = await loadUsage(env);
  const id = await keyId(key);
  usage.keys[id] ||= { used: 0, masked: maskKey(key) };
  usage.keys[id].used += 1;
  usage.keys[id].masked = maskKey(key);
  await saveUsage(env, usage);
}

async function buildUsage(env) {
  const usage = await loadUsage(env);
  const limit = Number(env.SERPER_MONTHLY_LIMIT || "2500");
  const keys = await Promise.all(getSerperKeys(env).map(async (key, index) => {
    const id = await keyId(key);
    const used = Number(usage.keys[id]?.used || 0);
    return {
      index: index + 1,
      key: maskKey(key),
      used: `${used}/${limit}`,
      remaining: `${Math.max(limit - used, 0)}/${limit}`,
    };
  }));
  return { month: usage.month, provider: "serper", keys };
}

async function serperRaw(env, query, limit, country) {
  const keys = getSerperKeys(env);
  if (!keys.length) throw new Error("Set SERPER_API_KEYS secret first");

  const monthlyLimit = Number(env.SERPER_MONTHLY_LIMIT || "2500");
  let lastError = "Serper API failed";

  for (let attempt = 0; attempt < keys.length; attempt += 1) {
    const index = state.nextKeyIndex % keys.length;
    state.nextKeyIndex = (state.nextKeyIndex + 1) % keys.length;
    const key = keys[index];

    if ((await getKeyUsed(env, key)) >= monthlyLimit) {
      lastError = `Serper API key #${index + 1} reached local monthly limit`;
      continue;
    }

    const payload = { q: query, num: limit };
    if (country) payload.gl = country.toLowerCase();

    await waitForRateLimit(env);
    const response = await fetch(SERPER_SEARCH_URL, {
      method: "POST",
      headers: { "X-API-KEY": key, "content-type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (response.ok) {
      await incrementKeyUsage(env, key);
      return await response.json();
    }

    const text = await response.text();
    lastError = `Serper API key #${index + 1} failed: ${text || response.status}`;
  }

  throw new Error(lastError);
}

async function searchLinks(env, query, limit, country) {
  const raw = await serperRaw(env, query, limit, country);
  const results = (raw.organic || []).filter((item) => item.link).map((item) => ({
    title: item.title || "",
    link: item.link || "",
    snippet: item.snippet || null,
  }));
  return { query, provider: "serper", cached: false, results, articles: null };
}

function cleanText(text) {
  return text.replace(/\s+/g, " ").trim();
}

function metaContent(html, names) {
  for (const [attr, value] of names) {
    const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`<meta[^>]+${attr}=["']${escaped}["'][^>]+content=["']([^"']+)["'][^>]*>`, "i");
    const match = html.match(re);
    if (match) return cleanText(decodeHtml(match[1]));
  }
  return null;
}

function decodeHtml(value) {
  return value
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function stripTags(html) {
  return decodeHtml(html.replace(/<[^>]+>/g, " "));
}

function extractContent(html) {
  const cleaned = html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
    .replace(/<(nav|footer|aside|form)[\s\S]*?<\/\1>/gi, " ");

  const article = cleaned.match(/<article[\s\S]*?<\/article>/i)?.[0]
    || cleaned.match(/<main[\s\S]*?<\/main>/i)?.[0]
    || cleaned.match(/<body[\s\S]*?<\/body>/i)?.[0]
    || cleaned;

  const blocks = [];
  const blockRe = /<(p|h2|h3|li)[^>]*>([\s\S]*?)<\/\1>/gi;
  let match;
  while ((match = blockRe.exec(article))) {
    const text = cleanText(stripTags(match[2]));
    if (text.length >= 30 && !blocks.includes(text)) blocks.push(text);
  }
  return blocks.length ? blocks.join("\n\n") : cleanText(stripTags(article));
}

function extractKeywords(html) {
  const value = metaContent(html, [
    ["name", "keywords"],
    ["name", "news_keywords"],
  ]);
  if (!value) return [];
  return value.split(",").map((item) => cleanText(item)).filter(Boolean);
}

function extractPublishedDate(html) {
  const meta = metaContent(html, [
    ["property", "article:published_time"],
    ["name", "pubdate"],
    ["name", "publishdate"],
    ["name", "date"],
    ["itemprop", "datePublished"],
  ]);
  if (meta) return meta;

  const jsonLdRe = /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  let match;
  while ((match = jsonLdRe.exec(html))) {
    try {
      const data = JSON.parse(match[1].trim());
      const found = findJsonValue(data, ["datePublished", "dateCreated"]);
      if (found) return cleanText(found);
    } catch {}
  }

  const time = html.match(/<time[^>]+datetime=["']([^"']+)["'][^>]*>/i);
  return time ? cleanText(time[1]) : null;
}

function findJsonValue(value, keys) {
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findJsonValue(item, keys);
      if (found) return found;
    }
  } else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      if (keys.includes(key) && typeof item === "string") return item;
      const found = findJsonValue(item, keys);
      if (found) return found;
    }
  }
  return null;
}

async function scrapeUrl(env, url) {
  const response = await fetch(url, {
    headers: { "user-agent": "Mozilla/5.0 (compatible; ArticleExtractor/1.0)" },
  });
  if (!response.ok) throw new Error(`Could not fetch URL: ${response.status}`);

  const finalUrl = response.url || url;
  const html = await response.text();
  return {
    url: finalUrl,
    content: extractContent(html),
    keyword: extractKeywords(html),
    author: metaContent(html, [
      ["name", "author"],
      ["property", "article:author"],
      ["name", "twitter:creator"],
    ]),
    published_date: extractPublishedDate(html),
    keys: await buildUsage(env),
  };
}

async function articles(env, query, limit, country) {
  const links = await searchLinks(env, query, limit, country);
  const articles = await Promise.allSettled(links.results.map((item) => scrapeUrl(env, item.link)));
  return {
    ...links,
    articles: articles.filter((item) => item.status === "fulfilled").map((item) => item.value),
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const q = url.searchParams.get("q");
    const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || "10"), 1), 10);
    const country = url.searchParams.get("country");

    try {
      if (request.method === "OPTIONS") return json({});
      if (url.pathname === "/") {
        return json({
          links: "/links?q=iphone%2017%20pro%20max&limit=10&country=eg",
          articles: "/articles?q=iphone%2017%20pro%20max&limit=10&country=eg",
          scrape_url: "/scrape-url?url=https://example.com/article",
          serper_raw: "/serper-raw?q=iphone%2017%20pro%20max&limit=10&country=eg",
          search_usage: "/search-usage",
        });
      }
      if (url.pathname === "/search-usage") return json(await buildUsage(env));
      if (url.pathname === "/scrape-url") return json(await scrapeUrl(env, url.searchParams.get("url")));
      if (!q && ["/links", "/articles", "/serper-raw"].includes(url.pathname)) {
        return json({ detail: "Missing q parameter" }, 400);
      }
      if (url.pathname === "/serper-raw") return json(await serperRaw(env, q, limit, country));
      if (url.pathname === "/links") return json(await searchLinks(env, q, limit, country));
      if (url.pathname === "/articles") return json(await articles(env, q, limit, country));
      return json({ detail: "Not found" }, 404);
    } catch (error) {
      return json({ detail: error.message || "Internal error" }, 500);
    }
  },
};
