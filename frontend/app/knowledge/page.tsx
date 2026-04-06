"use client";

import { useState, useEffect, useRef, ReactElement } from "react";
import {
    BookOpen,
    Plus,
    Trash2,
    Upload,
    Link,
    FileText,
    Search,
    RefreshCw,
    ChevronRight,
    AlertCircle,
    CheckCircle,
    Clock,
    Loader2,
    X,
} from "lucide-react";
import { knowledgeApi, KnowledgeBase, KBDocument, KBSearchResult } from "@/lib/api";

type Tab = "bases" | "search";
type IngestMode = "url" | "text" | "file";

const STATUS_ICON: Record<string, ReactElement> = {
    ready: <CheckCircle className="w-4 h-4 text-green-500" />,
    processing: <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />,
    pending: <Clock className="w-4 h-4 text-yellow-500" />,
    failed: <AlertCircle className="w-4 h-4 text-red-500" />,
};

export default function KnowledgePage() {
    const [tab, setTab] = useState<Tab>("bases");
    const [bases, setBases] = useState<KnowledgeBase[]>([]);
    const [selectedKb, setSelectedKb] = useState<KnowledgeBase | null>(null);
    const [documents, setDocuments] = useState<KBDocument[]>([]);
    const [loading, setLoading] = useState(false);
    const [docsLoading, setDocsLoading] = useState(false);

    // Create KB
    const [showCreate, setShowCreate] = useState(false);
    const [newName, setNewName] = useState("");
    const [newDesc, setNewDesc] = useState("");
    const [creating, setCreating] = useState(false);

    // Ingest
    const [showIngest, setShowIngest] = useState(false);
    const [ingestMode, setIngestMode] = useState<IngestMode>("url");
    const [ingestTitle, setIngestTitle] = useState("");
    const [ingestUrl, setIngestUrl] = useState("");
    const [ingestText, setIngestText] = useState("");
    const [ingesting, setIngesting] = useState(false);
    const [ingestError, setIngestError] = useState("");
    const fileRef = useRef<HTMLInputElement>(null);

    // Search
    const [searchQuery, setSearchQuery] = useState("");
    const [searchKbId, setSearchKbId] = useState<string>("");
    const [searchResults, setSearchResults] = useState<KBSearchResult[]>([]);
    const [searching, setSearching] = useState(false);

    useEffect(() => {
        loadBases();
    }, []);

    async function loadBases() {
        setLoading(true);
        try {
            setBases(await knowledgeApi.list());
        } finally {
            setLoading(false);
        }
    }

    async function loadDocuments(kb: KnowledgeBase) {
        setSelectedKb(kb);
        setDocsLoading(true);
        try {
            setDocuments(await knowledgeApi.listDocuments(kb.id));
        } finally {
            setDocsLoading(false);
        }
    }

    async function createKb() {
        if (!newName.trim()) return;
        setCreating(true);
        try {
            const kb = await knowledgeApi.create({ name: newName.trim(), description: newDesc.trim() || undefined });
            setBases(prev => [kb, ...prev]);
            setShowCreate(false);
            setNewName("");
            setNewDesc("");
        } finally {
            setCreating(false);
        }
    }

    async function deleteKb(kb: KnowledgeBase) {
        if (!confirm(`Delete knowledge base "${kb.name}" and all its documents?`)) return;
        await knowledgeApi.delete(kb.id);
        setBases(prev => prev.filter(b => b.id !== kb.id));
        if (selectedKb?.id === kb.id) {
            setSelectedKb(null);
            setDocuments([]);
        }
    }

    async function deleteDoc(doc: KBDocument) {
        if (!confirm(`Delete "${doc.title}"?`)) return;
        await knowledgeApi.deleteDocument(selectedKb!.id, doc.id);
        setDocuments(prev => prev.filter(d => d.id !== doc.id));
        // Update count on base
        setBases(prev => prev.map(b =>
            b.id === selectedKb!.id ? { ...b, document_count: b.document_count - 1 } : b
        ));
    }

    async function reindexDoc(doc: KBDocument) {
        const updated = await knowledgeApi.reindex(selectedKb!.id, doc.id);
        setDocuments(prev => prev.map(d => d.id === doc.id ? updated : d));
    }

    async function handleIngest() {
        if (!selectedKb) return;
        setIngesting(true);
        setIngestError("");
        try {
            if (ingestMode === "file") {
                const file = fileRef.current?.files?.[0];
                if (!file) { setIngestError("Please select a file"); return; }
                const doc = await knowledgeApi.upload(selectedKb.id, file, ingestTitle || undefined);
                setDocuments(prev => [doc, ...prev]);
            } else {
                const doc = await knowledgeApi.ingest(selectedKb.id, {
                    title: ingestTitle || (ingestMode === "url" ? ingestUrl : "Pasted Text"),
                    source_type: ingestMode,
                    source_url: ingestMode === "url" ? ingestUrl : undefined,
                    content: ingestMode === "text" ? ingestText : undefined,
                });
                setDocuments(prev => [doc, ...prev]);
            }
            setBases(prev => prev.map(b =>
                b.id === selectedKb.id ? { ...b, document_count: b.document_count + 1 } : b
            ));
            setShowIngest(false);
            setIngestTitle("");
            setIngestUrl("");
            setIngestText("");
        } catch (e: any) {
            setIngestError(e?.message || "Ingestion failed");
        } finally {
            setIngesting(false);
        }
    }

    async function handleSearch() {
        if (!searchQuery.trim()) return;
        setSearching(true);
        setSearchResults([]);
        try {
            if (searchKbId) {
                setSearchResults(await knowledgeApi.search(searchKbId, searchQuery));
            } else {
                setSearchResults(await knowledgeApi.searchAll(searchQuery));
            }
        } finally {
            setSearching(false);
        }
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-6 py-4 border-b border-stone-200 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <BookOpen className="w-6 h-6 text-stone-700" />
                    <div>
                        <h1 className="text-xl font-semibold text-stone-900">Knowledge Base</h1>
                        <p className="text-sm text-stone-500">Ingest documents, PDFs, and web pages for agents to search</p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={() => setTab("bases")}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "bases" ? "bg-stone-700 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"}`}
                    >
                        Knowledge Bases
                    </button>
                    <button
                        onClick={() => setTab("search")}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${tab === "search" ? "bg-stone-700 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"}`}
                    >
                        Search
                    </button>
                </div>
            </div>

            {tab === "bases" ? (
                <div className="flex flex-1 overflow-hidden">
                    {/* Left: KB list */}
                    <div className="w-72 border-r border-stone-200 flex flex-col">
                        <div className="p-3 border-b border-stone-200">
                            <button
                                onClick={() => setShowCreate(true)}
                                className="w-full flex items-center gap-2 px-3 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 transition-colors"
                            >
                                <Plus className="w-4 h-4" />
                                New Knowledge Base
                            </button>
                        </div>

                        {showCreate && (
                            <div className="p-3 border-b border-stone-200 bg-stone-50 space-y-2">
                                <input
                                    autoFocus
                                    value={newName}
                                    onChange={e => setNewName(e.target.value)}
                                    placeholder="Knowledge base name"
                                    className="w-full px-2 py-1.5 text-sm border border-stone-300 rounded"
                                    onKeyDown={e => e.key === "Enter" && createKb()}
                                />
                                <input
                                    value={newDesc}
                                    onChange={e => setNewDesc(e.target.value)}
                                    placeholder="Description (optional)"
                                    className="w-full px-2 py-1.5 text-sm border border-stone-300 rounded"
                                />
                                <div className="flex gap-2">
                                    <button
                                        onClick={createKb}
                                        disabled={creating || !newName.trim()}
                                        className="flex-1 py-1.5 bg-stone-700 text-white rounded text-sm disabled:opacity-50"
                                    >
                                        {creating ? "Creating..." : "Create"}
                                    </button>
                                    <button
                                        onClick={() => { setShowCreate(false); setNewName(""); setNewDesc(""); }}
                                        className="px-3 py-1.5 bg-stone-200 text-stone-600 rounded text-sm"
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        )}

                        <div className="flex-1 overflow-y-auto">
                            {loading ? (
                                <div className="p-4 text-center text-stone-400 text-sm">Loading...</div>
                            ) : bases.length === 0 ? (
                                <div className="p-4 text-center text-stone-400 text-sm">No knowledge bases yet</div>
                            ) : (
                                bases.map(kb => (
                                    <div
                                        key={kb.id}
                                        onClick={() => loadDocuments(kb)}
                                        className={`flex items-center gap-2 px-3 py-3 cursor-pointer border-b border-stone-100 hover:bg-stone-50 transition-colors ${selectedKb?.id === kb.id ? "bg-stone-100 border-l-2 border-l-stone-600" : ""}`}
                                    >
                                        <BookOpen className="w-4 h-4 text-stone-400 flex-shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-stone-800 truncate">{kb.name}</p>
                                            <p className="text-xs text-stone-400">{kb.document_count} doc{kb.document_count !== 1 ? "s" : ""}</p>
                                        </div>
                                        <div className="flex items-center gap-1">
                                            <ChevronRight className="w-4 h-4 text-stone-300" />
                                            <button
                                                onClick={e => { e.stopPropagation(); deleteKb(kb); }}
                                                className="p-1 rounded hover:bg-red-100 text-stone-400 hover:text-red-500 transition-colors"
                                            >
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>

                    {/* Right: Documents */}
                    <div className="flex-1 flex flex-col overflow-hidden">
                        {!selectedKb ? (
                            <div className="flex-1 flex items-center justify-center text-stone-400">
                                <div className="text-center">
                                    <BookOpen className="w-12 h-12 mx-auto mb-3 text-stone-200" />
                                    <p className="text-sm">Select a knowledge base to view its documents</p>
                                </div>
                            </div>
                        ) : (
                            <>
                                {/* KB header */}
                                <div className="px-5 py-3 border-b border-stone-200 flex items-center justify-between">
                                    <div>
                                        <h2 className="font-semibold text-stone-800">{selectedKb.name}</h2>
                                        {selectedKb.description && (
                                            <p className="text-xs text-stone-400 mt-0.5">{selectedKb.description}</p>
                                        )}
                                    </div>
                                    <button
                                        onClick={() => setShowIngest(true)}
                                        className="flex items-center gap-2 px-3 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 transition-colors"
                                    >
                                        <Plus className="w-4 h-4" />
                                        Add Document
                                    </button>
                                </div>

                                {/* Ingest modal */}
                                {showIngest && (
                                    <div className="px-5 py-4 border-b border-stone-200 bg-stone-50 space-y-3">
                                        <div className="flex items-center justify-between">
                                            <p className="text-sm font-medium text-stone-700">Add Document</p>
                                            <button onClick={() => setShowIngest(false)} className="p-1 rounded hover:bg-stone-200">
                                                <X className="w-4 h-4 text-stone-500" />
                                            </button>
                                        </div>

                                        {/* Source type tabs */}
                                        <div className="flex gap-1 bg-stone-200 p-1 rounded-lg w-fit">
                                            {(["url", "text", "file"] as IngestMode[]).map(m => (
                                                <button
                                                    key={m}
                                                    onClick={() => setIngestMode(m)}
                                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium capitalize transition-colors ${ingestMode === m ? "bg-white text-stone-800 shadow-sm" : "text-stone-600 hover:text-stone-800"}`}
                                                >
                                                    {m === "url" && <Link className="w-3.5 h-3.5" />}
                                                    {m === "text" && <FileText className="w-3.5 h-3.5" />}
                                                    {m === "file" && <Upload className="w-3.5 h-3.5" />}
                                                    {m}
                                                </button>
                                            ))}
                                        </div>

                                        <input
                                            value={ingestTitle}
                                            onChange={e => setIngestTitle(e.target.value)}
                                            placeholder="Title (optional)"
                                            className="w-full px-3 py-2 text-sm border border-stone-300 rounded-lg"
                                        />

                                        {ingestMode === "url" && (
                                            <input
                                                value={ingestUrl}
                                                onChange={e => setIngestUrl(e.target.value)}
                                                placeholder="https://..."
                                                className="w-full px-3 py-2 text-sm border border-stone-300 rounded-lg"
                                            />
                                        )}
                                        {ingestMode === "text" && (
                                            <textarea
                                                value={ingestText}
                                                onChange={e => setIngestText(e.target.value)}
                                                placeholder="Paste text content here..."
                                                rows={5}
                                                className="w-full px-3 py-2 text-sm border border-stone-300 rounded-lg resize-none"
                                            />
                                        )}
                                        {ingestMode === "file" && (
                                            <div>
                                                <input
                                                    ref={fileRef}
                                                    type="file"
                                                    accept=".pdf,.txt,.md,.csv"
                                                    className="w-full text-sm text-stone-500 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:bg-stone-100 file:text-stone-700 hover:file:bg-stone-200"
                                                />
                                                <p className="text-xs text-stone-400 mt-1">Supports PDF, TXT, MD, CSV</p>
                                            </div>
                                        )}

                                        {ingestError && (
                                            <p className="text-xs text-red-600 bg-red-50 px-3 py-2 rounded">{ingestError}</p>
                                        )}

                                        <div className="flex gap-2">
                                            <button
                                                onClick={handleIngest}
                                                disabled={ingesting}
                                                className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50 transition-colors"
                                            >
                                                {ingesting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                                                {ingesting ? "Processing..." : "Ingest"}
                                            </button>
                                        </div>
                                    </div>
                                )}

                                {/* Document list */}
                                <div className="flex-1 overflow-y-auto">
                                    {docsLoading ? (
                                        <div className="p-6 text-center text-stone-400 text-sm">Loading documents...</div>
                                    ) : documents.length === 0 ? (
                                        <div className="p-8 text-center text-stone-400">
                                            <FileText className="w-10 h-10 mx-auto mb-2 text-stone-200" />
                                            <p className="text-sm">No documents yet. Add one above.</p>
                                        </div>
                                    ) : (
                                        <table className="w-full text-sm">
                                            <thead>
                                                <tr className="border-b border-stone-200 bg-stone-50 text-left">
                                                    <th className="px-5 py-2.5 text-xs font-medium text-stone-500">Document</th>
                                                    <th className="px-3 py-2.5 text-xs font-medium text-stone-500">Status</th>
                                                    <th className="px-3 py-2.5 text-xs font-medium text-stone-500">Chunks</th>
                                                    <th className="px-3 py-2.5 text-xs font-medium text-stone-500">Tokens</th>
                                                    <th className="px-3 py-2.5 text-xs font-medium text-stone-500">Actions</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {documents.map(doc => (
                                                    <tr key={doc.id} className="border-b border-stone-100 hover:bg-stone-50">
                                                        <td className="px-5 py-3">
                                                            <div className="flex items-center gap-2">
                                                                {doc.source_type === "url" && <Link className="w-4 h-4 text-stone-400 flex-shrink-0" />}
                                                                {doc.source_type === "file" && <Upload className="w-4 h-4 text-stone-400 flex-shrink-0" />}
                                                                {doc.source_type === "text" && <FileText className="w-4 h-4 text-stone-400 flex-shrink-0" />}
                                                                <div className="min-w-0">
                                                                    <p className="font-medium text-stone-800 truncate max-w-xs">{doc.title}</p>
                                                                    {doc.source_url && (
                                                                        <a href={doc.source_url} target="_blank" rel="noreferrer" className="text-xs text-stone-600 hover:underline truncate max-w-xs block">
                                                                            {doc.source_url}
                                                                        </a>
                                                                    )}
                                                                    {doc.error_message && (
                                                                        <p className="text-xs text-red-500 mt-0.5">{doc.error_message}</p>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        </td>
                                                        <td className="px-3 py-3">
                                                            <div className="flex items-center gap-1.5">
                                                                {STATUS_ICON[doc.status]}
                                                                <span className="capitalize text-xs text-stone-600">{doc.status}</span>
                                                            </div>
                                                        </td>
                                                        <td className="px-3 py-3 text-stone-600">{doc.chunk_count}</td>
                                                        <td className="px-3 py-3 text-stone-600">~{doc.token_count.toLocaleString()}</td>
                                                        <td className="px-3 py-3">
                                                            <div className="flex items-center gap-1">
                                                                <button
                                                                    onClick={() => reindexDoc(doc)}
                                                                    title="Re-index"
                                                                    className="p-1.5 rounded hover:bg-stone-200 text-stone-400 hover:text-stone-700 transition-colors"
                                                                >
                                                                    <RefreshCw className="w-3.5 h-3.5" />
                                                                </button>
                                                                <button
                                                                    onClick={() => deleteDoc(doc)}
                                                                    title="Delete"
                                                                    className="p-1.5 rounded hover:bg-red-100 text-stone-400 hover:text-red-500 transition-colors"
                                                                >
                                                                    <Trash2 className="w-3.5 h-3.5" />
                                                                </button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    )}
                                </div>
                            </>
                        )}
                    </div>
                </div>
            ) : (
                /* ── Search Tab ── */
                <div className="flex-1 overflow-y-auto p-6 max-w-4xl mx-auto w-full">
                    <div className="space-y-4">
                        {/* Search form */}
                        <div className="bg-white border border-stone-200 rounded-xl p-4 space-y-3">
                            <div className="flex gap-3">
                                <div className="flex-1">
                                    <input
                                        value={searchQuery}
                                        onChange={e => setSearchQuery(e.target.value)}
                                        onKeyDown={e => e.key === "Enter" && handleSearch()}
                                        placeholder="Ask a question or search for a topic..."
                                        className="w-full px-4 py-2.5 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                    />
                                </div>
                                <select
                                    value={searchKbId}
                                    onChange={e => setSearchKbId(e.target.value)}
                                    className="px-3 py-2 border border-stone-300 rounded-lg text-sm text-stone-700"
                                >
                                    <option value="">All knowledge bases</option>
                                    {bases.map(kb => (
                                        <option key={kb.id} value={kb.id}>{kb.name}</option>
                                    ))}
                                </select>
                                <button
                                    onClick={handleSearch}
                                    disabled={searching || !searchQuery.trim()}
                                    className="flex items-center gap-2 px-4 py-2.5 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50 transition-colors"
                                >
                                    {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                                    Search
                                </button>
                            </div>
                        </div>

                        {/* Results */}
                        {searchResults.length > 0 && (
                            <div className="space-y-3">
                                <p className="text-sm text-stone-500">{searchResults.length} result{searchResults.length !== 1 ? "s" : ""}</p>
                                {searchResults.map((r, i) => (
                                    <div key={r.chunk_id} className="bg-white border border-stone-200 rounded-xl p-4 space-y-2">
                                        <div className="flex items-start justify-between gap-3">
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-bold text-stone-400">#{i + 1}</span>
                                                <span className="text-sm font-medium text-stone-800">{r.document_title}</span>
                                                {r.source_url && (
                                                    <a href={r.source_url} target="_blank" rel="noreferrer"
                                                        className="text-xs text-stone-600 hover:underline truncate max-w-xs">
                                                        {r.source_url}
                                                    </a>
                                                )}
                                            </div>
                                            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${r.score > 0.7 ? "bg-green-100 text-green-700" : r.score > 0.4 ? "bg-yellow-100 text-yellow-700" : "bg-stone-100 text-stone-600"}`}>
                                                {(r.score * 100).toFixed(0)}% match
                                            </span>
                                        </div>
                                        <p className="text-sm text-stone-600 leading-relaxed whitespace-pre-wrap">{r.content}</p>
                                    </div>
                                ))}
                            </div>
                        )}

                        {!searching && searchResults.length === 0 && searchQuery && (
                            <div className="text-center py-12 text-stone-400">
                                <Search className="w-10 h-10 mx-auto mb-2 text-stone-200" />
                                <p className="text-sm">No results found. Try different search terms.</p>
                            </div>
                        )}

                        {!searchQuery && (
                            <div className="text-center py-16 text-stone-400">
                                <Search className="w-12 h-12 mx-auto mb-3 text-stone-200" />
                                <p className="text-sm font-medium">Search your knowledge bases</p>
                                <p className="text-xs mt-1">Ask a question and Sutra will find the most relevant passages</p>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
