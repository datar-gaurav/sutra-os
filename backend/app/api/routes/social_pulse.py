"""Social Pulse API routes — trending content research dashboard."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.social_pulse import PulseNiche, SocialPulse, TrendKeyword

router = APIRouter(prefix="/social-pulse", tags=["social-pulse"])
logger = logging.getLogger(__name__)


# ── Dashboard ──────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    niche_id: str | None = Query(None),
    region: str = Query("US"),
    tracked_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard summary: grouped platform data + top viral items."""
    # Base query
    stmt = select(SocialPulse)
    
    if tracked_only:
        # Fetch active keywords
        kw_result = await db.execute(select(TrendKeyword).where(TrendKeyword.is_active == True))
        keywords = [k.keyword.lower() for k in kw_result.scalars().all()]
        if keywords:
            from sqlalchemy import or_
            conditions = [SocialPulse.title.ilike(f"%{kw}%") for kw in keywords]
            stmt = stmt.where(or_(*conditions))
        else:
            # If no keywords are tracked and tracked_only is requested, return empty structures
            return {
                "total_trending": 0,
                "viral_count": 0,
                "active_niches": 0,
                "keyword_count": 0,
                "last_refreshed": None,
                "by_platform": {},
                "top_viral": [],
            }

    if niche_id:
        stmt = stmt.where(SocialPulse.niche_id == niche_id)

    result = await db.execute(stmt.order_by(desc(SocialPulse.fetched_at)).limit(500))
    pulses = result.scalars().all()

    # Group by platform (with deduplication)
    by_platform: dict[str, list] = {}
    seen_titles_global = set()
    for p in pulses:
        if p.title in seen_titles_global:
            continue
        seen_titles_global.add(p.title)
        
        platform = p.platform
        if platform not in by_platform:
            by_platform[platform] = []
        virality = p.metrics.get("virality_score", 0) if p.metrics else 0
        by_platform[platform].append({
            "id": p.id,
            "title": p.title,
            "url": p.url,
            "virality_score": virality,
            "sentiment": p.sentiment,
            "fetched_at": p.fetched_at.isoformat() if p.fetched_at else None,
            "niche_id": p.niche_id,
        })

    # Top viral across all platforms
    all_items = []
    seen_titles_top = set()
    for p in pulses:
        if p.title in seen_titles_top:
            continue
        seen_titles_top.add(p.title)
        
        all_items.append({
            "id": p.id,
            "platform": p.platform,
            "category": p.category,
            "title": p.title,
            "url": p.url,
            "description": p.description,
            "metrics": p.metrics or {},
            "virality_score": (p.metrics or {}).get("virality_score", 0),
            "sentiment": p.sentiment,
            "region": p.region,
            "niche_id": p.niche_id,
            "tags": p.tags or [],
            "fetched_at": p.fetched_at.isoformat() if p.fetched_at else None,
        })
    
    top_viral = sorted(all_items, key=lambda x: x["virality_score"], reverse=True)[:10]

    # Counts
    keyword_count_result = await db.execute(
        select(func.count()).where(TrendKeyword.is_active == True)
    )
    keyword_count = keyword_count_result.scalar() or 0

    niche_count_result = await db.execute(
        select(func.count()).where(PulseNiche.is_active == True)
    )
    niche_count = niche_count_result.scalar() or 0

    # Last refresh time
    latest = pulses[0].fetched_at if pulses else None

    viral_count = sum(1 for item in all_items if item["virality_score"] > 70)

    return {
        "total_trending": len(pulses),
        "viral_count": viral_count,
        "active_niches": niche_count,
        "keyword_count": keyword_count,
        "last_refreshed": latest.isoformat() if latest else None,
        "by_platform": {k: v[:10] for k, v in by_platform.items()},
        "top_viral": top_viral,
    }


# ── Trends list ────────────────────────────────────────────────────────────────

@router.get("/trends")
async def list_trends(
    platform: str | None = Query(None),
    category: str | None = Query(None),
    region: str | None = Query(None),
    niche_id: str | None = Query(None),
    tracked_only: bool = Query(False),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get filtered list of trend items sorted by virality."""
    stmt = select(SocialPulse)
    
    if tracked_only:
        # Fetch active keywords
        kw_result = await db.execute(select(TrendKeyword).where(TrendKeyword.is_active == True))
        keywords = [k.keyword.lower() for k in kw_result.scalars().all()]
        if keywords:
            # Use ilike or a combined regex for filtering by title
            # For simplicity and performance with small keyword lists, we'll use OR with ilike
            from sqlalchemy import or_
            conditions = [SocialPulse.title.ilike(f"%{kw}%") for kw in keywords]
            stmt = stmt.where(or_(*conditions))
        else:
            # If no keywords are tracked, return empty list for tracked_only
            return []

    if platform:
        stmt = stmt.where(SocialPulse.platform == platform)
    if category:
        stmt = stmt.where(SocialPulse.category == category)
    if region:
        stmt = stmt.where(SocialPulse.region == region)
    if niche_id:
        stmt = stmt.where(SocialPulse.niche_id == niche_id)

    result = await db.execute(stmt.order_by(desc(SocialPulse.fetched_at)).limit(limit * 3))
    pulses = result.scalars().all()

    items = []
    seen_titles = set()
    for p in pulses:
        if p.title in seen_titles:
            continue
        seen_titles.add(p.title)
        
        items.append({
            "id": p.id,
            "platform": p.platform,
            "category": p.category,
            "title": p.title,
            "url": p.url,
            "description": p.description,
            "metrics": p.metrics or {},
            "virality_score": (p.metrics or {}).get("virality_score", 0),
            "sentiment": p.sentiment,
            "region": p.region,
            "niche_id": p.niche_id,
            "tags": p.tags or [],
            "fetched_at": p.fetched_at.isoformat() if p.fetched_at else None,
        })
    return sorted(items, key=lambda x: x["virality_score"], reverse=True)[:limit]


# ── Niches ─────────────────────────────────────────────────────────────────────

@router.get("/niches")
async def list_niches(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PulseNiche).order_by(PulseNiche.is_builtin.desc(), PulseNiche.name))
    niches = result.scalars().all()
    return [
        {
            "id": n.id,
            "name": n.name,
            "description": n.description,
            "is_active": n.is_active,
            "is_builtin": n.is_builtin,
            "google_trends_keywords": n.google_trends_keywords or [],
            "subreddits": n.subreddits or [],
            "youtube_category_ids": n.youtube_category_ids or [],
            "color": n.color,
            "created_at": n.created_at.isoformat(),
        }
        for n in niches
    ]


@router.post("/niches", status_code=201)
async def create_niche(body: dict, db: AsyncSession = Depends(get_db)):
    niche = PulseNiche(
        name=body.get("name", ""),
        description=body.get("description"),
        google_trends_keywords=body.get("google_trends_keywords", []),
        subreddits=body.get("subreddits", []),
        youtube_category_ids=body.get("youtube_category_ids", []),
        color=body.get("color"),
        is_active=body.get("is_active", True),
    )
    db.add(niche)
    await db.commit()
    await db.refresh(niche)
    return {"id": niche.id, "name": niche.name, "message": "Niche created"}


@router.put("/niches/{niche_id}")
async def update_niche(niche_id: str, body: dict, db: AsyncSession = Depends(get_db)):
    niche = await db.get(PulseNiche, niche_id)
    if not niche:
        raise HTTPException(status_code=404, detail="Niche not found")
    for field in ["name", "description", "google_trends_keywords", "subreddits", "youtube_category_ids", "color", "is_active"]:
        if field in body:
            setattr(niche, field, body[field])
    await db.commit()
    return {"message": "Updated"}


@router.delete("/niches/{niche_id}", status_code=204)
async def delete_niche(niche_id: str, db: AsyncSession = Depends(get_db)):
    niche = await db.get(PulseNiche, niche_id)
    if not niche:
        raise HTTPException(status_code=404, detail="Niche not found")
    if niche.is_builtin:
        raise HTTPException(status_code=400, detail="Cannot delete built-in niches — deactivate instead")
    await db.delete(niche)
    await db.commit()


# ── Keywords ───────────────────────────────────────────────────────────────────

@router.get("/keywords")
async def list_keywords(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrendKeyword).order_by(TrendKeyword.created_at.desc()))
    kws = result.scalars().all()
    return [
        {
            "id": k.id,
            "keyword": k.keyword,
            "is_active": k.is_active,
            "platforms": k.platforms or [],
            "created_at": k.created_at.isoformat(),
        }
        for k in kws
    ]


@router.post("/keywords", status_code=201)
async def add_keyword(body: dict, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.exc import IntegrityError
    kw = TrendKeyword(
        keyword=body.get("keyword", "").strip(),
        platforms=body.get("platforms", ["google_trends", "youtube", "reddit"]),
    )
    db.add(kw)
    try:
        await db.commit()
        await db.refresh(kw)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Keyword already tracked")
    return {"id": kw.id, "keyword": kw.keyword}


@router.delete("/keywords/{keyword_id}", status_code=204)
async def delete_keyword(keyword_id: str, db: AsyncSession = Depends(get_db)):
    kw = await db.get(TrendKeyword, keyword_id)
    if not kw:
        raise HTTPException(status_code=404, detail="Keyword not found")
    await db.delete(kw)
    await db.commit()


# ── Platform status ────────────────────────────────────────────────────────────

@router.get("/status")
async def get_platform_status():
    """Test connectivity to each data source and return status."""
    import httpx as _httpx
    from app.config import settings

    results = {}

    # Google Trends RSS
    try:
        async with _httpx.AsyncClient(timeout=10, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get("https://trends.google.com/trending/rss?geo=US")
        results["google_trends"] = {"ok": resp.is_success, "status": resp.status_code, "note": "RSS feed"}
    except Exception as e:
        results["google_trends"] = {"ok": False, "error": str(e)}

    # YouTube
    api_key = settings.google_api_key
    if not api_key:
        results["youtube"] = {"ok": False, "error": "GOOGLE_API_KEY not set in .env"}
    else:
        try:
            async with _httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={"part": "snippet", "chart": "mostPopular", "regionCode": "US", "maxResults": 1, "key": api_key},
                )
            data = resp.json()
            if resp.is_success:
                results["youtube"] = {"ok": True, "status": 200}
            else:
                err = data.get("error", {})
                err_message = err.get("message", "")
                if "SERVICE_DISABLED" in str(err) or "disabled" in err_message.lower():
                    results["youtube"] = {
                        "ok": False,
                        "error": "YouTube Data API v3 not enabled",
                        "fix": "https://console.developers.google.com/apis/api/youtube.googleapis.com/overview",
                    }
                elif "blocked" in err_message.lower() or "restricted" in err_message.lower():
                    results["youtube"] = {
                        "ok": False,
                        "error": "API Key is blocked or restricted",
                        "note": "Check API key restrictions in Google Cloud Console",
                        "fix": "https://console.cloud.google.com/apis/credentials",
                    }
                else:
                    results["youtube"] = {"ok": False, "error": err_message or f"HTTP {resp.status_code}"}
        except Exception as e:
            results["youtube"] = {"ok": False, "error": str(e)}

    # Reddit
    try:
        async with _httpx.AsyncClient(timeout=10,
            headers={"User-Agent": "SutraSocialPulse/1.0"}) as client:
            resp = await client.get("https://www.reddit.com/r/technology/hot.json?limit=1")
        results["reddit"] = {"ok": resp.is_success, "status": resp.status_code}
    except Exception as e:
        results["reddit"] = {"ok": False, "error": str(e)}

    # Hacker News
    try:
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
        results["hackernews"] = {"ok": resp.is_success, "status": resp.status_code}
    except Exception as e:
        results["hackernews"] = {"ok": False, "error": str(e)}

    return results


# ── Purge all data ─────────────────────────────────────────────────────────────

@router.delete("/purge", status_code=200)
async def purge_all_data(db: AsyncSession = Depends(get_db)):
    """Delete all social pulse trend items from every platform."""
    from sqlalchemy import delete
    result = await db.execute(delete(SocialPulse))
    await db.commit()
    return {"deleted": result.rowcount, "message": f"Purged {result.rowcount} trend items"}


@router.delete("/purge-low-score", status_code=200)
async def purge_low_score(min_score: float = 60, db: AsyncSession = Depends(get_db)):
    """Delete all trend items with virality_score below min_score (default 60)."""
    from sqlalchemy import text
    result = await db.execute(
        text(
            "DELETE FROM social_pulses "
            "WHERE COALESCE(CAST(metrics->>'virality_score' AS FLOAT), 0) < :min_score"
        ),
        {"min_score": min_score},
    )
    await db.commit()
    return {"deleted": result.rowcount, "message": f"Removed {result.rowcount} items below score {min_score}"}


# ── Manual refresh ─────────────────────────────────────────────────────────────

@router.post("/refresh")
async def trigger_refresh(
    background_tasks: BackgroundTasks,
    region: str = Query("US"),
):
    """Manually trigger a Social Pulse data refresh (runs in background)."""
    from app.core.social_pulse_service import refresh_all_platforms

    async def _run():
        try:
            await refresh_all_platforms(region)
        except Exception as e:
            logger.error(f"Manual refresh failed: {e}")

    background_tasks.add_task(_run)
    return {"message": "Refresh started in background", "region": region}


# ── AI Insights ────────────────────────────────────────────────────────────────

@router.get("/models")
async def list_available_models():
    """Return LLM providers/models that have API keys configured."""
    from app.config import settings
    available = []
    if settings.anthropic_api_key:
        available += [
            {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "label": "Claude Haiku (fast)"},
            {"provider": "anthropic", "model": "claude-sonnet-4-6", "label": "Claude Sonnet (smart)"},
        ]
    if settings.google_api_key:
        available += [
            {"provider": "google", "model": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
            {"provider": "google", "model": "gemini-1.5-flash", "label": "Gemini 1.5 Flash"},
        ]
    if settings.openai_api_key:
        available += [
            {"provider": "openai", "model": "gpt-4o-mini", "label": "GPT-4o Mini"},
            {"provider": "openai", "model": "gpt-4o", "label": "GPT-4o"},
        ]
    if settings.groq_api_key:
        available += [
            {"provider": "groq", "model": "moonshotai/kimi-k2-instruct", "label": "Kimi K2 (Groq)"},
            {"provider": "groq", "model": "llama-3.1-8b-instant", "label": "Llama 3.1 8B (Groq)"},
        ]
    return available


class InsightsRequest(BaseModel):
    niche_id: str | None = None
    provider: str = "groq"
    model: str = "moonshotai/kimi-k2-instruct"
    queued_titles: list[str] = []
    tracked_keywords: list[str] = []


@router.post("/insights")
async def get_insights(
    body: InsightsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Context-aware LLM analysis: considers virality, tracked keywords, content queue, and deduplication."""
    from langchain_core.messages import HumanMessage

    # ── Fetch trending items ───────────────────────────────────────────────────
    stmt = select(SocialPulse)
    if body.niche_id:
        stmt = stmt.where(SocialPulse.niche_id == body.niche_id)
    result = await db.execute(stmt.order_by(desc(SocialPulse.fetched_at)).limit(200))
    pulses = result.scalars().all()

    if not pulses:
        return {"insights": "No trend data available. Run a refresh first."}

    # ── Pull tracked keywords from DB if not provided ──────────────────────────
    tracked_keywords = list(body.tracked_keywords)
    if not tracked_keywords:
        kw_result = await db.execute(select(TrendKeyword).where(TrendKeyword.is_active == True))  # noqa: E712
        tracked_keywords = [k.keyword for k in kw_result.scalars().all()]

    # ── Deduplicate by title similarity (keep highest virality per group) ───────
    seen_prefixes: set[str] = set()
    deduped: list[dict] = []
    for p in sorted(pulses, key=lambda x: (x.metrics or {}).get("virality_score", 0), reverse=True):
        # Use first 6 words as a fingerprint
        fingerprint = " ".join((p.title or "").lower().split()[:6])
        if fingerprint in seen_prefixes:
            continue
        seen_prefixes.add(fingerprint)
        deduped.append({
            "title": p.title,
            "platform": p.platform,
            "virality_score": round((p.metrics or {}).get("virality_score", 0), 1),
            "sentiment": p.sentiment or "neutral",
            "url": p.url,
        })

    top_items = deduped[:30]

    # ── Build prompt sections ──────────────────────────────────────────────────
    trending_lines = "\n".join(
        f"  {i+1}. [{item['platform'].upper():<14}] "
        f"virality={item['virality_score']:>5.1f} | "
        f"sentiment={item['sentiment']:<8} | "
        f"{item['title']}"
        for i, item in enumerate(top_items)
    )

    keyword_section = ""
    if tracked_keywords:
        kw_matches = []
        for item in top_items:
            matched = [kw for kw in tracked_keywords if kw.lower() in (item["title"] or "").lower()]
            if matched:
                kw_matches.append(f"  - '{item['title']}' matches keywords: {', '.join(matched)}")
        keyword_section = f"""

🔑 USER'S TRACKED KEYWORDS: {', '.join(tracked_keywords)}
{'Keyword matches in current trends:' + chr(10) + chr(10).join(kw_matches) if kw_matches else 'No direct keyword matches found in current trends.'}
"""

    queue_section = ""
    if body.queued_titles:
        queue_lines = "\n".join(f"  - {t}" for t in body.queued_titles)
        queue_section = f"""

📋 USER'S CONTENT QUEUE (already selected — do NOT recommend these again):
{queue_lines}
"""

    prompt = f"""You are a content strategist analyzing real-time internet trends to recommend the most interesting and high-potential content themes.

📊 TRENDING CONTENT (sorted by virality, deduplicated):
{trending_lines}
{keyword_section}{queue_section}

Based on ALL of the above context, provide a strategic content recommendation:

1. **TOP 3 FRESH CONTENT OPPORTUNITIES** — choose topics NOT in the queue above, ranked by:
   - Virality score (higher = more traction)
   - Keyword alignment (prefer topics matching tracked keywords)
   - Cross-platform presence (trending on multiple sources = stronger signal)
   - Uniqueness (avoid recommending what the user already queued)

2. **EMERGING THEME** — identify the single biggest narrative thread across platforms right now (2-3 sentences)

3. **BEST ANGLE** — for the #1 recommendation, suggest a specific content angle/hook that would stand out (1-2 sentences)

4. **KEYWORD GAP** — if tracked keywords have no strong trending matches, flag it briefly

Be concise, specific, and actionable. Reference actual titles from the data. Total: 8-12 sentences."""

    try:
        from app.core.llm_registry import llm_registry
        llm = llm_registry.get_chat_model(
            provider=body.provider, model=body.model, temperature=0.4, streaming=False
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return {
            "insights": response.content,
            "items_analyzed": len(top_items),
            "model": f"{body.provider}/{body.model}",
            "keywords_used": tracked_keywords,
            "queue_size": len(body.queued_titles),
        }
    except Exception as e:
        logger.warning(f"LLM insights failed ({body.provider}/{body.model}): {e}")
        return {"insights": f"Could not generate insights: {e}", "items_analyzed": len(top_items)}


@router.post("/themes")
async def get_themes(
    body: InsightsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Identify 3-5 prominent themes from current trend data using LLM."""
    from langchain_core.messages import HumanMessage
    import json

    # Fetch trending items
    stmt = select(SocialPulse)
    if body.niche_id:
        stmt = stmt.where(SocialPulse.niche_id == body.niche_id)
    result = await db.execute(stmt.order_by(desc(SocialPulse.fetched_at)).limit(150))
    pulses = result.scalars().all()

    if not pulses:
        return []

    # Deduplicate by title
    seen_titles = set()
    items = []
    for p in pulses:
        if p.title in seen_titles: continue
        seen_titles.add(p.title)
        items.append({
            "title": p.title,
            "platform": p.platform,
            "virality": round((p.metrics or {}).get("virality_score", 0), 1)
        })

    # Prepare data for prompt
    data_str = "\n".join([f"- [{i['platform']}] {i['title']} (virality: {i['virality']})" for i in items[:50]])

    prompt = f"""Analyze the following trending content and identify 3-5 prominent "themes" or "narratives" that are emerging.
A theme should group multiple related items together.

TRENDING DATA:
{data_str}

Return ONLY a valid JSON list of objects with this structure:
[
  {{
    "theme": "Short Theme Name",
    "description": "1-2 sentence description of why this is trending and what it's about.",
    "virality_score": 0-100 (average of related items),
    "related_platforms": ["reddit", "youtube"],
    "keywords": ["keyword1", "keyword2"]
  }}
]
"""

    try:
        from app.core.llm_registry import llm_registry
        llm = llm_registry.get_chat_model(
            provider=body.provider, model=body.model, temperature=0.2, streaming=False
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        
        # Clean response if it contains markdown code blocks
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        themes = json.loads(content)
        return themes
    except Exception as e:
        logger.warning(f"Theme generation failed: {e}")
        return []
