"""Knowledge base API routes — CRUD, document ingestion, and RAG search."""

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    DocumentIngestRequest,
    DocumentResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KBSearchResult,
)
from app.core.rag_service import _extract_pdf_text, process_document, search
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.knowledge_base import (
    Document,
    DocumentChunk,
    DocumentSourceType,
    DocumentStatus,
    KnowledgeBase,
)
from app.models.user import User

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge"])
logger = logging.getLogger(__name__)


# ─── Knowledge Base CRUD ─────────────────────────────────────────────────────

@router.get("/", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()))
    kbs = result.scalars().all()

    # Attach document counts
    out = []
    for kb in kbs:
        count_result = await db.execute(
            select(func.count()).select_from(Document).where(Document.knowledge_base_id == kb.id)
        )
        doc_count = count_result.scalar() or 0
        out.append(KnowledgeBaseResponse(
            id=kb.id,
            name=kb.name,
            description=kb.description,
            is_shared=kb.is_shared,
            owner_user_id=kb.owner_user_id,
            document_count=doc_count,
            created_at=kb.created_at,
        ))
    return out


@router.post("/", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kb = KnowledgeBase(
        name=payload.name,
        description=payload.description,
        is_shared=payload.is_shared,
        owner_user_id=current_user.id,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return KnowledgeBaseResponse(
        id=kb.id, name=kb.name, description=kb.description,
        is_shared=kb.is_shared, owner_user_id=kb.owner_user_id,
        document_count=0, created_at=kb.created_at,
    )


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    await db.delete(kb)
    await db.commit()


# ─── Document Listing ────────────────────────────────────────────────────────

@router.get("/{kb_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    kb = await db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    result = await db.execute(
        select(Document)
        .where(Document.knowledge_base_id == kb_id)
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{kb_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    kb_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    doc = await db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()


# ─── Document Ingestion (URL / Text) ─────────────────────────────────────────

@router.post("/{kb_id}/ingest", response_model=DocumentResponse, status_code=201)
async def ingest_document(
    kb_id: str,
    payload: DocumentIngestRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Ingest a document from a URL or raw text into a knowledge base."""
    kb = await db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    source_type = DocumentSourceType(payload.source_type)

    if source_type == DocumentSourceType.url and not payload.source_url:
        raise HTTPException(status_code=422, detail="source_url is required for url type")
    if source_type == DocumentSourceType.text and not payload.content:
        raise HTTPException(status_code=422, detail="content is required for text type")

    doc = Document(
        knowledge_base_id=kb_id,
        title=payload.title,
        source_type=source_type,
        source_url=payload.source_url,
        content=payload.content,
        status=DocumentStatus.pending,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    # Process synchronously (chunking + embedding)
    await process_document(db, doc.id)
    await db.commit()
    await db.refresh(doc)
    return doc


# ─── File Upload ─────────────────────────────────────────────────────────────

@router.post("/{kb_id}/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    kb_id: str,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()] = "",
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Upload a file (PDF, .txt, .md) and ingest it into a knowledge base."""
    _MAX_KB_UPLOAD = 20 * 1024 * 1024  # 20 MB
    _ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".csv", ".json", ".rst"}

    kb = await db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    raw = await file.read()
    if len(raw) > _MAX_KB_UPLOAD:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    doc_title = title or filename

    # Extract text based on file type
    if ext == ".pdf":
        try:
            extracted = _extract_pdf_text(raw)
        except ValueError:
            raise HTTPException(status_code=422, detail="Failed to extract text from PDF")
    else:
        # Plain text / Markdown / code
        try:
            extracted = raw.decode("utf-8", errors="replace")
        except Exception:
            raise HTTPException(status_code=422, detail="Could not decode file as text")

    doc = Document(
        knowledge_base_id=kb_id,
        title=doc_title,
        source_type=DocumentSourceType.file,
        file_name=filename,
        content=extracted,
        status=DocumentStatus.pending,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    await process_document(db, doc.id)
    await db.commit()
    await db.refresh(doc)
    return doc


# ─── Re-index ─────────────────────────────────────────────────────────────────

@router.post("/{kb_id}/documents/{doc_id}/reindex", response_model=DocumentResponse)
async def reindex_document(
    kb_id: str,
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Re-run ingestion on an existing document (useful after fixing errors)."""
    doc = await db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")

    await process_document(db, doc.id)
    await db.commit()
    await db.refresh(doc)
    return doc


# ─── Search ──────────────────────────────────────────────────────────────────

@router.get("/{kb_id}/search", response_model=list[KBSearchResult])
async def search_knowledge_base(
    kb_id: str,
    q: str,
    top_k: int = 5,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Semantic search within a specific knowledge base."""
    kb = await db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    results = await search(db, query=q, kb_ids=[kb_id], top_k=min(top_k, 20))
    return results


@router.get("/search/all", response_model=list[KBSearchResult])
async def search_all_knowledge_bases(
    q: str,
    top_k: int = 5,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Semantic search across all knowledge bases."""
    results = await search(db, query=q, kb_ids=None, top_k=min(top_k, 20))
    return results
