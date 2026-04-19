"""RAG service — document ingestion, chunking, embedding, and retrieval."""

import json
import logging
import math
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import embedding_service
from app.core.tracing import set_attrs, span
from app.models.knowledge_base import Document, DocumentChunk, DocumentSourceType, DocumentStatus

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000    # characters per chunk
CHUNK_OVERLAP = 150  # character overlap between chunks


# ─── Similarity Helpers ───────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x**2 for x in a))
    mag_b = math.sqrt(sum(x**2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _keyword_score(query: str, content: str) -> float:
    qwords = set(query.lower().split())
    cwords = set(content.lower().split())
    if not qwords:
        return 0.0
    return len(qwords & cwords) / len(qwords)


# ─── Text Extraction ──────────────────────────────────────────────────────────

def _split_text(text: str) -> list[str]:
    """Split text into overlapping chunks using LangChain's splitter."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
    return splitter.split_text(text)


async def _fetch_url_text(url: str) -> str:
    """Fetch and extract readable text from a URL."""
    import httpx
    from bs4 import BeautifulSoup

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Sutra RAG)"})
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _extract_pdf_text(raw_bytes: bytes) -> str:
    """Extract text from PDF bytes using pypdf."""
    try:
        import io
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        pages = [page.extract_text() for page in reader.pages if page.extract_text()]
        return "\n\n".join(pages)
    except ImportError:
        raise ValueError("pypdf is not installed. Run: pip install pypdf")


# ─── Ingestion ────────────────────────────────────────────────────────────────

async def process_document(db: AsyncSession, document_id: str) -> None:
    """Extract text from a document, chunk it, embed each chunk, and store."""
    doc = await db.get(Document, document_id)
    if not doc:
        return

    doc.status = DocumentStatus.processing
    await db.flush()

    try:
        # 1. Get raw text
        raw_text = ""
        if doc.source_type == DocumentSourceType.url:
            if not doc.source_url:
                raise ValueError("source_url is required for URL documents")
            raw_text = await _fetch_url_text(doc.source_url)
            # Store extracted text
            doc.content = raw_text[:50_000]  # cap stored raw text at 50k chars
        elif doc.source_type in (DocumentSourceType.text, DocumentSourceType.file):
            raw_text = doc.content or ""

        if not raw_text.strip():
            doc.status = DocumentStatus.failed
            doc.error_message = "No text content extracted from source"
            return

        # 2. Split into chunks
        chunks = _split_text(raw_text)
        if not chunks:
            doc.status = DocumentStatus.failed
            doc.error_message = "Text splitting produced no chunks"
            return

        # 3. Remove any old chunks (re-ingestion support)
        old_chunks = await db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        for old in old_chunks.scalars().all():
            await db.delete(old)

        # 4. Embed and persist each chunk
        for i, chunk_text in enumerate(chunks):
            embedding = await embedding_service.aembed(chunk_text)
            db.add(DocumentChunk(
                document_id=document_id,
                knowledge_base_id=doc.knowledge_base_id,
                chunk_index=i,
                content=chunk_text,
                embedding=json.dumps(embedding) if embedding else None,
                token_count=len(chunk_text) // 4,
            ))

        doc.chunk_count = len(chunks)
        doc.token_count = sum(len(c) // 4 for c in chunks)
        doc.status = DocumentStatus.ready
        doc.error_message = None

    except Exception as exc:
        logger.error(f"Document processing failed [{document_id}]: {exc}")
        doc.status = DocumentStatus.failed
        doc.error_message = str(exc)[:500]


# ─── Retrieval ────────────────────────────────────────────────────────────────

async def search(
    db: AsyncSession,
    query: str,
    kb_ids: list[str] | None = None,
    top_k: int = 5,
    min_score: float = 0.1,
) -> list[dict]:
    """
    Semantic search over document chunks.

    Returns a list of dicts sorted by relevance score (descending).
    Each dict has: chunk_id, content, score, document_id, document_title,
    source_url, knowledge_base_id.
    """
    t0 = time.perf_counter()
    with span(
        "rag.retrieve",
        query_len=len(query),
        kb_count=len(kb_ids) if kb_ids else 0,
        top_k=top_k,
        min_score=min_score,
    ) as s:
        stmt = select(DocumentChunk)
        if kb_ids:
            stmt = stmt.where(DocumentChunk.knowledge_base_id.in_(kb_ids))

        result = await db.execute(stmt)
        chunks = result.scalars().all()
        if not chunks:
            set_attrs(s, corpus_size=0, returned=0, latency_ms=int((time.perf_counter() - t0) * 1000))
            return []

        query_embedding = await embedding_service.aembed(query)
        used_embeddings = bool(query_embedding)

        scored: list[tuple[float, DocumentChunk]] = []
        for chunk in chunks:
            if query_embedding and chunk.embedding:
                chunk_emb = json.loads(chunk.embedding)
                score = _cosine_similarity(query_embedding, chunk_emb)
            else:
                score = _keyword_score(query, chunk.content)
            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [(s_, c) for s_, c in scored[:top_k] if s_ >= min_score]

        # Enrich with document metadata (batch fetch unique doc IDs)
        doc_ids = list({c.document_id for _, c in top})
        docs = {}
        for doc_id in doc_ids:
            doc = await db.get(Document, doc_id)
            if doc:
                docs[doc_id] = doc

        out = [
            {
                "chunk_id": chunk.id,
                "content": chunk.content,
                "score": round(score, 4),
                "document_id": chunk.document_id,
                "document_title": docs.get(chunk.document_id, type("", (), {"title": "Unknown"})()).title
                if chunk.document_id in docs else "Unknown",
                "source_url": docs[chunk.document_id].source_url if chunk.document_id in docs else None,
                "knowledge_base_id": chunk.knowledge_base_id,
            }
            for score, chunk in top
        ]

        set_attrs(
            s,
            corpus_size=len(chunks),
            returned=len(out),
            top_score=round(top[0][0], 4) if top else 0.0,
            used_embeddings=used_embeddings,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        return out
