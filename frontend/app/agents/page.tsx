"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import {
    Bot,
    Plus,
    Play,
    Square,
    RotateCw,
    LayoutGrid,
    List,
    Trash2,
    Zap,
    Activity,
    Folder as FolderIcon,
    FolderPlus,
    Edit2,
    X,
    Check,
    ChevronDown,
    Copy,
} from "lucide-react";
import { agentsApi, chatApi, llmsApi, foldersApi, purposesApi, type Agent, type OpenRouterQuota, type AgentDailyUsage, type Folder } from "@/lib/api";
import AgentAvatar, { AvatarPicker } from "@/components/AgentAvatar";

export default function AgentsPage() {
    const [viewMode, setViewMode] = useState<"grid" | "table">("table");
    const [agents, setAgents] = useState<Agent[]>([]);
    const [purposeNames, setPurposeNames] = useState<Record<string, string>>({});
    const [loading, setLoading] = useState(true);
    const [actionLoading, setActionLoading] = useState<string | null>(null);
    const [openRouterQuota, setOpenRouterQuota] = useState<OpenRouterQuota | null>(null);
    const [dailyUsage, setDailyUsage] = useState<Record<string, number>>({});

    // Folder State
    const [folders, setFolders] = useState<Folder[]>([]);
    const [selectedFolderId, setSelectedFolderId] = useState<string | null>(() => {
        if (typeof window !== "undefined") {
            const stored = localStorage.getItem("agents_selectedFolderId");
            if (stored === "NULL") return null;
            return stored ?? "ALL";
        }
        return "ALL";
    });

    function selectFolder(id: string | null) {
        setSelectedFolderId(id);
        if (typeof window !== "undefined") {
            localStorage.setItem("agents_selectedFolderId", id ?? "NULL");
        }
    }

    // Folder CRUD UI State
    const [isCreatingFolder, setIsCreatingFolder] = useState(false);
    const [newFolderName, setNewFolderName] = useState("");
    const [editingFolderId, setEditingFolderId] = useState<string | null>(null);
    const [editingFolderName, setEditingFolderName] = useState("");
    const [folderDropdownOpen, setFolderDropdownOpen] = useState(false);
    const folderDropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        loadAgents();
    }, []);

    // Close dropdown on outside click
    useEffect(() => {
        function handleClickOutside(e: MouseEvent) {
            if (folderDropdownRef.current && !folderDropdownRef.current.contains(e.target as Node)) {
                setFolderDropdownOpen(false);
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    async function loadAgents() {
        try {
            const [list, folderList, purposes] = await Promise.all([
                agentsApi.list(),
                foldersApi.list().catch(() => []),
                purposesApi.list().catch(() => []),
            ]);
            setAgents(list);
            setFolders(folderList);
            const nameMap: Record<string, string> = {};
            purposes.forEach(p => { nameMap[p.id] = p.name; });
            setPurposeNames(nameMap);

            const usageResults = await Promise.all(
                list.map(a => chatApi.dailyUsage(a.id).catch(() => ({ agent_id: a.id, date: "", request_count: 0 })))
            );
            const usageMap: Record<string, number> = {};
            usageResults.forEach(u => { usageMap[u.agent_id] = u.request_count; });
            setDailyUsage(usageMap);

            if (list.some(a => a.llm_provider === "openrouter")) {
                llmsApi.openRouterQuota()
                    .then(q => setOpenRouterQuota(q))
                    .catch(() => { });
            }
        } catch (err) {
            console.error("Failed to load agents:", err);
        } finally {
            setLoading(false);
        }
    }

    async function handleStart(id: string) {
        setActionLoading(id);
        try { await agentsApi.start(id); await loadAgents(); } catch (err) { console.error(err); } finally { setActionLoading(null); }
    }

    async function handleStop(id: string) {
        setActionLoading(id);
        try { await agentsApi.stop(id); await loadAgents(); } catch (err) { console.error(err); } finally { setActionLoading(null); }
    }

    async function handleRestart(id: string) {
        setActionLoading(id);
        try { await agentsApi.restart(id); await loadAgents(); } catch (err) { console.error(err); } finally { setActionLoading(null); }
    }

    async function handleDelete(id: string) {
        if (!confirm("Are you sure you want to delete this agent?")) return;
        try { await agentsApi.delete(id); await loadAgents(); } catch (err) { console.error(err); }
    }

    async function handleClone(id: string) {
        setActionLoading(id);
        try { await agentsApi.clone(id); await loadAgents(); } catch (err) { console.error(err); } finally { setActionLoading(null); }
    }

    // ─── Avatar Picker ─────────────────────────────────────────────────────────

    const [avatarPickerAgentId, setAvatarPickerAgentId] = useState<string | null>(null);

    async function handleAvatarChange(agentId: string, avatarId: string | null) {
        try {
            await agentsApi.update(agentId, { avatar_url: avatarId } as any);
            setAgents(prev => prev.map(a => a.id === agentId ? { ...a, avatar_url: avatarId } : a));
        } catch (err) { console.error(err); }
        setAvatarPickerAgentId(null);
    }

    // ─── Folder Actions ──────────────────────────────────────────────────────────

    async function handleCreateFolder(e: React.FormEvent) {
        e.preventDefault();
        if (!newFolderName.trim()) return;
        try {
            const folder = await foldersApi.create({ name: newFolderName.trim() });
            setFolders([...folders, folder]);
            setIsCreatingFolder(false);
            setNewFolderName("");
            selectFolder(folder.id);
        } catch (err) { console.error(err); alert("Failed to create folder"); }
    }

    async function handleUpdateFolder(e: React.FormEvent, id: string) {
        e.preventDefault();
        if (!editingFolderName.trim()) return;
        try {
            const updated = await foldersApi.update(id, { name: editingFolderName.trim() });
            setFolders(folders.map(f => f.id === id ? updated : f));
            setEditingFolderId(null);
            setEditingFolderName("");
        } catch (err) { console.error(err); alert("Failed to update folder"); }
    }

    async function handleDeleteFolder(id: string, name: string) {
        if (!confirm(`Delete folder "${name}"? Agents inside will be moved to Uncategorized.`)) return;
        try {
            await foldersApi.delete(id);
            setFolders(folders.filter(f => f.id !== id));
            if (selectedFolderId === id) selectFolder("ALL");
            await loadAgents();
        } catch (err) { console.error(err); alert("Failed to delete folder"); }
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────────

    const filteredAgents = agents.filter(agent => {
        if (selectedFolderId === "ALL") return true;
        if (selectedFolderId === null) return agent.folder_id === null;
        return agent.folder_id === selectedFolderId;
    });

    const selectedFolderLabel = selectedFolderId === "ALL"
        ? "All Agents"
        : selectedFolderId === null
            ? "Uncategorized"
            : folders.find(f => f.id === selectedFolderId)?.name || "All Agents";

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-stone-900">Agents</h1>
                    <p className="text-sm text-stone-500 mt-1">Create and manage your AI agents</p>
                </div>
                <div className="flex items-center gap-3">
                    {/* Folder Dropdown */}
                    <div className="relative" ref={folderDropdownRef}>
                        <button
                            onClick={() => setFolderDropdownOpen(!folderDropdownOpen)}
                            className="flex items-center gap-2 px-3 py-1.5 bg-white border border-stone-200 rounded-lg text-sm text-stone-700 hover:bg-stone-50 transition-colors shadow-sm"
                        >
                            <FolderIcon className="w-3.5 h-3.5 text-stone-400" />
                            <span className="max-w-[120px] truncate">{selectedFolderLabel}</span>
                            <ChevronDown className="w-3.5 h-3.5 text-stone-400" />
                        </button>

                        {folderDropdownOpen && (
                            <div className="absolute right-0 top-full mt-1.5 w-64 bg-white border border-stone-200 rounded-xl shadow-lg z-50 py-1 animate-slide-up">
                                <button
                                    onClick={() => { selectFolder("ALL"); setFolderDropdownOpen(false); }}
                                    className={`w-full flex items-center gap-3 px-3 py-2 text-sm transition-colors ${selectedFolderId === "ALL" ? "bg-stone-100 text-stone-800 font-medium" : "text-stone-600 hover:bg-stone-50"}`}
                                >
                                    <FolderIcon className="w-4 h-4" />
                                    All Agents
                                    <span className="ml-auto text-xs text-stone-400">{agents.length}</span>
                                </button>
                                <button
                                    onClick={() => { selectFolder(null); setFolderDropdownOpen(false); }}
                                    className={`w-full flex items-center gap-3 px-3 py-2 text-sm transition-colors ${selectedFolderId === null ? "bg-stone-100 text-stone-800 font-medium" : "text-stone-600 hover:bg-stone-50"}`}
                                >
                                    <FolderIcon className="w-4 h-4" />
                                    Uncategorized
                                    <span className="ml-auto text-xs text-stone-400">{agents.filter(a => a.folder_id === null).length}</span>
                                </button>

                                {folders.length > 0 && <div className="border-t border-stone-100 my-1" />}

                                {folders.map(folder => (
                                    <div key={folder.id} className="group flex items-center">
                                        {editingFolderId === folder.id ? (
                                            <form onSubmit={(e) => handleUpdateFolder(e, folder.id)} className="flex items-center gap-1 w-full px-3 py-1">
                                                <input
                                                    type="text"
                                                    value={editingFolderName}
                                                    onChange={(e) => setEditingFolderName(e.target.value)}
                                                    className="input py-1 px-2 text-sm flex-1"
                                                    autoFocus
                                                />
                                                <button type="submit" className="text-emerald-500 hover:text-emerald-600 p-1"><Check className="w-3.5 h-3.5" /></button>
                                                <button type="button" onClick={() => setEditingFolderId(null)} className="text-stone-400 hover:text-stone-600 p-1"><X className="w-3.5 h-3.5" /></button>
                                            </form>
                                        ) : (
                                            <button
                                                onClick={() => { selectFolder(folder.id); setFolderDropdownOpen(false); }}
                                                className={`flex-1 flex items-center gap-3 px-3 py-2 text-sm transition-colors ${selectedFolderId === folder.id ? "bg-stone-100 text-stone-800 font-medium" : "text-stone-600 hover:bg-stone-50"}`}
                                            >
                                                <FolderIcon className="w-4 h-4" />
                                                {folder.name}
                                                <span className="ml-auto text-xs text-stone-400">{agents.filter(a => a.folder_id === folder.id).length}</span>
                                            </button>
                                        )}
                                        {editingFolderId !== folder.id && (
                                            <div className="opacity-0 group-hover:opacity-100 flex items-center gap-0.5 pr-2 transition-opacity">
                                                <button onClick={() => { setEditingFolderId(folder.id); setEditingFolderName(folder.name); }} className="text-stone-400 hover:text-stone-600 p-1 rounded"><Edit2 className="w-3 h-3" /></button>
                                                <button onClick={() => handleDeleteFolder(folder.id, folder.name)} className="text-stone-400 hover:text-red-500 p-1 rounded"><Trash2 className="w-3 h-3" /></button>
                                            </div>
                                        )}
                                    </div>
                                ))}

                                <div className="border-t border-stone-100 mt-1 pt-1">
                                    {isCreatingFolder ? (
                                        <form onSubmit={handleCreateFolder} className="flex items-center gap-1 px-3 py-1">
                                            <input
                                                type="text"
                                                value={newFolderName}
                                                onChange={(e) => setNewFolderName(e.target.value)}
                                                placeholder="Folder name..."
                                                className="input py-1 px-2 text-sm flex-1"
                                                autoFocus
                                            />
                                            <button type="submit" className="text-emerald-500 hover:text-emerald-600 p-1"><Check className="w-3.5 h-3.5" /></button>
                                            <button type="button" onClick={() => { setIsCreatingFolder(false); setNewFolderName(""); }} className="text-stone-400 hover:text-stone-600 p-1"><X className="w-3.5 h-3.5" /></button>
                                        </form>
                                    ) : (
                                        <button
                                            onClick={() => setIsCreatingFolder(true)}
                                            className="w-full flex items-center gap-3 px-3 py-2 text-sm text-stone-400 hover:text-stone-600 hover:bg-stone-50 transition-colors"
                                        >
                                            <FolderPlus className="w-4 h-4" />
                                            New Folder
                                        </button>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* View Toggle */}
                    <div className="flex items-center bg-stone-100 rounded-lg p-0.5">
                        <button
                            onClick={() => setViewMode("grid")}
                            className={`p-1.5 rounded-md transition-colors ${viewMode === "grid" ? "bg-white text-stone-800 shadow-sm" : "text-stone-400 hover:text-stone-600"}`}
                            title="Grid View"
                        >
                            <LayoutGrid className="w-4 h-4" />
                        </button>
                        <button
                            onClick={() => setViewMode("table")}
                            className={`p-1.5 rounded-md transition-colors ${viewMode === "table" ? "bg-white text-stone-800 shadow-sm" : "text-stone-400 hover:text-stone-600"}`}
                            title="List View"
                        >
                            <List className="w-4 h-4" />
                        </button>
                    </div>

                    <Link href="/agents/new" className="btn-primary flex items-center gap-2">
                        <Plus className="w-4 h-4" />
                        <span className="hidden sm:inline">New Agent</span>
                        <span className="sm:hidden">New</span>
                    </Link>
                </div>
            </div>

            {/* Content */}
            {loading ? (
                <div className="text-center py-16 text-stone-400">Loading agents...</div>
            ) : agents.length === 0 ? (
                <div className="text-center py-20 glass-card">
                    <div className="w-16 h-16 rounded-2xl bg-stone-200 flex items-center justify-center mx-auto mb-4">
                        <Bot className="w-8 h-8 text-stone-500" />
                    </div>
                    <h3 className="text-xl font-semibold text-stone-800 mb-2">No agents yet</h3>
                    <p className="text-stone-500 mb-6">Create your first AI agent to get started</p>
                    <Link href="/agents/new" className="btn-primary inline-flex items-center gap-2">
                        <Zap className="w-4 h-4" />
                        Create Agent
                    </Link>
                </div>
            ) : filteredAgents.length === 0 ? (
                <div className="text-center py-20 glass-card">
                    <FolderIcon className="w-12 h-12 text-stone-300 mx-auto mb-3" />
                    <h3 className="text-lg font-medium text-stone-800 mb-1">Empty Folder</h3>
                    <p className="text-sm text-stone-500">No agents found in this category.</p>
                </div>
            ) : viewMode === "grid" ? (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                    {filteredAgents.map((agent) => (
                        <div
                            key={agent.id}
                            className="glass-card p-5 hover:border-stone-300 transition-all duration-300 animate-slide-up group"
                        >
                            <div className="flex items-start justify-between mb-4">
                                <div className="flex items-center gap-3">
                                    <div className="relative">
                                        <button
                                            type="button"
                                            onClick={(e) => { e.stopPropagation(); setAvatarPickerAgentId(avatarPickerAgentId === agent.id ? null : agent.id); }}
                                            className="rounded-lg hover:ring-2 hover:ring-stone-300 transition-all"
                                            title="Change avatar"
                                        >
                                            <AgentAvatar name={agent.name} avatarUrl={agent.avatar_url} size="md" />
                                        </button>
                                        {avatarPickerAgentId === agent.id && (
                                            <div className="absolute top-12 left-0 z-50 bg-white border border-stone-200 rounded-xl shadow-xl p-3 w-[280px]" onClick={e => e.stopPropagation()}>
                                                <p className="text-xs text-stone-500 mb-2">Pick an avatar</p>
                                                <AvatarPicker selected={agent.avatar_url ?? null} onSelect={(id) => handleAvatarChange(agent.id, id)} />
                                            </div>
                                        )}
                                    </div>
                                    <div>
                                        <h3 className="font-semibold text-stone-900">{agent.name}</h3>
                                        <div className="flex items-center gap-1.5 mt-0.5">
                                            <div className={`status-dot ${agent.status === "running" ? "status-dot-running" : agent.status === "starting" ? "status-dot-starting" : agent.status === "error" ? "status-dot-error" : "status-dot-stopped"}`} />
                                            <span className="text-xs text-stone-500 capitalize">{agent.status}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {agent.description && (
                                <p className="text-sm text-stone-500 mb-4 line-clamp-2">{agent.description}</p>
                            )}

                            <div className="flex items-center gap-2 mb-3">
                                {agent.purpose_id ? (
                                    <>
                                        <span className="px-2 py-0.5 rounded-md bg-violet-100 text-violet-700 text-[11px] font-medium uppercase tracking-wider">Smart</span>
                                        <span className="px-2 py-0.5 rounded-md bg-surface-2 border border-stone-200 text-stone-600 text-xs font-mono truncate max-w-[140px]" title={purposeNames[agent.purpose_id] ?? agent.purpose_id}>{purposeNames[agent.purpose_id] ?? agent.purpose_id}</span>
                                    </>
                                ) : (
                                    <>
                                        <span className="px-2 py-0.5 rounded-md bg-stone-100 text-stone-700 text-[11px] font-medium uppercase tracking-wider">{agent.llm_provider}</span>
                                        <span className="px-2 py-0.5 rounded-md bg-surface-2 border border-stone-200 text-stone-600 text-xs font-mono">{agent.llm_model}</span>
                                    </>
                                )}
                            </div>

                            <div className="flex items-center gap-2 mb-3 flex-wrap">
                                {agent.llm_provider === "ollama" && (
                                    <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-600 text-[11px] font-medium uppercase tracking-wider">Unlimited</span>
                                )}
                                {agent.llm_provider === "openrouter" && openRouterQuota && !openRouterQuota.error && (
                                    <span className="px-2 py-0.5 rounded-md bg-violet-50 text-violet-600 text-[11px] font-medium">
                                        {openRouterQuota.limit_remaining != null ? `$${openRouterQuota.limit_remaining.toFixed(2)} rem` : `$${(openRouterQuota.usage ?? 0).toFixed(2)} used`}
                                    </span>
                                )}
                                {agent.llm_provider === "google" && (
                                    <span className="px-2 py-0.5 rounded-md bg-blue-50 text-blue-600 text-[11px] font-medium uppercase tracking-wider">Free Tier</span>
                                )}
                                <span className="px-2 py-0.5 rounded-md bg-surface-2 border border-stone-200 text-stone-500 text-xs flex items-center gap-1">
                                    <Activity className="w-3 h-3" />
                                    {dailyUsage[agent.id] ?? 0} reqs today
                                </span>
                            </div>

                            <div className="flex items-center gap-2 pt-3 mt-auto border-t border-stone-100">
                                {agent.status === "running" ? (
                                    <>
                                        <button onClick={() => handleStop(agent.id)} disabled={actionLoading === agent.id} className="btn-secondary flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs">
                                            <Square className="w-3.5 h-3.5" /> Stop
                                        </button>
                                        <button onClick={() => handleRestart(agent.id)} disabled={actionLoading === agent.id} className="btn-secondary flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs">
                                            <RotateCw className="w-3.5 h-3.5" /> Restart
                                        </button>
                                    </>
                                ) : (
                                    <button onClick={() => handleStart(agent.id)} disabled={actionLoading === agent.id} className="btn-primary flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs">
                                        <Play className="w-3.5 h-3.5" /> Start
                                    </button>
                                )}
                                <Link href={`/agents/${agent.id}`} className="btn-secondary px-3 py-1.5 text-xs">Edit</Link>
                                <button onClick={() => handleClone(agent.id)} disabled={actionLoading === agent.id} className="btn-icon text-stone-400 hover:text-stone-700" title="Clone agent">
                                    <Copy className="w-4 h-4" />
                                </button>
                                <button onClick={() => handleDelete(agent.id)} className="btn-icon text-stone-400 hover:text-red-500">
                                    <Trash2 className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="glass-card overflow-x-auto animate-fade-in">
                    <table className="w-full text-left text-sm whitespace-nowrap">
                        <thead>
                            <tr className="border-b border-stone-200 text-stone-500">
                                <th className="px-4 py-3 font-medium">Name</th>
                                <th className="px-4 py-3 font-medium">Status</th>
                                <th className="px-4 py-3 font-medium">Model</th>
                                <th className="px-4 py-3 font-medium">Daily Usage</th>
                                <th className="px-4 py-3 font-medium text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-stone-100">
                            {filteredAgents.map((agent) => (
                                <tr key={agent.id} className="hover:bg-stone-50 transition-colors group">
                                    <td className="px-4 py-3">
                                        <div className="flex items-center gap-3">
                                            <AgentAvatar name={agent.name} avatarUrl={agent.avatar_url} size="sm" />
                                            <div>
                                                <div className="font-semibold text-stone-900">{agent.name}</div>
                                                {agent.description && (
                                                    <div className="text-[11px] text-stone-500 truncate max-w-[200px]">{agent.description}</div>
                                                )}
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex items-center gap-1.5">
                                            <div className={`status-dot ${agent.status === "running" ? "status-dot-running" : agent.status === "starting" ? "status-dot-starting" : agent.status === "error" ? "status-dot-error" : "status-dot-stopped"}`} />
                                            <span className="text-xs text-stone-600 capitalize">{agent.status}</span>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="flex items-center gap-2">
                                            {agent.purpose_id ? (
                                                <>
                                                    <span className="px-2 py-0.5 rounded-md bg-violet-100 text-violet-700 text-[10px] font-semibold uppercase tracking-wider">Smart</span>
                                                    <span className="text-xs text-stone-500 font-mono truncate max-w-[120px]" title={purposeNames[agent.purpose_id] ?? agent.purpose_id}>{purposeNames[agent.purpose_id] ?? agent.purpose_id}</span>
                                                </>
                                            ) : (
                                                <>
                                                    <span className="px-2 py-0.5 rounded-md bg-stone-100 text-stone-700 text-[10px] font-semibold uppercase tracking-wider">{agent.llm_provider}</span>
                                                    <span className="text-xs text-stone-500 font-mono truncate max-w-[120px]" title={agent.llm_model}>{agent.llm_model}</span>
                                                </>
                                            )}
                                        </div>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className="text-xs text-stone-500 font-mono">{dailyUsage[agent.id] ?? 0} reqs</span>
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        <div className="flex items-center justify-end gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                            {agent.status === "running" ? (
                                                <>
                                                    <button onClick={() => handleStop(agent.id)} disabled={actionLoading === agent.id} className="btn-secondary px-2 py-1" title="Stop"><Square className="w-3.5 h-3.5" /></button>
                                                    <button onClick={() => handleRestart(agent.id)} disabled={actionLoading === agent.id} className="btn-secondary px-2 py-1" title="Restart"><RotateCw className="w-3.5 h-3.5" /></button>
                                                </>
                                            ) : (
                                                <button onClick={() => handleStart(agent.id)} disabled={actionLoading === agent.id} className="btn-primary px-2 py-1" title="Start"><Play className="w-3.5 h-3.5" /></button>
                                            )}
                                            <Link href={`/agents/${agent.id}`} className="btn-secondary px-2 py-1" title="Edit"><Edit2 className="w-3.5 h-3.5" /></Link>
                                            <button onClick={() => handleClone(agent.id)} disabled={actionLoading === agent.id} className="btn-secondary px-2 py-1" title="Clone"><Copy className="w-3.5 h-3.5" /></button>
                                            <button onClick={() => handleDelete(agent.id)} className="btn-icon p-1 text-stone-400 hover:text-red-500" title="Delete"><Trash2 className="w-4 h-4" /></button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
