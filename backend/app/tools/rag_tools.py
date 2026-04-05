"""RAG tools — agents can search knowledge bases and ingest URLs."""

import logging

from langchain_core.tools import tool

from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

RAG_TOOL_IDS = {"search_knowledge_base", "ingest_url_to_kb"}


def create_rag_tools(agent_id: str):  # noqa: ARG001 — kept for consistent factory signature
    """Create RAG LangChain tools (not agent-specific, but follows factory pattern)."""

    @tool
    async def search_knowledge_base(query: str, knowledge_base_id: str = "") -> str:
        """Search the organization's knowledge bases for relevant information.

        Args:
            query: The question or topic to search for.
            knowledge_base_id: Optional. Restrict search to a specific knowledge base ID.
                               Leave empty to search all knowledge bases.
        """
        from app.core.rag_service import search

        try:
            async with async_session_factory() as db:
                kb_ids = [knowledge_base_id] if knowledge_base_id else None
                results = await search(db, query=query, kb_ids=kb_ids, top_k=5)

            if not results:
                return "No relevant content found in the knowledge bases."

            parts = [f"Found {len(results)} relevant passages:\n"]
            for i, r in enumerate(results, 1):
                parts.append(
                    f"[{i}] Source: {r['document_title']}"
                    + (f" ({r['source_url']})" if r['source_url'] else "")
                    + f"\nScore: {r['score']}\n{r['content']}\n"
                )
            return "\n".join(parts)

        except Exception as exc:
            logger.error(f"search_knowledge_base failed: {exc}")
            return f"Search failed: {exc}"

    @tool
    async def ingest_url_to_kb(url: str, knowledge_base_id: str, title: str = "") -> str:
        """Fetch a web page and add it to a knowledge base for future retrieval.

        Args:
            url: The URL to fetch and ingest.
            knowledge_base_id: The ID of the knowledge base to add the document to.
            title: Optional title for the document. Defaults to the URL.
        """
        from app.core.rag_service import process_document
        from app.models.knowledge_base import Document, DocumentSourceType, DocumentStatus

        try:
            async with async_session_factory() as db:
                doc = Document(
                    knowledge_base_id=knowledge_base_id,
                    title=title or url,
                    source_type=DocumentSourceType.url,
                    source_url=url,
                    status=DocumentStatus.pending,
                )
                db.add(doc)
                await db.flush()
                await db.refresh(doc)
                await process_document(db, doc.id)
                await db.commit()
                await db.refresh(doc)

            if doc.status == DocumentStatus.ready:
                return f"Successfully ingested '{doc.title}' — {doc.chunk_count} chunks indexed."
            else:
                return f"Ingestion failed: {doc.error_message}"

        except Exception as exc:
            logger.error(f"ingest_url_to_kb failed: {exc}")
            return f"Ingestion failed: {exc}"

    return [search_knowledge_base, ingest_url_to_kb]
