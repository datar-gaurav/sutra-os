"""LLM provider pricing model — cost per 1K tokens per provider/model."""

from sqlalchemy import Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid

# Built-in pricing defaults (USD per 1K tokens, approximate 2025 rates)
# Format: (provider, model, input_per_1k, output_per_1k)
DEFAULT_PRICING: list[tuple[str, str, float, float]] = [
    # OpenAI
    ("openai", "gpt-4o",                 0.0025,  0.0100),
    ("openai", "gpt-4o-mini",            0.00015, 0.0006),
    ("openai", "gpt-4-turbo",            0.010,   0.030),
    ("openai", "gpt-4",                  0.030,   0.060),
    ("openai", "gpt-3.5-turbo",          0.0005,  0.0015),
    ("openai", "o1",                     0.015,   0.060),
    ("openai", "o1-mini",                0.003,   0.012),
    # Anthropic
    ("anthropic", "claude-opus-4-7",             0.015,   0.075),
    ("anthropic", "claude-sonnet-4-6",       0.003,   0.015),
    ("anthropic", "claude-haiku-4-5-20251001",      0.0008,  0.004),
    ("anthropic", "claude-3-5-sonnet-20241022",   0.003,   0.015),
    ("anthropic", "claude-3-5-haiku-20241022",    0.0008,  0.004),
    ("anthropic", "claude-3-opus-20240229",       0.015,   0.075),
    # Google
    ("google", "gemini-1.5-pro",         0.00125, 0.005),
    ("google", "gemini-1.5-flash",       0.000075,0.0003),
    ("google", "gemini-2.0-flash",       0.0001,  0.0004),
    ("google", "gemini-2.5-pro",         0.00125, 0.010),
    # Groq
    ("groq", "llama-3.3-70b-versatile",  0.00059, 0.00079),
    ("groq", "llama-3.1-8b-instant",     0.00005, 0.00008),
    ("groq", "mixtral-8x7b-32768",       0.00024, 0.00024),
    # Default wildcard (very cheap estimate for unknown models)
    ("*", "*", 0.001, 0.002),
]


class ModelPricing(Base, TimestampMixin):
    """Stores cost per 1K tokens for a provider/model pair.

    Use provider='*' and model='*' as a catch-all fallback.
    """

    __tablename__ = "model_pricing"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    # USD cost per 1,000 tokens
    input_cost_per_1k: Mapped[float] = mapped_column(Float, nullable=False, default=0.001)
    output_cost_per_1k: Mapped[float] = mapped_column(Float, nullable=False, default=0.002)

    __table_args__ = (
        UniqueConstraint("provider", "model", name="uq_pricing_provider_model"),
    )

    @property
    def blended_cost_per_1k(self) -> float:
        """Average of input + output cost — used when input/output tokens aren't tracked separately."""
        return (self.input_cost_per_1k + self.output_cost_per_1k) / 2

    def __repr__(self) -> str:
        return f"<ModelPricing {self.provider}/{self.model} in=${self.input_cost_per_1k} out=${self.output_cost_per_1k}>"
