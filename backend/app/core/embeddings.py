"""Embedding service with fallback chain: OpenAI → Ollama → keyword similarity.

Includes a batch embedding queue that collects requests and flushes in batches
to reduce API calls (N individual calls → ceil(N/batch_size) batch calls).
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Lazy-initialized embedding service. Falls back gracefully if no model is available."""

    def __init__(self):
        self._embedder = None
        self._initialized = False

    def _init_embedder(self):
        if self._initialized:
            return
        self._initialized = True

        # 1. Try OpenAI (text-embedding-3-small — fast, cheap, 1536-dim)
        try:
            from langchain_openai import OpenAIEmbeddings
            from app.config import settings
            if settings.openai_api_key:
                self._embedder = OpenAIEmbeddings(
                    model="text-embedding-3-small",
                    api_key=settings.openai_api_key,
                )
                logger.info("Embedding service: OpenAI text-embedding-3-small")
                return
        except Exception as e:
            logger.debug(f"OpenAI embeddings unavailable: {e}")

        # 2. Try Ollama (nomic-embed-text — local, no API key, 768-dim)
        try:
            from langchain_ollama import OllamaEmbeddings
            from app.config import settings
            embedder = OllamaEmbeddings(
                model="nomic-embed-text",
                base_url=settings.ollama_base_url,
            )
            # Quick connection test
            embedder.embed_query("test")
            self._embedder = embedder
            logger.info("Embedding service: Ollama nomic-embed-text")
            return
        except Exception as e:
            logger.debug(f"Ollama embeddings unavailable: {e}")

        logger.warning(
            "No embedding model available — memory search will use keyword matching."
        )

    def embed(self, text: str) -> list[float] | None:
        self._init_embedder()
        if not self._embedder:
            return None
        try:
            return self._embedder.embed_query(text)
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return None

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Embed multiple texts in a single API call where possible."""
        self._init_embedder()
        if not self._embedder:
            return [None] * len(texts)
        try:
            return self._embedder.embed_documents(texts)
        except Exception as e:
            logger.error(f"Batch embedding failed, falling back to individual: {e}")
            return [self.embed(t) for t in texts]

    async def aembed(self, text: str) -> list[float] | None:
        """Async wrapper — routes through batcher for efficiency."""
        return await embedding_batcher.embed(text)

    async def aembed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Async batch embed — runs sync batch in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_batch, texts)


class EmbeddingBatcher:
    """
    Queues individual embedding requests and flushes in batches.
    Reduces API calls from N to ceil(N/batch_size).

    How it works:
    1. Each call to embed() adds text to a queue and returns a Future.
    2. When the queue reaches batch_size OR flush_interval passes, the batch is processed.
    3. Results are distributed back to the waiting Futures.
    """

    def __init__(self, batch_size: int = 20, flush_interval: float = 0.3):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue: list[tuple[str, asyncio.Future]] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None

        # Stats
        self.batches_processed = 0
        self.items_processed = 0

    async def embed(self, text: str) -> list[float] | None:
        """Queue a single text for batch embedding. Returns when the batch is processed."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        async with self._lock:
            self._queue.append((text, future))

            if len(self._queue) >= self.batch_size:
                await self._flush()
            elif len(self._queue) == 1 and (self._flush_task is None or self._flush_task.done()):
                # Single request: use a very short delay to allow batching without
                # adding noticeable latency for the common single-request case
                self._flush_task = asyncio.create_task(self._delayed_flush(0.01))
            elif self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._delayed_flush(self.flush_interval))

        return await future

    async def _delayed_flush(self, delay: float | None = None):
        """Wait briefly then flush whatever is in the queue."""
        await asyncio.sleep(delay if delay is not None else self.flush_interval)
        async with self._lock:
            await self._flush()

    async def _flush(self):
        """Process the current queue as a batch."""
        if not self._queue:
            return

        batch = self._queue[:]
        self._queue.clear()
        self._flush_task = None

        texts = [t for t, _ in batch]
        self.batches_processed += 1
        self.items_processed += len(texts)

        try:
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None, embedding_service.embed_batch, texts
            )
            for (_, future), embedding in zip(batch, embeddings):
                if not future.done():
                    future.set_result(embedding)
        except Exception as e:
            logger.error(f"Batch embedding flush failed: {e}")
            for _, future in batch:
                if not future.done():
                    future.set_result(None)

    @property
    def stats(self) -> dict:
        return {
            "queue_size": len(self._queue),
            "batches_processed": self.batches_processed,
            "items_processed": self.items_processed,
            "batch_size": self.batch_size,
        }


# Global singletons
embedding_service = EmbeddingService()
def _create_batcher() -> EmbeddingBatcher:
    try:
        from app.core.system_settings import sys_settings
        return EmbeddingBatcher(
            batch_size=sys_settings.get("embedding_batch_size") or 20,
            flush_interval=sys_settings.get("embedding_flush_interval") or 0.3,
        )
    except Exception:
        return EmbeddingBatcher(batch_size=20, flush_interval=0.3)

embedding_batcher = _create_batcher()
