"use client";

import { useEffect, useState } from "react";
import { Brain, Plus, Search, Trash2, Globe, Bot, X, Eraser, ArrowUpCircle, Layers } from "lucide-react";
import { agentsApi, memoryApi, type Agent, type Memory, type MemoryCreate, type MemoryType, type MemoryTier } from "@/lib/api";

const TYPE_COLORS: Record<MemoryType, string> = {
    fact: "bg-blue-100 text-blue-700",
    episode: "bg-purple-100 text-purple-700",
    procedure: "bg-green-100 text-green-700",
};

const TIER_COLORS: Record<MemoryTier, string> = {
    core: "bg-amber-100 text-amber-700 border-amber-200",
    recall: "bg-stone-100 text-stone-600 border-stone-200",
    archival: "bg-indigo-100 text-indigo-700 border-indigo-200",
};

const TIER_LABELS: Record<MemoryTier, string> = {
    core: "Core",
    recall: "Recall",
    archival: "Archival",
};

const IMPORTANCE_LABEL = (s: number) =>
    s >= 0.8 ? "Critical" : s >= 0.6 ? "High" : s >= 0.4 ? "Medium" : "Low";

const IMPORTANCE_COLOR = (s: number) =>
    s >= 0.8 ? "text-red-600" : s >= 0.6 ? "text-orange-500" : s >= 0.4 ? "text-yellow-600" : "text-stone-400";

const DECAY_BAR = (score: number) => {
    const pct = Math.round(score * 100);
    const color = score >= 0.7 ? "bg-green-500" : score >= 0.4 ? "bg-yellow-500" : "bg-red-500";
    return { pct, color };
};

export default function MemoryPage() {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [selectedAgentId, setSelectedAgentId] = useState<string | "shared">("shared");
    const [memories, setMemories] = useState<Memory[]>([]);
    const [searchQuery, setSearchQuery] = useState("");
    const [isSearching, setIsSearching] = useState(false);
    const [loading, setLoading] = useState(false);
    const [showAdd, setShowAdd] = useState(false);
    const [typeFilter, setTypeFilter] = useState<MemoryType | "">("");
    const [tierFilter, setTierFilter] = useState<MemoryTier | "">("");

    // Add form state
    const [newContent, setNewContent] = useState("");
    const [newType, setNewType] = useState<MemoryType>("fact");
    const [newTier, setNewTier] = useState<MemoryTier>("recall");
    const [newImportance, setNewImportance] = useState(0.5);
    const [adding, setAdding] = useState(false);

    useEffect(() => {
        agentsApi.list().then(setAgents).catch(console.error);
    }, []);

    useEffect(() => {
        if (!searchQuery) loadMemories();
    }, [selectedAgentId, typeFilter, tierFilter]);

    async function loadMemories() {
        setLoading(true);
        try {
            const agentId = selectedAgentId === "shared" ? undefined : selectedAgentId;
            const tier = tierFilter || undefined;
            const data = await memoryApi.list(agentId, false, tier);
            setMemories(typeFilter ? data.filter((m) => m.type === typeFilter) : data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    }

    async function handleSearch() {
        if (!searchQuery.trim()) return loadMemories();
        setIsSearching(true);
        try {
            const agentId = selectedAgentId === "shared" ? undefined : selectedAgentId;
            const tier = tierFilter || undefined;
            const data = await memoryApi.search(searchQuery, agentId, selectedAgentId === "shared", tier);
            setMemories(data);
        } catch (e) {
            console.error(e);
        } finally {
            setIsSearching(false);
        }
    }

    async function handleDelete(id: string) {
        if (!confirm("Delete this memory?")) return;
        await memoryApi.delete(id);
        setMemories((prev) => prev.filter((m) => m.id !== id));
    }

    async function handlePromote(id: string, targetTier: MemoryTier) {
        try {
            const updated = await memoryApi.promote(id, targetTier);
            setMemories((prev) => prev.map((m) => (m.id === id ? updated : m)));
        } catch (e: any) {
            alert(e.message);
        }
    }

    async function handleClearAll() {
        const label = selectedAgentId === "shared" ? "shared memories" : `${selectedAgent?.name ?? "agent"}'s memories`;
        if (!confirm(`Clear all ${label}? This cannot be undone.`)) return;
        const agentId = selectedAgentId === "shared" ? undefined : selectedAgentId;
        await memoryApi.clearAll(agentId);
        setMemories([]);
    }

    async function handleAdd(e: React.FormEvent) {
        e.preventDefault();
        if (!newContent.trim()) return;
        setAdding(true);
        try {
            const payload: MemoryCreate = {
                content: newContent,
                type: newType,
                importance_score: newImportance,
                tier: newTier,
                agent_id: selectedAgentId === "shared" ? null : selectedAgentId,
            };
            const created = await memoryApi.create(payload);
            setMemories((prev) => [created, ...prev]);
            setNewContent("");
            setNewType("fact");
            setNewTier("recall");
            setNewImportance(0.5);
            setShowAdd(false);
        } catch (e: any) {
            alert(e.message);
        } finally {
            setAdding(false);
        }
    }

    const selectedAgent = agents.find((a) => a.id === selectedAgentId);

    // Tier stats
    const tierCounts = {
        core: memories.filter((m) => m.tier === "core").length,
        recall: memories.filter((m) => m.tier === "recall").length,
        archival: memories.filter((m) => m.tier === "archival").length,
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-purple-100 flex items-center justify-center">
                        <Brain className="w-5 h-5 text-purple-600" />
                    </div>
                    <div>
                        <h1 className="text-xl font-semibold text-stone-900">Memory</h1>
                        <p className="text-sm text-stone-500">Three-tier memory: Core (always active) / Recall (searchable) / Archival (long-term)</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {memories.length > 0 && (
                        <button
                            onClick={handleClearAll}
                            className="flex items-center gap-2 px-3 py-2 border border-red-200 text-red-600 text-sm rounded-lg hover:bg-red-50 transition-colors"
                        >
                            <Eraser className="w-4 h-4" />
                            Clear All
                        </button>
                    )}
                    <button
                        onClick={() => setShowAdd(!showAdd)}
                        className="flex items-center gap-2 px-3 py-2 bg-stone-900 text-white text-sm rounded-lg hover:bg-stone-700 transition-colors"
                    >
                        <Plus className="w-4 h-4" />
                        Add Memory
                    </button>
                </div>
            </div>

            {/* Tier Stats Bar */}
            <div className="flex gap-3">
                {(["core", "recall", "archival"] as MemoryTier[]).map((t) => (
                    <button
                        key={t}
                        onClick={() => setTierFilter(tierFilter === t ? "" : t)}
                        className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border text-sm font-medium transition-all ${
                            tierFilter === t
                                ? TIER_COLORS[t] + " ring-2 ring-offset-1 ring-stone-300"
                                : "border-stone-200 bg-white text-stone-600 hover:border-stone-300"
                        }`}
                    >
                        <Layers className="w-4 h-4" />
                        {TIER_LABELS[t]}
                        <span className="text-xs font-normal opacity-70">{tierCounts[t]}</span>
                    </button>
                ))}
            </div>

            {/* Add Memory Form */}
            {showAdd && (
                <form onSubmit={handleAdd} className="border border-stone-200 rounded-xl p-5 bg-stone-50 space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="font-medium text-stone-900 text-sm">New Memory</h3>
                        <button type="button" onClick={() => setShowAdd(false)}>
                            <X className="w-4 h-4 text-stone-400" />
                        </button>
                    </div>
                    <textarea
                        value={newContent}
                        onChange={(e) => setNewContent(e.target.value)}
                        rows={3}
                        required
                        placeholder="Enter the information to remember..."
                        className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-stone-900"
                    />
                    <div className="flex gap-3 flex-wrap">
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1">Type</label>
                            <select
                                value={newType}
                                onChange={(e) => setNewType(e.target.value as MemoryType)}
                                className="px-3 py-1.5 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
                            >
                                <option value="fact">Fact</option>
                                <option value="episode">Episode</option>
                                <option value="procedure">Procedure</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1">Tier</label>
                            <select
                                value={newTier}
                                onChange={(e) => setNewTier(e.target.value as MemoryTier)}
                                className="px-3 py-1.5 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
                            >
                                <option value="core">Core (always in context)</option>
                                <option value="recall">Recall (searchable)</option>
                                <option value="archival">Archival (long-term)</option>
                            </select>
                        </div>
                        <div className="flex-1 min-w-40">
                            <label className="block text-xs font-medium text-stone-600 mb-1">
                                Importance: {IMPORTANCE_LABEL(newImportance)} ({newImportance.toFixed(1)})
                            </label>
                            <input
                                type="range"
                                min={0}
                                max={1}
                                step={0.1}
                                value={newImportance}
                                onChange={(e) => setNewImportance(parseFloat(e.target.value))}
                                className="w-full"
                            />
                        </div>
                        <div className="flex items-end">
                            <button
                                type="submit"
                                disabled={adding}
                                className="px-4 py-1.5 bg-stone-900 text-white text-sm rounded-lg hover:bg-stone-700 disabled:opacity-50"
                            >
                                {adding ? "Saving..." : "Save"}
                            </button>
                        </div>
                    </div>
                </form>
            )}

            {/* Filters Row */}
            <div className="flex gap-3 flex-wrap items-center">
                {/* Agent / Shared selector */}
                <div className="flex items-center gap-1 bg-stone-100 rounded-lg p-1">
                    <button
                        onClick={() => setSelectedAgentId("shared")}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                            selectedAgentId === "shared"
                                ? "bg-white text-stone-900 shadow-sm"
                                : "text-stone-500 hover:text-stone-700"
                        }`}
                    >
                        <Globe className="w-4 h-4" />
                        Shared
                    </button>
                    {agents.map((a) => (
                        <button
                            key={a.id}
                            onClick={() => setSelectedAgentId(a.id)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                                selectedAgentId === a.id
                                    ? "bg-white text-stone-900 shadow-sm"
                                    : "text-stone-500 hover:text-stone-700"
                            }`}
                        >
                            <Bot className="w-3.5 h-3.5" />
                            {a.name}
                        </button>
                    ))}
                </div>

                {/* Type filter */}
                <select
                    value={typeFilter}
                    onChange={(e) => setTypeFilter(e.target.value as MemoryType | "")}
                    className="px-3 py-1.5 border border-stone-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-stone-900"
                >
                    <option value="">All types</option>
                    <option value="fact">Facts</option>
                    <option value="episode">Episodes</option>
                    <option value="procedure">Procedures</option>
                </select>

                {/* Search */}
                <div className="flex-1 flex gap-2 min-w-48">
                    <input
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                        placeholder="Semantic search..."
                        className="flex-1 px-3 py-1.5 border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-900"
                    />
                    <button
                        onClick={handleSearch}
                        disabled={isSearching}
                        className="px-3 py-1.5 bg-stone-900 text-white rounded-lg hover:bg-stone-700 disabled:opacity-50 transition-colors"
                    >
                        <Search className="w-4 h-4" />
                    </button>
                    {searchQuery && (
                        <button
                            onClick={() => { setSearchQuery(""); loadMemories(); }}
                            className="px-3 py-1.5 border border-stone-200 rounded-lg text-sm text-stone-500 hover:text-stone-700"
                        >
                            <X className="w-4 h-4" />
                        </button>
                    )}
                </div>
            </div>

            {/* Memory List */}
            {loading ? (
                <div className="text-center py-16 text-stone-400 text-sm">Loading memories...</div>
            ) : memories.length === 0 ? (
                <div className="text-center py-16">
                    <Brain className="w-10 h-10 text-stone-200 mx-auto mb-3" />
                    <p className="text-stone-400 text-sm">No memories yet.</p>
                    <p className="text-stone-300 text-xs mt-1">
                        Memories are created automatically from conversations or added manually.
                    </p>
                </div>
            ) : (
                <div className="space-y-2">
                    <p className="text-xs text-stone-400">{memories.length} memories</p>
                    {memories.map((m) => {
                        const { pct, color } = DECAY_BAR(m.decay_score);
                        return (
                            <div
                                key={m.id}
                                className="flex items-start gap-3 p-4 border border-stone-200 rounded-xl bg-white hover:border-stone-300 transition-colors group"
                            >
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${TIER_COLORS[m.tier]}`}>
                                            {TIER_LABELS[m.tier]}
                                        </span>
                                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${TYPE_COLORS[m.type]}`}>
                                            {m.type}
                                        </span>
                                        <span className={`text-xs font-medium ${IMPORTANCE_COLOR(m.importance_score)}`}>
                                            {IMPORTANCE_LABEL(m.importance_score)}
                                        </span>
                                        {m.agent_id === null && (
                                            <span className="text-xs text-stone-400 flex items-center gap-1">
                                                <Globe className="w-3 h-3" /> shared
                                            </span>
                                        )}
                                        {m.source !== "auto" && (
                                            <span className="text-xs text-stone-400">via {m.source}</span>
                                        )}
                                    </div>
                                    <p className="text-sm text-stone-800 leading-relaxed">{m.content}</p>
                                    <div className="flex items-center gap-3 mt-2 text-xs text-stone-400">
                                        <span>{new Date(m.created_at).toLocaleDateString()}</span>
                                        {m.access_count > 0 && <span>Recalled {m.access_count}x</span>}
                                        {m.last_accessed_at && (
                                            <span>Last: {new Date(m.last_accessed_at).toLocaleDateString()}</span>
                                        )}
                                        {/* Decay bar */}
                                        <div className="flex items-center gap-1.5">
                                            <span>Decay:</span>
                                            <div className="w-16 h-1.5 bg-stone-200 rounded-full overflow-hidden">
                                                <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
                                            </div>
                                            <span>{pct}%</span>
                                        </div>
                                    </div>
                                </div>
                                <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-all">
                                    {m.tier !== "core" && (
                                        <button
                                            onClick={() => handlePromote(m.id, "core")}
                                            title="Promote to Core"
                                            className="p-1.5 rounded-lg hover:bg-amber-50 text-stone-400 hover:text-amber-600"
                                        >
                                            <ArrowUpCircle className="w-4 h-4" />
                                        </button>
                                    )}
                                    {m.tier === "core" && (
                                        <button
                                            onClick={() => handlePromote(m.id, "recall")}
                                            title="Demote to Recall"
                                            className="p-1.5 rounded-lg hover:bg-stone-100 text-stone-400 hover:text-stone-600"
                                        >
                                            <ArrowUpCircle className="w-4 h-4 rotate-180" />
                                        </button>
                                    )}
                                    <button
                                        onClick={() => handleDelete(m.id)}
                                        className="p-1.5 rounded-lg hover:bg-red-50 text-stone-400 hover:text-red-500"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
