"""Social Pulse service — fetches trending content from free APIs."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.db.session import async_session_factory
from app.models.social_pulse import PulseNiche, SocialPulse, TrendKeyword

logger = logging.getLogger(__name__)

REDDIT_HEADERS = {
    "User-Agent": "SutraSocialPulse/1.0 (research bot; contact@sutra.ai)"
}


# ── Sentiment ──────────────────────────────────────────────────────────────────

def analyze_sentiment(text: str) -> str:
    """Simple keyword-based sentiment (avoids TextBlob NLTK downloads)."""
    if not text:
        return "neutral"
    text_lower = text.lower()
    positive_words = {"great", "amazing", "excellent", "best", "love", "awesome", "revolutionary",
                      "breakthrough", "win", "success", "growth", "profit", "bullish", "surge", "boom"}
    negative_words = {"crash", "fail", "bad", "worst", "terrible", "scandal", "loss", "bearish",
                      "drop", "decline", "crisis", "ban", "lawsuit", "hack", "breach", "controversy"}
    pos = sum(1 for w in positive_words if w in text_lower)
    neg = sum(1 for w in negative_words if w in text_lower)
    if pos > neg + 1:
        return "positive"
    if neg > pos + 1:
        return "negative"
    if pos > 0 and neg > 0:
        return "mixed"
    return "neutral"


def calculate_virality_score(metrics: dict) -> float:
    """Composite virality score 0–100."""
    velocity = min(metrics.get("velocity", 0), 100)
    growth = min(metrics.get("growth_pct", 0), 100)
    cross_platform = min(metrics.get("cross_platform", 0) * 20, 100)
    freshness_hours = metrics.get("freshness_hours", 24)
    freshness = max(0, 100 - (freshness_hours * 4))

    score = (velocity * 0.4 + growth * 0.3 + cross_platform * 0.2 + freshness * 0.1)
    return round(min(score, 100), 1)


# ── Google Trends ──────────────────────────────────────────────────────────────

# Geo code mapping for the trending RSS feed
_GEO_MAP = {
    "US": "US", "UK": "GB", "GB": "GB", "IN": "IN",
    "AU": "AU", "CA": "CA", "DE": "DE", "FR": "FR",
    "JP": "JP", "BR": "BR", "global": "US",
}


async def fetch_google_trends(region: str = "US") -> list[dict]:
    """Fetch daily trending searches from Google Trends public RSS feed."""
    geo = _GEO_MAP.get(region.upper(), "US")
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    try:
        from xml.etree import ElementTree as ET

        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        ) as client:
            resp = await client.get(url)
            if not resp.is_success:
                logger.warning(f"Google Trends RSS {resp.status_code} for geo={geo}")
                return []

        root = ET.fromstring(resp.text)
        ns = {"ht": "https://trends.google.com/trending/rss"}
        items_xml = root.findall(".//item")

        results = []
        for i, item in enumerate(items_xml[:20]):
            title = item.findtext("title") or ""
            link = item.findtext("link") or f"https://trends.google.com/trends/explore?q={title.replace(' ', '+')}&geo={geo}"
            traffic_raw = item.findtext("ht:approx_traffic", namespaces=ns) or "0+"
            # Parse traffic: "20000+" → 20000
            traffic = int(traffic_raw.replace(",", "").replace("+", "").strip() or "0")

            # Normalize traffic to 0-100 velocity (log scale capped at 1M)
            import math
            velocity = min(math.log10(max(traffic, 10)) / 6 * 100, 100) if traffic else max(0, 80 - i * 4)

            virality = calculate_virality_score({
                "velocity": velocity,
                "growth_pct": max(0, 80 - i * 3),
                "freshness_hours": 1,
            })

            # Extract news articles from item
            news_items = item.findall("ht:news_item", namespaces=ns)
            description = None
            if news_items:
                news_title = news_items[0].findtext("ht:news_item_title", namespaces=ns)
                news_source = news_items[0].findtext("ht:news_item_source", namespaces=ns)
                if news_title:
                    description = f"{news_title}" + (f" — {news_source}" if news_source else "")

            results.append({
                "platform": "google_trends",
                "category": "trending",
                "title": title,
                "url": link,
                "description": description or f"Trending on Google (approx. {traffic_raw} searches)",
                "metrics": {
                    "rank": i + 1,
                    "approx_traffic": traffic,
                    "velocity": velocity,
                    "growth_pct": max(0, 80 - i * 3),
                    "freshness_hours": 1,
                    "virality_score": virality,
                },
                "sentiment": analyze_sentiment(title + " " + (description or "")),
                "region": region,
                "tags": ["google_trends", "trending"],
            })
        logger.info(f"[SocialPulse] Google Trends: {len(results)} items fetched for {region}")
        return results
    except Exception as e:
        logger.warning(f"Google Trends RSS fetch failed: {e}")
        return []


async def fetch_google_trends_for_niche(niche: PulseNiche, region: str = "US") -> list[dict]:
    """Fetch niche-specific trends via pytrends interest_over_time (most reliable endpoint)."""
    if not niche.google_trends_keywords:
        return []
    try:
        from pytrends.request import TrendReq

        def _fetch():
            pt = TrendReq(hl="en-US", tz=360, timeout=(10, 30))
            keywords = niche.google_trends_keywords[:5]  # max 5 at once
            results = []
            try:
                pt.build_payload(keywords, cat=0, timeframe="now 7-d", geo=region if region != "global" else "")
                df = pt.interest_over_time()
                if df is not None and not df.empty:
                    # Get average interest for each keyword in last 7 days
                    for kw in keywords:
                        if kw in df.columns:
                            avg_interest = float(df[kw].mean())
                            if avg_interest > 10:  # filter low interest
                                results.append({"keyword": kw, "value": avg_interest})
            except Exception as e:
                logger.debug(f"pytrends interest_over_time failed: {e}")
            return sorted(results, key=lambda x: x["value"], reverse=True)

        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, _fetch)

        items = []
        for r in raw:
            virality = calculate_virality_score({
                "velocity": min(r["value"], 100),
                "growth_pct": min(r["value"] * 0.7, 100),
                "freshness_hours": 12,
            })
            kw = r["keyword"]
            items.append({
                "platform": "google_trends",
                "category": "rising",
                "title": kw,
                "url": f"https://trends.google.com/trends/explore?q={kw.replace(' ', '+')}&geo={region}",
                "description": f"Interest score {r['value']:.0f}/100 in last 7 days — niche: {niche.name}",
                "metrics": {
                    "interest_score": r["value"],
                    "velocity": min(r["value"], 100),
                    "growth_pct": min(r["value"] * 0.7, 100),
                    "freshness_hours": 12,
                    "virality_score": virality,
                },
                "sentiment": analyze_sentiment(kw),
                "region": region,
                "tags": ["google_trends", "niche", niche.name.lower()],
                "niche_id": niche.id,
            })
        return items
    except ImportError:
        return []
    except Exception as e:
        logger.warning(f"Google Trends niche fetch failed for {niche.name}: {e}")
        return []


# ── YouTube ────────────────────────────────────────────────────────────────────

async def fetch_youtube_trending(region: str = "US", category_id: int = 0) -> list[dict]:
    """Fetch trending YouTube videos using Data API v3 (1 unit/call)."""
    from app.config import settings
    api_key = settings.google_api_key
    if not api_key:
        logger.warning("[SocialPulse] YouTube: GOOGLE_API_KEY not set — skipping")
        return []

    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region if region != "global" else "US",
        "maxResults": 20,
        "key": api_key,
    }
    if category_id:
        params["videoCategoryId"] = str(category_id)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://www.googleapis.com/youtube/v3/videos", params=params)
            if not resp.is_success:
                data = resp.json()
                err_msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                if "disabled" in err_msg.lower() or "SERVICE_DISABLED" in str(data):
                    logger.warning(
                        "[SocialPulse] YouTube Data API v3 is not enabled. "
                        "Enable it at: https://console.developers.google.com/apis/api/youtube.googleapis.com/overview"
                    )
                elif "blocked" in err_msg.lower() or "restricted" in err_msg.lower():
                    logger.warning(
                        f"[SocialPulse] YouTube API call blocked/restricted: {err_msg}. "
                        "Check your API key restrictions at: https://console.cloud.google.com/apis/credentials"
                    )
                else:
                    logger.warning(f"YouTube trending API failed: {err_msg}")
                return []
            data = resp.json()

        results = []
        for i, item in enumerate(data.get("items", [])):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            virality = calculate_virality_score({
                "velocity": min(views / 100000, 100),
                "growth_pct": min(likes / max(views, 1) * 500, 100),
                "freshness_hours": 6,
            })
            title = snippet.get("title", "")
            results.append({
                "platform": "youtube",
                "category": "trending",
                "title": title,
                "url": f"https://youtube.com/watch?v={item['id']}",
                "description": snippet.get("description", "")[:300],
                "metrics": {
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "velocity": min(views / 100000, 100),
                    "freshness_hours": 6,
                    "virality_score": virality,
                },
                "sentiment": analyze_sentiment(title),
                "region": region,
                "tags": ["youtube", "trending"] + snippet.get("tags", [])[:5],
            })
        return results
    except Exception as e:
        logger.warning(f"YouTube trending fetch failed: {e}")
        return []


async def fetch_youtube_for_niche(niche: PulseNiche, region: str = "US") -> list[dict]:
    """Search YouTube for niche-specific trending content (100 units/call)."""
    from app.config import settings
    api_key = settings.google_api_key
    if not api_key or not niche.google_trends_keywords:
        return []

    # Only use 1 keyword to conserve quota
    keyword = niche.google_trends_keywords[0]
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "viewCount",
        "publishedAfter": (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "maxResults": 10,
        "key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://www.googleapis.com/youtube/v3/search", params=params)
            if not resp.is_success:
                return []
            data = resp.json()

        results = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            vid_id = item.get("id", {}).get("videoId", "")
            title = snippet.get("title", "")
            virality = calculate_virality_score({"velocity": 60, "growth_pct": 70, "freshness_hours": 12})
            results.append({
                "platform": "youtube",
                "category": "viral",
                "title": title,
                "url": f"https://youtube.com/watch?v={vid_id}" if vid_id else None,
                "description": snippet.get("description", "")[:300],
                "metrics": {"velocity": 60, "growth_pct": 70, "freshness_hours": 12, "virality_score": virality},
                "sentiment": analyze_sentiment(title),
                "region": region,
                "tags": ["youtube", keyword],
                "niche_id": niche.id,
            })
        return results
    except Exception as e:
        logger.warning(f"YouTube niche fetch failed for {niche.name}: {e}")
        return []


# ── Reddit ─────────────────────────────────────────────────────────────────────

async def _fetch_reddit_posts(subreddit: str, sort: str = "rising", limit: int = 10) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}"
    try:
        async with httpx.AsyncClient(headers=REDDIT_HEADERS, timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)
            if not resp.is_success:
                return []
            data = resp.json()
        posts = []
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            posts.append({
                "title": p.get("title", ""),
                "url": f"https://reddit.com{p.get('permalink', '')}",
                "score": p.get("score", 0),
                "comments": p.get("num_comments", 0),
                "upvote_ratio": p.get("upvote_ratio", 0.5),
                "subreddit": subreddit,
                "created_utc": p.get("created_utc", 0),
            })
        return posts
    except Exception:
        return []


async def fetch_reddit_trending(subreddits: list[str] | None = None, region: str = "US") -> list[dict]:
    """Fetch rising/hot posts from default or configured subreddits."""
    if not subreddits:
        subreddits = ["technology", "programming", "business", "marketing", "worldnews"]

    all_posts = []
    tasks = [_fetch_reddit_posts(sub, "hot", 8) for sub in subreddits[:6]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_posts.extend(r)

    # Deduplicate by title
    seen = set()
    items = []
    for p in sorted(all_posts, key=lambda x: x["score"], reverse=True):
        if p["title"] in seen:
            continue
        seen.add(p["title"])
        age_hours = max(0, (datetime.now(timezone.utc).timestamp() - p["created_utc"]) / 3600)
        virality = calculate_virality_score({
            "velocity": min(p["score"] / 100, 100),
            "growth_pct": min(p["upvote_ratio"] * 100, 100),
            "freshness_hours": age_hours,
        })
        items.append({
            "platform": "reddit",
            "category": "trending",
            "title": p["title"],
            "url": p["url"],
            "description": f"r/{p['subreddit']} • {p['score']} upvotes • {p['comments']} comments",
            "metrics": {
                "score": p["score"],
                "comments": p["comments"],
                "upvote_ratio": p["upvote_ratio"],
                "velocity": min(p["score"] / 100, 100),
                "freshness_hours": age_hours,
                "virality_score": virality,
            },
            "sentiment": analyze_sentiment(p["title"]),
            "region": region,
            "tags": ["reddit", p["subreddit"]],
        })
    return items[:20]


async def fetch_reddit_for_niche(niche: PulseNiche, region: str = "US") -> list[dict]:
    """Fetch Reddit posts from niche-specific subreddits."""
    if not niche.subreddits:
        return []

    all_posts = []
    tasks = [_fetch_reddit_posts(sub, "rising", 8) for sub in niche.subreddits[:5]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_posts.extend(r)

    seen = set()
    items = []
    for p in sorted(all_posts, key=lambda x: x["score"], reverse=True):
        if p["title"] in seen:
            continue
        seen.add(p["title"])
        age_hours = max(0, (datetime.now(timezone.utc).timestamp() - p["created_utc"]) / 3600)
        virality = calculate_virality_score({
            "velocity": min(p["score"] / 50, 100),
            "growth_pct": min(p["upvote_ratio"] * 100, 100),
            "freshness_hours": age_hours,
        })
        items.append({
            "platform": "reddit",
            "category": "rising",
            "title": p["title"],
            "url": p["url"],
            "description": f"r/{p['subreddit']} • {p['score']} upvotes • {p['comments']} comments",
            "metrics": {
                "score": p["score"],
                "comments": p["comments"],
                "upvote_ratio": p["upvote_ratio"],
                "velocity": min(p["score"] / 50, 100),
                "freshness_hours": age_hours,
                "virality_score": virality,
            },
            "sentiment": analyze_sentiment(p["title"]),
            "region": region,
            "tags": ["reddit", p["subreddit"]],
            "niche_id": niche.id,
        })
    return items[:15]


# ── Hacker News ────────────────────────────────────────────────────────────────

async def fetch_hackernews_top(limit: int = 20) -> list[dict]:
    """Fetch top Hacker News stories via Firebase API (free, unlimited)."""
    base = "https://hacker-news.firebaseio.com/v0"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base}/topstories.json")
            if not resp.is_success:
                return []
            ids = resp.json()[:limit]

            async def fetch_item(item_id: int) -> dict | None:
                try:
                    r = await client.get(f"{base}/item/{item_id}.json")
                    return r.json() if r.is_success else None
                except Exception:
                    return None

            items_raw = await asyncio.gather(*[fetch_item(i) for i in ids])

        results = []
        for i, item in enumerate(items_raw):
            if not item or item.get("type") != "story":
                continue
            score = item.get("score", 0)
            title = item.get("title", "")
            virality = calculate_virality_score({
                "velocity": min(score / 5, 100),
                "growth_pct": min(score / 3, 100),
                "freshness_hours": max(0, (datetime.now(timezone.utc).timestamp() - item.get("time", 0)) / 3600),
            })
            results.append({
                "platform": "hackernews",
                "category": "trending",
                "title": title,
                "url": item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}",
                "description": f"HN #{i + 1} • {score} points • {item.get('descendants', 0)} comments",
                "metrics": {
                    "score": score,
                    "comments": item.get("descendants", 0),
                    "velocity": min(score / 5, 100),
                    "freshness_hours": max(0, (datetime.now(timezone.utc).timestamp() - item.get("time", 0)) / 3600),
                    "virality_score": virality,
                },
                "sentiment": analyze_sentiment(title),
                "region": "global",
                "tags": ["hackernews"],
            })
        return results
    except Exception as e:
        logger.warning(f"HackerNews fetch failed: {e}")
        return []


# ── Orchestrator ───────────────────────────────────────────────────────────────

async def refresh_all_platforms(region: str = "US") -> dict:
    """Main orchestrator: fetch all platforms + niches + keywords, save to DB."""
    from sqlalchemy import select, delete

    logger.info("[SocialPulse] Starting refresh...")
    stats = {"fetched": 0, "errors": 0, "niches": 0, "keywords": 0}

    async with async_session_factory() as db:
        # Load active niches
        niche_result = await db.execute(select(PulseNiche).where(PulseNiche.is_active == True))
        niches = niche_result.scalars().all()

        # Load active tracked keywords
        kw_result = await db.execute(select(TrendKeyword).where(TrendKeyword.is_active == True))
        tracked_keywords = kw_result.scalars().all()

        # Fetch general (non-niche) data concurrently
        general_tasks = [
            fetch_google_trends(region),
            fetch_youtube_trending(region),
            fetch_reddit_trending(region=region),
            fetch_hackernews_top(20),
        ]
        general_results = await asyncio.gather(*general_tasks, return_exceptions=True)

        all_items = []
        for r in general_results:
            if isinstance(r, list):
                all_items.extend(r)
            else:
                stats["errors"] += 1

        # Fetch niche-specific data
        for niche in niches:
            niche_tasks = [
                fetch_google_trends_for_niche(niche, region),
                fetch_reddit_for_niche(niche, region),
                fetch_youtube_for_niche(niche, region),
            ]
            niche_results = await asyncio.gather(*niche_tasks, return_exceptions=True)
            for r in niche_results:
                if isinstance(r, list):
                    all_items.extend(r)
                else:
                    stats["errors"] += 1
            stats["niches"] += 1

        # Fetch data for tracked keywords
        if tracked_keywords:
            from app.config import settings
            api_key = settings.google_api_key

            for kw_obj in tracked_keywords:
                kw = kw_obj.keyword
                kw_tasks = []
                
                # YouTube search for keyword
                if api_key:
                    kw_tasks.append(fetch_youtube_for_keyword(kw, api_key, region))
                
                # Reddit search for keyword
                kw_tasks.append(fetch_reddit_search(kw, region))

                kw_results = await asyncio.gather(*kw_tasks, return_exceptions=True)
                for r in kw_results:
                    if isinstance(r, list):
                        all_items.extend(r)
                    else:
                        stats["errors"] += 1
                stats["keywords"] += 1

        # Clean up old records (>7 days)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        await db.execute(delete(SocialPulse).where(SocialPulse.fetched_at < cutoff))

        # Save new records (deduplicated by title)
        seen_titles = set()
        
        # Get existing titles from last 24h to avoid immediate dupes
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        existing_result = await db.execute(
            select(SocialPulse.title).where(SocialPulse.fetched_at > yesterday)
        )
        existing_titles = set(existing_result.scalars().all())

        for item in all_items:
            title = item["title"][:500]
            if title in seen_titles or title in existing_titles:
                continue
            
            seen_titles.add(title)
            
            pulse = SocialPulse(
                platform=item["platform"],
                category=item["category"],
                title=title,
                url=item.get("url"),
                description=item.get("description"),
                metrics=item.get("metrics", {}),
                sentiment=item.get("sentiment", "neutral"),
                region=item.get("region", region),
                niche_id=item.get("niche_id"),
                tags=item.get("tags", []),
                raw_data=None,
            )
            db.add(pulse)

        await db.commit()
        stats["fetched"] = len(all_items)

        # Prune low-signal items (virality_score < 60) to keep the DB lean
        from sqlalchemy import cast, Float, text
        prune_result = await db.execute(
            text(
                "DELETE FROM social_pulses "
                "WHERE COALESCE(CAST(metrics->>'virality_score' AS FLOAT), 0) < 60"
            )
        )
        await db.commit()
        stats["pruned"] = prune_result.rowcount

    logger.info(f"[SocialPulse] Refresh complete: {stats}")
    return stats


async def fetch_youtube_for_keyword(keyword: str, api_key: str, region: str = "US") -> list[dict]:
    """Search YouTube for a specific keyword (100 units/call)."""
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "relevance",
        "publishedAfter": (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "maxResults": 5,
        "key": api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://www.googleapis.com/youtube/v3/search", params=params)
            if not resp.is_success:
                return []
            data = resp.json()

        results = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            vid_id = item.get("id", {}).get("videoId", "")
            title = snippet.get("title", "")
            virality = calculate_virality_score({"velocity": 50, "growth_pct": 50, "freshness_hours": 24})
            results.append({
                "platform": "youtube",
                "category": "search",
                "title": title,
                "url": f"https://youtube.com/watch?v={vid_id}" if vid_id else None,
                "description": snippet.get("description", "")[:300],
                "metrics": {"velocity": 50, "growth_pct": 50, "freshness_hours": 24, "virality_score": virality},
                "sentiment": analyze_sentiment(title),
                "region": region,
                "tags": ["youtube", "keyword", keyword],
            })
        return results
    except Exception as e:
        logger.warning(f"YouTube keyword fetch failed for '{keyword}': {e}")
        return []


async def fetch_reddit_search(keyword: str, region: str = "US") -> list[dict]:
    """Search Reddit for a specific keyword."""
    url = f"https://www.reddit.com/search.json?q={keyword}&sort=relevance&t=week&limit=5"
    try:
        async with httpx.AsyncClient(headers=REDDIT_HEADERS, timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)
            if not resp.is_success:
                return []
            data = resp.json()
        
        items = []
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            title = p.get("title", "")
            age_hours = max(0, (datetime.now(timezone.utc).timestamp() - p.get("created_utc", 0)) / 3600)
            virality = calculate_virality_score({
                "velocity": min(p.get("score", 0) / 50, 100),
                "growth_pct": min(p.get("upvote_ratio", 0.5) * 100, 100),
                "freshness_hours": age_hours,
            })
            items.append({
                "platform": "reddit",
                "category": "search",
                "title": title,
                "url": f"https://reddit.com{p.get('permalink', '')}",
                "description": f"r/{p.get('subreddit')} • {p.get('score', 0)} upvotes",
                "metrics": {
                    "score": p.get("score", 0),
                    "velocity": min(p.get("score", 0) / 50, 100),
                    "freshness_hours": age_hours,
                    "virality_score": virality,
                },
                "sentiment": analyze_sentiment(title),
                "region": region,
                "tags": ["reddit", "keyword", keyword],
            })
        return items
    except Exception:
        return []
