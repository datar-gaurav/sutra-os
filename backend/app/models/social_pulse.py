"""Social Pulse models — trending content research."""

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class PulseNiche(Base, TimestampMixin):
    """User-defined niche to focus social pulse research."""

    __tablename__ = "pulse_niches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Seed terms for each platform
    google_trends_keywords: Mapped[list] = mapped_column(JSON, default=list)
    subreddits: Mapped[list] = mapped_column(JSON, default=list)
    youtube_category_ids: Mapped[list] = mapped_column(JSON, default=list)

    # UI display
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)


class SocialPulse(Base, TimestampMixin):
    """Single trending/viral content item fetched from a platform."""

    __tablename__ = "social_pulses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # google_trends|youtube|reddit|hackernews
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # trending|rising|viral|keyword_track
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metrics: views, likes, comments, score, velocity, growth_pct, virality_score
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)

    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)  # positive|negative|neutral|mixed
    region: Mapped[str] = mapped_column(String(10), default="US", nullable=False)

    niche_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("pulse_niches.id", ondelete="SET NULL"), nullable=True
    )
    tags: Mapped[list] = mapped_column(JSON, default=list)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_social_pulses_platform", "platform"),
        Index("ix_social_pulses_niche_id", "niche_id"),
        Index("ix_social_pulses_fetched_at", "fetched_at"),
    )


class TrendKeyword(Base, TimestampMixin):
    """User-tracked keywords to monitor across platforms."""

    __tablename__ = "trend_keywords"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    keyword: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    platforms: Mapped[list] = mapped_column(
        JSON, default=lambda: ["google_trends", "youtube", "reddit"]
    )


# ── Built-in niches seeded on startup ─────────────────────────────────────────

BUILTIN_NICHES = [
    {
        "name": "Technology",
        "description": "AI, SaaS, Startups, Developer Tools",
        "google_trends_keywords": ["artificial intelligence", "machine learning", "SaaS", "startup", "ChatGPT", "LLM"],
        "subreddits": ["technology", "MachineLearning", "artificial", "LocalLLaMA", "singularity", "programming"],
        "youtube_category_ids": [28],  # Science & Technology
        "color": "#6366f1",
    },
    {
        "name": "Business & Finance",
        "description": "Crypto, Stock Market, Entrepreneurship",
        "google_trends_keywords": ["bitcoin", "stock market", "entrepreneurship", "investing", "crypto"],
        "subreddits": ["CryptoCurrency", "stocks", "investing", "entrepreneur", "wallstreetbets"],
        "youtube_category_ids": [25],  # News & Politics
        "color": "#10b981",
    },
    {
        "name": "Marketing & Social Media",
        "description": "Digital marketing, growth hacking, content strategy",
        "google_trends_keywords": ["digital marketing", "content marketing", "social media", "SEO", "growth hacking"],
        "subreddits": ["marketing", "socialmedia", "SEO", "content_marketing", "growthhacking"],
        "youtube_category_ids": [22],  # People & Blogs
        "color": "#f59e0b",
    },
    {
        "name": "Health & Fitness",
        "description": "Wellness, fitness trends, nutrition",
        "google_trends_keywords": ["fitness", "weight loss", "keto diet", "mental health", "meditation"],
        "subreddits": ["fitness", "loseit", "nutrition", "yoga", "running"],
        "youtube_category_ids": [26],  # How-to & Style
        "color": "#ef4444",
    },
    {
        "name": "Entertainment",
        "description": "Movies, music, pop culture",
        "google_trends_keywords": ["new movie", "trending music", "celebrity", "viral video", "Netflix"],
        "subreddits": ["movies", "music", "television", "popculture", "entertainment"],
        "youtube_category_ids": [24],  # Entertainment
        "color": "#8b5cf6",
    },
    {
        "name": "Gaming",
        "description": "Video games, esports, game releases",
        "google_trends_keywords": ["video games", "esports", "game release", "gaming PC", "Twitch"],
        "subreddits": ["gaming", "games", "pcgaming", "esports", "leagueoflegends"],
        "youtube_category_ids": [20],  # Gaming
        "color": "#06b6d4",
    },
    {
        "name": "Science & Education",
        "description": "Scientific discoveries, online learning",
        "google_trends_keywords": ["science news", "space exploration", "climate change", "online learning", "research"],
        "subreddits": ["science", "space", "education", "askscience", "futurology"],
        "youtube_category_ids": [27],  # Education
        "color": "#84cc16",
    },
]
