"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
    FolderKanban, Plus, Trash2, Edit2, Brain, MessageSquare, Zap, Clock,
    ChevronDown, ChevronRight, Loader2, X, Search, FileText, Lightbulb,
    ArrowRight, RefreshCw, KanbanSquare,
} from "lucide-react";
import {
    projectsApi, agentsApi,
    Project, ProjectDecision, ProjectFile, Agent,
} from "@/lib/api";

type Tab = "projects" | "decisions" | "files";

const STATUS_STYLES: Record<string, string> = {
    active: "bg-green-50 text-green-700 border-green-200",
    on_hold: "bg-yellow-50 text-yellow-700 border-yellow-200",
    completed: "bg-blue-50 text-blue-700 border-blue-200",
    archived: "bg-stone-100 text-stone-500 border-stone-200",
};

const IMPORTANCE_STYLES: Record<string, string> = {
    critical: "bg-red-50 text-red-700 border-red-200",
    high: "bg-orange-50 text-orange-700 border-orange-200",
    medium: "bg-blue-50 text-blue-700 border-blue-200",
    low: "bg-stone-50 text-stone-500 border-stone-200",
};

const COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6", "#8b5cf6", "#ec4899", "#6b7280"];

export default function ProjectsPage() {
    const [tab, setTab] = useState<Tab>("projects");
    const [projects, setProjects] = useState<Project[]>([]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [decisions, setDecisions] = useState<ProjectDecision[]>([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [expandedDecision, setExpandedDecision] = useState<string | null>(null);

    // Create form
    const [newName, setNewName] = useState("");
    const [newDesc, setNewDesc] = useState("");
    const [newColor, setNewColor] = useState(COLORS[0]);
    const [newIcon, setNewIcon] = useState("");
    const [newAgentId, setNewAgentId] = useState("");

    useEffect(() => {
        load();
    }, []);

    async function load() {
        setLoading(true);
        try {
            const [p, a] = await Promise.all([
                projectsApi.list(),
                agentsApi.list(),
            ]);
            setProjects(p);
            setAgents(a);

            // Load decisions across all projects
            const allDecs: ProjectDecision[] = [];
            for (const proj of p.slice(0, 10)) {
                try {
                    const decs = await projectsApi.listDecisions(proj.id);
                    allDecs.push(...decs);
                } catch { /* ignore */ }
            }
            setDecisions(allDecs.sort((a, b) => b.created_at.localeCompare(a.created_at)));
        } catch (e) {
            console.error("Failed to load projects:", e);
        }
        setLoading(false);
    }

    async function handleCreate() {
        if (!newName.trim()) return;
        try {
            await projectsApi.create({
                name: newName,
                description: newDesc || undefined,
                color: newColor,
                icon: newIcon || undefined,
                default_agent_id: newAgentId || undefined,
            } as any);
            setShowCreate(false);
            setNewName("");
            setNewDesc("");
            load();
        } catch (e) {
            console.error("Failed to create project:", e);
        }
    }

    async function handleDelete(id: string) {
        if (!confirm("Archive this project?")) return;
        await projectsApi.delete(id);
        load();
    }

    function formatDate(d: string | null) {
        if (!d) return "Never";
        return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    }

    if (loading) {
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
                    <div className="p-2 bg-stone-100 rounded-lg">
                        <FolderKanban className="w-6 h-6 text-stone-600" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-stone-900">Projects</h1>
                        <p className="text-sm text-stone-500">Manage project-scoped memory, decisions, and files</p>
                    </div>
                </div>
                <button
                    onClick={() => setShowCreate(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-stone-900 text-white rounded-lg hover:bg-stone-800 transition-colors text-sm"
                >
                    <Plus className="w-4 h-4" />
                    New Project
                </button>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-stone-100 rounded-lg p-1 w-fit">
                {(["projects", "decisions", "files"] as Tab[]).map((t) => (
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

            {/* Projects Grid */}
            {tab === "projects" && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {projects.map((p) => (
                        <Link
                            key={p.id}
                            href={`/projects/${p.id}`}
                            className="bg-white border border-stone-200 rounded-xl p-5 hover:shadow-md transition-all group"
                        >
                            <div className="flex items-start justify-between mb-3">
                                <div className="flex items-center gap-2">
                                    <div
                                        className="w-3 h-3 rounded-full flex-shrink-0"
                                        style={{ backgroundColor: p.color || "#6b7280" }}
                                    />
                                    <h3 className="font-semibold text-stone-900 group-hover:text-stone-700">{p.name}</h3>
                                </div>
                                <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_STYLES[p.status] || STATUS_STYLES.active}`}>
                                    {p.status.replace("_", " ")}
                                </span>
                            </div>
                            {p.description && (
                                <p className="text-sm text-stone-500 mb-3 line-clamp-2">{p.description}</p>
                            )}
                            <div className="flex items-center gap-4 text-xs text-stone-400">
                                <span className="flex items-center gap-1">
                                    <KanbanSquare className="w-3 h-3" />
                                    {p.task_count || 0} tasks
                                </span>
                                <span className="flex items-center gap-1">
                                    <Brain className="w-3 h-3" />
                                    {p.memory_count} memories
                                </span>
                                <span className="flex items-center gap-1">
                                    <MessageSquare className="w-3 h-3" />
                                    {p.conversation_count} convos
                                </span>
                                <span className="flex items-center gap-1">
                                    <Clock className="w-3 h-3" />
                                    {formatDate(p.last_active_at)}
                                </span>
                            </div>
                        </Link>
                    ))}
                    {projects.length === 0 && (
                        <div className="col-span-full text-center py-12 text-stone-400">
                            <FolderKanban className="w-12 h-12 mx-auto mb-3 opacity-30" />
                            <p>No projects yet. Create one to get started.</p>
                        </div>
                    )}
                </div>
            )}

            {/* Decisions Table */}
            {tab === "decisions" && (
                <div className="bg-white border border-stone-200 rounded-xl overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-stone-50 border-b border-stone-200">
                            <tr>
                                <th className="text-left px-4 py-3 font-medium text-stone-600">Decision</th>
                                <th className="text-left px-4 py-3 font-medium text-stone-600">Project</th>
                                <th className="text-left px-4 py-3 font-medium text-stone-600">Importance</th>
                                <th className="text-left px-4 py-3 font-medium text-stone-600">Date</th>
                            </tr>
                        </thead>
                        <tbody>
                            {decisions.map((d) => {
                                const proj = projects.find((p) => p.id === d.project_id);
                                const isExpanded = expandedDecision === d.id;
                                return (
                                    <>
                                        <tr
                                            key={d.id}
                                            onClick={() => setExpandedDecision(isExpanded ? null : d.id)}
                                            className="border-b border-stone-100 hover:bg-stone-50 cursor-pointer"
                                        >
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-2">
                                                    {isExpanded ? <ChevronDown className="w-3.5 h-3.5 text-stone-400" /> : <ChevronRight className="w-3.5 h-3.5 text-stone-400" />}
                                                    <span className="font-medium text-stone-800">{d.title}</span>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-stone-500">{proj?.name || "—"}</td>
                                            <td className="px-4 py-3">
                                                <span className={`text-xs px-2 py-0.5 rounded-full border ${IMPORTANCE_STYLES[d.importance] || IMPORTANCE_STYLES.medium}`}>
                                                    {d.importance}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-stone-400">{formatDate(d.created_at)}</td>
                                        </tr>
                                        {isExpanded && (
                                            <tr key={`${d.id}-detail`} className="bg-stone-50">
                                                <td colSpan={4} className="px-4 py-4">
                                                    <div className="space-y-2 pl-6">
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
                                                        {d.tags.length > 0 && (
                                                            <div className="flex gap-1">
                                                                {d.tags.map((t) => (
                                                                    <span key={t} className="text-xs bg-stone-100 text-stone-500 px-1.5 py-0.5 rounded">{t}</span>
                                                                ))}
                                                            </div>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        )}
                                    </>
                                );
                            })}
                            {decisions.length === 0 && (
                                <tr>
                                    <td colSpan={4} className="px-4 py-12 text-center text-stone-400">
                                        <Lightbulb className="w-8 h-8 mx-auto mb-2 opacity-30" />
                                        No decisions tracked yet. Decisions are auto-extracted from conversations when a project is active.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Files (grouped by project) */}
            {tab === "files" && (
                <div className="space-y-4">
                    {projects.map((p) => (
                        <ProjectFilesSection key={p.id} project={p} />
                    ))}
                    {projects.length === 0 && (
                        <div className="text-center py-12 text-stone-400">
                            <FileText className="w-8 h-8 mx-auto mb-2 opacity-30" />
                            No projects yet.
                        </div>
                    )}
                </div>
            )}

            {/* Create Modal */}
            {showCreate && (
                <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setShowCreate(false)}>
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-semibold text-stone-900">New Project</h2>
                            <button onClick={() => setShowCreate(false)} className="text-stone-400 hover:text-stone-600">
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="space-y-3">
                            <div>
                                <label className="text-xs font-medium text-stone-600">Name *</label>
                                <input
                                    value={newName}
                                    onChange={(e) => setNewName(e.target.value)}
                                    className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-300"
                                    placeholder="My Project"
                                />
                            </div>
                            <div>
                                <label className="text-xs font-medium text-stone-600">Description</label>
                                <textarea
                                    value={newDesc}
                                    onChange={(e) => setNewDesc(e.target.value)}
                                    rows={2}
                                    className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-300"
                                    placeholder="What is this project about?"
                                />
                            </div>
                            <div>
                                <label className="text-xs font-medium text-stone-600">Color</label>
                                <div className="flex gap-2 mt-1">
                                    {COLORS.map((c) => (
                                        <button
                                            key={c}
                                            onClick={() => setNewColor(c)}
                                            className={`w-6 h-6 rounded-full border-2 transition-all ${
                                                newColor === c ? "border-stone-900 scale-110" : "border-transparent"
                                            }`}
                                            style={{ backgroundColor: c }}
                                        />
                                    ))}
                                </div>
                            </div>
                            <div>
                                <label className="text-xs font-medium text-stone-600">Default Agent</label>
                                <select
                                    value={newAgentId}
                                    onChange={(e) => setNewAgentId(e.target.value)}
                                    className="w-full mt-1 px-3 py-2 border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-300"
                                >
                                    <option value="">None</option>
                                    {agents.map((a) => (
                                        <option key={a.id} value={a.id}>{a.name}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2 pt-2">
                            <button onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-stone-600 hover:text-stone-800">
                                Cancel
                            </button>
                            <button
                                onClick={handleCreate}
                                disabled={!newName.trim()}
                                className="px-4 py-2 text-sm bg-stone-900 text-white rounded-lg hover:bg-stone-800 disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                                Create
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function ProjectFilesSection({ project }: { project: Project }) {
    const [files, setFiles] = useState<ProjectFile[]>([]);
    const [expanded, setExpanded] = useState(false);

    useEffect(() => {
        if (expanded && files.length === 0) {
            projectsApi.listFiles(project.id).then(setFiles).catch(() => {});
        }
    }, [expanded, project.id]);

    function formatSize(bytes: number) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    return (
        <div className="bg-white border border-stone-200 rounded-xl overflow-hidden">
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-stone-50 transition-colors"
            >
                <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: project.color || "#6b7280" }} />
                    <span className="font-medium text-sm text-stone-800">{project.name}</span>
                </div>
                {expanded ? <ChevronDown className="w-4 h-4 text-stone-400" /> : <ChevronRight className="w-4 h-4 text-stone-400" />}
            </button>
            {expanded && (
                <div className="border-t border-stone-100 px-4 py-3">
                    {files.length === 0 ? (
                        <p className="text-sm text-stone-400 text-center py-4">No files uploaded yet</p>
                    ) : (
                        <div className="space-y-2">
                            {files.map((f) => (
                                <div key={f.id} className="flex items-center justify-between text-sm">
                                    <div className="flex items-center gap-2">
                                        <FileText className="w-4 h-4 text-stone-400" />
                                        <span className="text-stone-700">{f.file_name}</span>
                                        <span className="text-stone-400 text-xs">{formatSize(f.file_size)}</span>
                                    </div>
                                    <span className="text-xs text-stone-400">{new Date(f.created_at).toLocaleDateString()}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
