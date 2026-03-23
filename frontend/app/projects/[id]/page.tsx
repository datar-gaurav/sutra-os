"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
    FolderKanban, ArrowLeft, Brain, MessageSquare, Lightbulb, FileText,
    Plus, Trash2, Upload, Download, RefreshCw, Loader2, X, Clock,
    ChevronDown, ChevronRight, Edit2, Zap, Settings, KanbanSquare,
    Bot, CheckCircle2, Circle, AlertCircle,
} from "lucide-react";
import {
    projectsApi, agentsApi,
    Project, ProjectDecision, ProjectFile, Agent,
} from "@/lib/api";

type SubTab = "overview" | "tasks" | "memories" | "conversations" | "decisions" | "files";

const STATUS_COLORS: Record<string, string> = {
    backlog: "text-stone-400",
    todo: "text-blue-500",
    in_progress: "text-amber-500",
    review: "text-purple-500",
    done: "text-green-500",
};

const PRIORITY_STYLES: Record<string, string> = {
    critical: "bg-red-100 text-red-700",
    high: "bg-orange-100 text-orange-700",
    medium: "bg-blue-100 text-blue-700",
    low: "bg-stone-100 text-stone-500",
};

const IMPORTANCE_STYLES: Record<string, string> = {
    critical: "bg-red-50 text-red-700 border-red-200",
    high: "bg-orange-50 text-orange-700 border-orange-200",
    medium: "bg-blue-50 text-blue-700 border-blue-200",
    low: "bg-stone-50 text-stone-500 border-stone-200",
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ProjectDetailPage() {
    const { id } = useParams<{ id: string }>();
    const router = useRouter();
    const [project, setProject] = useState<Project | null>(null);
    const [tab, setTab] = useState<SubTab>("overview");
    const [loading, setLoading] = useState(true);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [tasks, setTasks] = useState<any[]>([]);
    const [memories, setMemories] = useState<any[]>([]);
    const [conversations, setConversations] = useState<any[]>([]);
    const [decisions, setDecisions] = useState<ProjectDecision[]>([]);
    const [files, setFiles] = useState<ProjectFile[]>([]);
    const [compacting, setCompacting] = useState(false);
    const [expandedDecision, setExpandedDecision] = useState<string | null>(null);
    const [memoryTier, setMemoryTier] = useState("");
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Edit project
    const [showEditProject, setShowEditProject] = useState(false);
    const [editName, setEditName] = useState("");
    const [editDescription, setEditDescription] = useState("");
    const [editStatus, setEditStatus] = useState("");
    const [editColor, setEditColor] = useState("");
    const [editDefaultAgent, setEditDefaultAgent] = useState("");
    const [saving, setSaving] = useState(false);

    // File upload
    const [uploading, setUploading] = useState(false);

    // Decision create
    const [showCreateDecision, setShowCreateDecision] = useState(false);
    const [decTitle, setDecTitle] = useState("");
    const [decDecision, setDecDecision] = useState("");
    const [decReasoning, setDecReasoning] = useState("");
    const [decImportance, setDecImportance] = useState("medium");

    useEffect(() => {
        loadProject();
        agentsApi.list().then(setAgents).catch(() => {});
    }, [id]);

    useEffect(() => {
        if (project) loadTabData();
    }, [tab, project, memoryTier]);

    async function loadProject() {
        setLoading(true);
        try {
            const p = await projectsApi.get(id);
            setProject(p);
        } catch {
            router.push("/projects");
        }
        setLoading(false);
    }

    async function loadTabData() {
        if (!project) return;
        try {
            if (tab === "tasks") {
                const t = await projectsApi.listTasks(id);
                setTasks(t);
            } else if (tab === "memories") {
                const m = await projectsApi.listMemories(id, { tier: memoryTier || undefined });
                setMemories(m);
            } else if (tab === "conversations") {
                const c = await projectsApi.listConversations(id);
                setConversations(c);
            } else if (tab === "decisions") {
                const d = await projectsApi.listDecisions(id);
                setDecisions(d);
            } else if (tab === "files") {
                const f = await projectsApi.listFiles(id);
                setFiles(f);
            }
        } catch (e) {
            console.error("Load tab data failed:", e);
        }
    }

    function openEditProject() {
        if (!project) return;
        setEditName(project.name);
        setEditDescription(project.description || "");
        setEditStatus(project.status);
        setEditColor(project.color || "#6b7280");
        setEditDefaultAgent(project.default_agent_id || "");
        setShowEditProject(true);
    }

    async function handleSaveProject() {
        if (!editName.trim()) return;
        setSaving(true);
        try {
            const updated = await projectsApi.update(id, {
                name: editName.trim(),
                description: editDescription.trim() || undefined,
                status: editStatus as any,
                color: editColor || undefined,
                default_agent_id: editDefaultAgent || undefined,
            });
            setProject(updated);
            setShowEditProject(false);
        } catch (e) {
            console.error("Update project failed:", e);
        }
        setSaving(false);
    }

    async function handleCompact() {
        setCompacting(true);
        try {
            const result = await projectsApi.compact(id);
            alert(`Compaction complete: ${result.consolidated} memories consolidated, ${result.decay_updated} decay scores updated`);
            loadProject();
        } catch (e) {
            console.error("Compaction failed:", e);
        }
        setCompacting(false);
    }

    async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
        const fileList = e.target.files;
        if (!fileList || fileList.length === 0) return;
        setUploading(true);
        const token = localStorage.getItem("sutra_access_token");
        for (let i = 0; i < fileList.length; i++) {
            const file = fileList[i];
            const formData = new FormData();
            formData.append("file", file);
            try {
                await fetch(`${API_BASE}/api/projects/${id}/files`, {
                    method: "POST",
                    headers: { Authorization: `Bearer ${token}` },
                    body: formData,
                });
            } catch (err) {
                console.error(`Upload failed for ${file.name}:`, err);
            }
        }
        setUploading(false);
        loadTabData();
        if (fileInputRef.current) fileInputRef.current.value = "";
    }

    async function handleDeleteFile(fileId: string) {
        if (!confirm("Delete this file?")) return;
        await projectsApi.deleteFile(id, fileId);
        loadTabData();
    }

    async function handleCreateDecision() {
        if (!decTitle || !decDecision || !decReasoning) return;
        try {
            await projectsApi.createDecision(id, {
                title: decTitle,
                decision: decDecision,
                reasoning: decReasoning,
                importance: decImportance,
            } as any);
            setShowCreateDecision(false);
            setDecTitle("");
            setDecDecision("");
            setDecReasoning("");
            loadTabData();
        } catch (e) {
            console.error("Create decision failed:", e);
        }
    }

    function formatDate(d: string | null) {
        if (!d) return "—";
        return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
    }

    function formatSize(bytes: number) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    if (loading || !project) {
        return (
            <div className="flex items-center justify-center h-96">
                <Loader2 className="w-6 h-6 animate-spin text-stone-400" />
            </div>
        );
    }

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Link href="/projects" className="p-1.5 rounded-lg hover:bg-stone-100 text-stone-400 hover:text-stone-600">
                        <ArrowLeft className="w-5 h-5" />
                    </Link>
                    <div className="w-4 h-4 rounded-full" style={{ backgroundColor: project.color || "#6b7280" }} />
                    <div>
                        <h1 className="text-2xl font-bold text-stone-900">{project.name}</h1>
                        {project.description && (
                            <p className="text-sm text-stone-500">{project.description}</p>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={openEditProject}
                        className="flex items-center gap-2 px-3 py-1.5 text-sm border border-stone-200 rounded-lg hover:bg-stone-50 text-stone-600"
                    >
                        <Edit2 className="w-4 h-4" />
                        Edit
                    </button>
                    <button
                        onClick={handleCompact}
                        disabled={compacting}
                        className="flex items-center gap-2 px-3 py-1.5 text-sm border border-stone-200 rounded-lg hover:bg-stone-50 text-stone-600 disabled:opacity-40"
                    >
                        <RefreshCw className={`w-4 h-4 ${compacting ? "animate-spin" : ""}`} />
                        Compact
                    </button>
                </div>
            </div>

            {/* Stats bar */}
            <div className="flex gap-6 text-sm text-stone-500">
                <span className="flex items-center gap-1.5">
                    <KanbanSquare className="w-4 h-4" />
                    {project.task_count || 0} tasks
                </span>
                <span className="flex items-center gap-1.5">
                    <Brain className="w-4 h-4" />
                    {project.memory_count} memories
                </span>
                <span className="flex items-center gap-1.5">
                    <MessageSquare className="w-4 h-4" />
                    {project.conversation_count} conversations
                </span>
                <span className="flex items-center gap-1.5">
                    <Clock className="w-4 h-4" />
                    Last active: {formatDate(project.last_active_at)}
                </span>
                {project.slug && (
                    <span className="text-xs text-stone-400 font-mono">@{project.slug}</span>
                )}
            </div>

            {/* Sub-tabs */}
            <div className="flex gap-1 bg-stone-100 rounded-lg p-1 w-fit">
                {(["overview", "tasks", "memories", "conversations", "decisions", "files"] as SubTab[]).map((t) => (
                    <button
                        key={t}
                        onClick={() => setTab(t)}
                        className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize ${
                            tab === t ? "bg-white text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-700"
                        }`}
                    >
                        {t}
                    </button>
                ))}
            </div>

            {/* Overview */}
            {tab === "overview" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-white border border-stone-200 rounded-xl p-5 space-y-3">
                        <h3 className="text-sm font-semibold text-stone-700 flex items-center gap-2">
                            <Settings className="w-4 h-4" /> Details
                        </h3>
                        <div className="space-y-2 text-sm">
                            <div className="flex justify-between">
                                <span className="text-stone-500">Status</span>
                                <span className="text-stone-800 capitalize">{project.status.replace("_", " ")}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-stone-500">Default Agent</span>
                                <span className="text-stone-800">
                                    {project.default_agent_id
                                        ? agents.find(a => a.id === project.default_agent_id)?.name || "—"
                                        : "—"}
                                </span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-stone-500">Created</span>
                                <span className="text-stone-800">{formatDate(project.created_at)}</span>
                            </div>
                            {project.compaction_summary && (
                                <div className="pt-2 border-t border-stone-100">
                                    <span className="text-xs text-stone-400">{project.compaction_summary}</span>
                                </div>
                            )}
                        </div>
                    </div>
                    <div className="bg-white border border-stone-200 rounded-xl p-5 space-y-3">
                        <h3 className="text-sm font-semibold text-stone-700 flex items-center gap-2">
                            <Zap className="w-4 h-4" /> Quick Actions
                        </h3>
                        <div className="space-y-2">
                            {agents.slice(0, 3).map((a) => (
                                <button
                                    key={a.id}
                                    onClick={async () => {
                                        try {
                                            await projectsApi.switchAgent(project.id, a.id);
                                            alert(`${a.name} switched to project ${project.name}`);
                                        } catch (e) {
                                            console.error(e);
                                        }
                                    }}
                                    className="w-full text-left px-3 py-2 text-sm border border-stone-100 rounded-lg hover:bg-stone-50 text-stone-600"
                                >
                                    Switch <span className="font-medium">{a.name}</span> to this project
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* Tasks */}
            {tab === "tasks" && (
                <div className="space-y-4">
                    {tasks.length > 0 && (
                        <div className="flex gap-3 flex-wrap">
                            {["backlog", "todo", "in_progress", "review", "done"].map((s) => {
                                const count = tasks.filter((t: any) => t.status === s).length;
                                if (count === 0) return null;
                                return (
                                    <span key={s} className="text-xs flex items-center gap-1.5 text-stone-500">
                                        <span className={`w-2 h-2 rounded-full ${STATUS_COLORS[s]?.replace("text-", "bg-") || "bg-stone-400"}`} />
                                        {s.replace("_", " ")} ({count})
                                    </span>
                                );
                            })}
                        </div>
                    )}
                    <div className="space-y-2">
                        {tasks.map((t: any) => (
                            <div key={t.id} className="bg-white border border-stone-200 rounded-lg px-4 py-3">
                                <div className="flex items-start justify-between">
                                    <div className="flex items-start gap-3 flex-1 min-w-0">
                                        {t.status === "done" ? (
                                            <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                                        ) : t.status === "in_progress" ? (
                                            <Loader2 className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                                        ) : (
                                            <Circle className={`w-4 h-4 flex-shrink-0 mt-0.5 ${STATUS_COLORS[t.status] || "text-stone-400"}`} />
                                        )}
                                        <div className="min-w-0">
                                            <p className={`text-sm font-medium ${t.status === "done" ? "text-stone-400 line-through" : "text-stone-800"}`}>
                                                {t.title}
                                            </p>
                                            {t.description && (
                                                <p className="text-xs text-stone-400 mt-0.5 line-clamp-1">{t.description}</p>
                                            )}
                                            <div className="flex items-center gap-3 mt-1.5 text-xs text-stone-400">
                                                {t.assignee_agent_name && (
                                                    <span className="flex items-center gap-1">
                                                        <Bot className="w-3 h-3" />
                                                        {t.assignee_agent_name}
                                                    </span>
                                                )}
                                                {t.due_date && (
                                                    <span className="flex items-center gap-1">
                                                        <Clock className="w-3 h-3" />
                                                        {formatDate(t.due_date)}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${PRIORITY_STYLES[t.priority] || PRIORITY_STYLES.medium}`}>
                                            {t.priority}
                                        </span>
                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-stone-100 text-stone-500 capitalize">
                                            {(t.status || "").replace("_", " ")}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        ))}
                        {tasks.length === 0 && (
                            <div className="text-center py-12 text-stone-400">
                                <KanbanSquare className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                <p>No tasks in this project yet.</p>
                                <p className="text-xs mt-1">Create tasks on the <a href="/tasks" className="text-stone-600 underline">Tasks page</a> and assign them to this project.</p>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Memories */}
            {tab === "memories" && (
                <div className="space-y-4">
                    <div className="flex items-center gap-2">
                        <select
                            value={memoryTier}
                            onChange={(e) => setMemoryTier(e.target.value)}
                            className="px-3 py-1.5 text-sm border border-stone-200 rounded-lg"
                        >
                            <option value="">All tiers</option>
                            <option value="core">Core</option>
                            <option value="recall">Recall</option>
                            <option value="archival">Archival</option>
                        </select>
                    </div>
                    <div className="space-y-2">
                        {memories.map((m: any) => (
                            <div key={m.id} className="bg-white border border-stone-200 rounded-lg px-4 py-3">
                                <div className="flex items-start justify-between">
                                    <p className="text-sm text-stone-700 flex-1">{m.content}</p>
                                    <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                                        <span className="text-xs px-2 py-0.5 rounded bg-stone-100 text-stone-500">{m.tier}</span>
                                        <span className="text-xs px-2 py-0.5 rounded bg-stone-100 text-stone-500">{m.type}</span>
                                    </div>
                                </div>
                                <div className="flex items-center gap-4 mt-2 text-xs text-stone-400">
                                    <span>Importance: {(m.importance_score * 100).toFixed(0)}%</span>
                                    <span>Decay: {(m.decay_score * 100).toFixed(0)}%</span>
                                    <span>{formatDate(m.created_at)}</span>
                                </div>
                            </div>
                        ))}
                        {memories.length === 0 && (
                            <div className="text-center py-12 text-stone-400">
                                <Brain className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                No project memories yet. Memories are created as you chat with agents in this project context.
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Conversations */}
            {tab === "conversations" && (
                <div className="space-y-2">
                    {conversations.map((c: any) => (
                        <div key={c.id} className="bg-white border border-stone-200 rounded-lg px-4 py-3 flex items-center justify-between">
                            <div className="flex items-center gap-3 min-w-0">
                                <div className="p-1.5 rounded-lg bg-stone-100 flex-shrink-0">
                                    <Bot className="w-4 h-4 text-stone-500" />
                                </div>
                                <div className="min-w-0">
                                    <p className="text-sm font-medium text-stone-800 truncate">{c.title || "Untitled"}</p>
                                    <div className="flex items-center gap-3 text-xs text-stone-400 mt-0.5">
                                        <span className="font-medium text-stone-500">{c.agent_name || "Agent"}</span>
                                        <span>{c.message_count || 0} messages</span>
                                        <span>{formatDate(c.created_at)}</span>
                                    </div>
                                </div>
                            </div>
                            <span className="text-xs text-stone-400 flex-shrink-0 ml-3">{c.source}</span>
                        </div>
                    ))}
                    {conversations.length === 0 && (
                        <div className="text-center py-12 text-stone-400">
                            <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-30" />
                            <p>No conversations linked to this project yet.</p>
                            <p className="text-xs mt-1">Conversations are linked when you chat with an agent that has this project active.</p>
                        </div>
                    )}
                </div>
            )}

            {/* Decisions */}
            {tab === "decisions" && (
                <div className="space-y-4">
                    <div className="flex justify-end">
                        <button
                            onClick={() => setShowCreateDecision(true)}
                            className="flex items-center gap-2 px-3 py-1.5 text-sm bg-stone-900 text-white rounded-lg hover:bg-stone-800"
                        >
                            <Plus className="w-4 h-4" /> Record Decision
                        </button>
                    </div>
                    <div className="space-y-2">
                        {decisions.map((d) => (
                            <div key={d.id} className="bg-white border border-stone-200 rounded-lg overflow-hidden">
                                <button
                                    onClick={() => setExpandedDecision(expandedDecision === d.id ? null : d.id)}
                                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-stone-50 text-left"
                                >
                                    <div className="flex items-center gap-2">
                                        {expandedDecision === d.id ? <ChevronDown className="w-3.5 h-3.5 text-stone-400" /> : <ChevronRight className="w-3.5 h-3.5 text-stone-400" />}
                                        <span className="text-sm font-medium text-stone-800">{d.title}</span>
                                        <span className={`text-xs px-2 py-0.5 rounded-full border ${IMPORTANCE_STYLES[d.importance] || IMPORTANCE_STYLES.medium}`}>
                                            {d.importance}
                                        </span>
                                    </div>
                                    <span className="text-xs text-stone-400">{formatDate(d.created_at)}</span>
                                </button>
                                {expandedDecision === d.id && (
                                    <div className="border-t border-stone-100 px-4 py-3 bg-stone-50 space-y-2">
                                        <div>
                                            <span className="text-xs font-medium text-stone-500 uppercase">Decision:</span>
                                            <p className="text-sm text-stone-700 mt-0.5">{d.decision}</p>
                                        </div>
                                        <div>
                                            <span className="text-xs font-medium text-stone-500 uppercase">Reasoning:</span>
                                            <p className="text-sm text-stone-700 mt-0.5">{d.reasoning}</p>
                                        </div>
                                        {d.data_points && Object.keys(d.data_points).length > 0 && (
                                            <div>
                                                <span className="text-xs font-medium text-stone-500 uppercase">Data Points:</span>
                                                <div className="flex flex-wrap gap-2 mt-1">
                                                    {Object.entries(d.data_points).map(([k, v]) => (
                                                        <span key={k} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded border border-blue-200">
                                                            {k}: {String(v)}
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                        {decisions.length === 0 && (
                            <div className="text-center py-12 text-stone-400">
                                <Lightbulb className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                No decisions recorded. Use the button above or let agents auto-extract them from conversations.
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Files */}
            {tab === "files" && (
                <div className="space-y-4">
                    {/* Drop zone */}
                    <div
                        onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add("border-stone-400", "bg-stone-50"); }}
                        onDragLeave={(e) => { e.currentTarget.classList.remove("border-stone-400", "bg-stone-50"); }}
                        onDrop={(e) => {
                            e.preventDefault();
                            e.currentTarget.classList.remove("border-stone-400", "bg-stone-50");
                            if (e.dataTransfer.files.length > 0) {
                                const dt = new DataTransfer();
                                Array.from(e.dataTransfer.files).forEach(f => dt.items.add(f));
                                if (fileInputRef.current) {
                                    fileInputRef.current.files = dt.files;
                                    fileInputRef.current.dispatchEvent(new Event("change", { bubbles: true }));
                                }
                            }
                        }}
                        className="border-2 border-dashed border-stone-200 rounded-xl p-6 text-center transition-colors cursor-pointer"
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileUpload} multiple />
                        {uploading ? (
                            <div className="flex items-center justify-center gap-2 text-stone-500">
                                <Loader2 className="w-5 h-5 animate-spin" />
                                <span className="text-sm">Uploading files...</span>
                            </div>
                        ) : (
                            <>
                                <Upload className="w-6 h-6 mx-auto mb-2 text-stone-300" />
                                <p className="text-sm text-stone-500">Drop files here or click to upload</p>
                                <p className="text-xs text-stone-400 mt-1">Supports multiple files</p>
                            </>
                        )}
                    </div>

                    <div className="space-y-2">
                        {files.map((f) => (
                            <div key={f.id} className="bg-white border border-stone-200 rounded-lg px-4 py-3 flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <FileText className="w-4 h-4 text-stone-400" />
                                    <div>
                                        <p className="text-sm font-medium text-stone-800">{f.file_name}</p>
                                        <span className="text-xs text-stone-400">{formatSize(f.file_size)} · {f.mime_type || "unknown"} · {formatDate(f.created_at)}</span>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <a
                                        href={`${API_BASE}/api/projects/${id}/files/${f.id}/download`}
                                        className="p-1.5 rounded-lg hover:bg-stone-100 text-stone-400 hover:text-stone-600"
                                        title="Download"
                                    >
                                        <Download className="w-4 h-4" />
                                    </a>
                                    <button
                                        onClick={() => handleDeleteFile(f.id)}
                                        className="p-1.5 rounded-lg hover:bg-red-50 text-stone-400 hover:text-red-600"
                                        title="Delete"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        ))}
                        {files.length === 0 && !uploading && (
                            <p className="text-center text-sm text-stone-400 py-4">No files uploaded yet.</p>
                        )}
                    </div>
                </div>
            )}

            {/* Edit Project Modal */}
            {showEditProject && (
                <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setShowEditProject(false)}>
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-semibold text-stone-900">Edit Project</h2>
                            <button onClick={() => setShowEditProject(false)} className="text-stone-400 hover:text-stone-600">
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="space-y-3">
                            <div>
                                <label className="text-xs font-medium text-stone-600">Name *</label>
                                <input
                                    value={editName}
                                    onChange={(e) => setEditName(e.target.value)}
                                    className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm"
                                />
                            </div>
                            <div>
                                <label className="text-xs font-medium text-stone-600">Description</label>
                                <textarea
                                    value={editDescription}
                                    onChange={(e) => setEditDescription(e.target.value)}
                                    rows={3}
                                    className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm"
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-xs font-medium text-stone-600">Status</label>
                                    <select
                                        value={editStatus}
                                        onChange={(e) => setEditStatus(e.target.value)}
                                        className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm"
                                    >
                                        <option value="active">Active</option>
                                        <option value="on_hold">On Hold</option>
                                        <option value="completed">Completed</option>
                                        <option value="archived">Archived</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-medium text-stone-600">Color</label>
                                    <div className="flex items-center gap-2 mt-1">
                                        <input
                                            type="color"
                                            value={editColor}
                                            onChange={(e) => setEditColor(e.target.value)}
                                            className="w-10 h-10 rounded-lg border border-stone-200 cursor-pointer p-0.5"
                                        />
                                        <input
                                            value={editColor}
                                            onChange={(e) => setEditColor(e.target.value)}
                                            className="flex-1 px-3 py-2 border border-stone-200 rounded-lg text-sm font-mono"
                                            placeholder="#6b7280"
                                        />
                                    </div>
                                </div>
                            </div>
                            <div>
                                <label className="text-xs font-medium text-stone-600">Default Agent</label>
                                <select
                                    value={editDefaultAgent}
                                    onChange={(e) => setEditDefaultAgent(e.target.value)}
                                    className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm"
                                >
                                    <option value="">None</option>
                                    {agents.map((a) => (
                                        <option key={a.id} value={a.id}>{a.name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2 pt-2">
                            <button onClick={() => setShowEditProject(false)} className="px-4 py-2 text-sm text-stone-600">
                                Cancel
                            </button>
                            <button
                                onClick={handleSaveProject}
                                disabled={!editName.trim() || saving}
                                className="flex items-center gap-2 px-4 py-2 text-sm bg-stone-900 text-white rounded-lg hover:bg-stone-800 disabled:opacity-40"
                            >
                                {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                                Save Changes
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Create Decision Modal */}
            {showCreateDecision && (
                <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setShowCreateDecision(false)}>
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-semibold text-stone-900">Record Decision</h2>
                            <button onClick={() => setShowCreateDecision(false)} className="text-stone-400 hover:text-stone-600">
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="space-y-3">
                            <div>
                                <label className="text-xs font-medium text-stone-600">Title *</label>
                                <input
                                    value={decTitle}
                                    onChange={(e) => setDecTitle(e.target.value)}
                                    className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm"
                                    placeholder="What was decided?"
                                />
                            </div>
                            <div>
                                <label className="text-xs font-medium text-stone-600">Decision *</label>
                                <textarea
                                    value={decDecision}
                                    onChange={(e) => setDecDecision(e.target.value)}
                                    rows={2}
                                    className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm"
                                    placeholder="The decision itself"
                                />
                            </div>
                            <div>
                                <label className="text-xs font-medium text-stone-600">Reasoning *</label>
                                <textarea
                                    value={decReasoning}
                                    onChange={(e) => setDecReasoning(e.target.value)}
                                    rows={2}
                                    className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm"
                                    placeholder="Why was this decided?"
                                />
                            </div>
                            <div>
                                <label className="text-xs font-medium text-stone-600">Importance</label>
                                <select
                                    value={decImportance}
                                    onChange={(e) => setDecImportance(e.target.value)}
                                    className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm"
                                >
                                    <option value="low">Low</option>
                                    <option value="medium">Medium</option>
                                    <option value="high">High</option>
                                    <option value="critical">Critical</option>
                                </select>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2 pt-2">
                            <button onClick={() => setShowCreateDecision(false)} className="px-4 py-2 text-sm text-stone-600">
                                Cancel
                            </button>
                            <button
                                onClick={handleCreateDecision}
                                disabled={!decTitle || !decDecision || !decReasoning}
                                className="px-4 py-2 text-sm bg-stone-900 text-white rounded-lg hover:bg-stone-800 disabled:opacity-40"
                            >
                                Save Decision
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
