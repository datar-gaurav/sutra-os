"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
    Sparkles, Plus, Search, Code2, Globe, Mail, BarChart3, FileText,
    ClipboardList, Database, Languages, BookOpen, ShieldCheck, HeartHandshake,
    KanbanSquare, Upload, Github, Bot, Pencil, Trash2, X, Download,
    ChevronDown, ChevronUp, RefreshCw, CheckCircle, AlertCircle,
} from "lucide-react";
import { skillsApi, agentsApi, Skill, Agent } from "@/lib/api";

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
    Code2, Globe, Mail, BarChart3, FileText, ClipboardList, Database,
    Languages, BookOpen, ShieldCheck, HeartHandshake, KanbanSquare, Upload,
    Github, Search, Sparkles, Bot,
};

const CATEGORY_LABELS: Record<string, string> = {
    all: "All",
    coding: "Coding",
    research: "Research",
    writing: "Writing",
    data: "Data",
    communication: "Communication",
    automation: "Automation",
    general: "General",
};

function SkillIcon({ icon, color, size = "md" }: { icon: string | null; color: string | null; size?: "sm" | "md" }) {
    const Icon = (icon && ICON_MAP[icon]) ? ICON_MAP[icon] : Sparkles;
    const sz = size === "sm" ? "w-9 h-9" : "w-10 h-10";
    const isz = size === "sm" ? "w-4 h-4" : "w-5 h-5";
    return (
        <div
            className={`${sz} rounded-xl flex items-center justify-center flex-shrink-0`}
            style={{ backgroundColor: (color || "#6366f1") + "18", border: `1px solid ${color || "#6366f1"}30` }}
        >
            <Icon className={isz} style={{ color: color || "#6366f1" }} />
        </div>
    );
}

// ─── Attach Skill Modal ───────────────────────────────────────────────────────

function AttachSkillModal({ skill, onClose, onDone }: { skill: Skill; onClose: () => void; onDone: () => void }) {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [agentId, setAgentId] = useState("");
    const [priority, setPriority] = useState(0);
    const [overrides, setOverrides] = useState<Record<string, string>>({});
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => { agentsApi.list().then(setAgents).catch(() => {}); }, []);

    const schemaProps = skill.config_schema?.properties as Record<string, any> ?? {};

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!agentId) { setError("Please select an agent"); return; }
        setSaving(true); setError("");
        try {
            await skillsApi.attachToAgent(agentId, { skill_id: skill.id, priority, config_overrides: overrides });
            onDone(); onClose();
        } catch (err: any) {
            setError(err.message || "Failed to attach skill");
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
                <div className="p-5 border-b border-stone-100 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <SkillIcon icon={skill.icon} color={skill.color} size="sm" />
                        <div>
                            <h2 className="text-base font-semibold text-stone-900">Attach Skill</h2>
                            <p className="text-xs text-stone-500">{skill.name}</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-stone-100 rounded-lg text-stone-400"><X className="w-4 h-4" /></button>
                </div>

                {error && (
                    <div className="mx-5 mt-4 flex items-center gap-2 text-red-600 text-sm bg-red-50 rounded-lg p-3">
                        <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="p-5 space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">Agent *</label>
                        <select
                            value={agentId} onChange={e => setAgentId(e.target.value)}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                        >
                            <option value="">Select agent…</option>
                            {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                        </select>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">Priority <span className="text-stone-400 font-normal">(lower = applied first)</span></label>
                        <input type="number" value={priority} onChange={e => setPriority(Number(e.target.value))}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                    </div>

                    {Object.keys(schemaProps).length > 0 && (
                        <div className="space-y-3">
                            <p className="text-sm font-medium text-stone-700">Configuration</p>
                            {Object.entries(schemaProps).map(([key, prop]: [string, any]) => (
                                <div key={key}>
                                    <label className="block text-xs font-medium text-stone-600 mb-1">
                                        {prop.description || key}
                                        {prop.default !== undefined && <span className="ml-1 text-stone-400 font-normal">default: {String(prop.default)}</span>}
                                    </label>
                                    {prop.enum ? (
                                        <select value={overrides[key] ?? prop.default ?? ""} onChange={e => setOverrides(o => ({ ...o, [key]: e.target.value }))}
                                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600">
                                            {prop.enum.map((v: string) => <option key={v} value={v}>{v}</option>)}
                                        </select>
                                    ) : (
                                        <input type={prop.type === "number" ? "number" : "text"} placeholder={String(prop.default ?? "")}
                                            value={overrides[key] ?? ""} onChange={e => setOverrides(o => ({ ...o, [key]: e.target.value }))}
                                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    <div className="flex gap-3 pt-1">
                        <button type="button" onClick={onClose} className="flex-1 px-4 py-2 border border-stone-200 rounded-lg text-stone-600 text-sm hover:bg-stone-50">Cancel</button>
                        <button type="submit" disabled={saving} className="flex-1 px-4 py-2 bg-stone-700 hover:bg-stone-700 rounded-lg text-white text-sm font-medium disabled:opacity-50">
                            {saving ? "Attaching…" : "Attach Skill"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ─── Create / Edit Skill Modal ────────────────────────────────────────────────

const EMPTY_FORM = {
    name: "", description: "", version: "1.0.0", category: "general",
    prompt_fragment: "", required_tool_ids: [] as string[], icon: "", color: "#6366f1",
};

const ALL_TOOL_IDS = [
    "create_task", "list_tasks", "update_task", "get_task",
    "start_discussion", "ask_agent", "control_agent", "request_approval",
    "save_memory", "search_memory",
    "create_agent_from_template", "list_agent_templates", "archive_agent",
    "read_file", "write_file", "list_directory", "search_files",
    "run_shell_command", "get_system_info", "list_processes",
    "create_github_issue", "create_github_pr", "commit_and_push",
    "search_knowledge_base", "ingest_url_to_kb", "scrape_webpage",
    "analyze_data", "append_to_google_sheet",
    "send_email", "read_emails", "call_webhook",
];

function SkillFormModal({ skill, onClose, onSaved }: { skill: Skill | null; onClose: () => void; onSaved: () => void }) {
    const [form, setForm] = useState(skill ? {
        name: skill.name, description: skill.description || "", version: skill.version,
        category: skill.category, prompt_fragment: skill.prompt_fragment,
        required_tool_ids: skill.required_tool_ids, icon: skill.icon || "", color: skill.color || "#6366f1",
    } : { ...EMPTY_FORM });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    const toggleTool = (id: string) => setForm(f => ({
        ...f, required_tool_ids: f.required_tool_ids.includes(id) ? f.required_tool_ids.filter(t => t !== id) : [...f.required_tool_ids, id],
    }));

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault(); setSaving(true); setError("");
        try {
            if (skill) { await skillsApi.update(skill.id, form); } else { await skillsApi.create(form); }
            onSaved(); onClose();
        } catch (err: any) { setError(err.message || "Failed to save skill"); }
        finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
                <div className="p-5 border-b border-stone-100 flex items-center justify-between flex-shrink-0">
                    <h2 className="text-base font-semibold text-stone-900">{skill ? "Edit Skill" : "Create Custom Skill"}</h2>
                    <button onClick={onClose} className="p-2 hover:bg-stone-100 rounded-lg text-stone-400"><X className="w-4 h-4" /></button>
                </div>

                {error && (
                    <div className="mx-5 mt-4 flex items-center gap-2 text-red-600 text-sm bg-red-50 rounded-lg p-3">
                        <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-5 space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="col-span-2">
                            <label className="block text-sm font-medium text-stone-700 mb-1">Name *</label>
                            <input required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                placeholder="e.g. Code Review" />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">Category</label>
                            <select value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600">
                                {Object.entries(CATEGORY_LABELS).filter(([k]) => k !== "all").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">Version</label>
                            <input value={form.version} onChange={e => setForm(f => ({ ...f, version: e.target.value }))}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" placeholder="1.0.0" />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">Icon (Lucide name)</label>
                            <input value={form.icon} onChange={e => setForm(f => ({ ...f, icon: e.target.value }))}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" placeholder="e.g. Code2" />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">Color</label>
                            <div className="flex gap-2">
                                <input type="color" value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
                                    className="w-10 h-9 rounded border border-stone-200 cursor-pointer bg-transparent" />
                                <input value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
                                    className="flex-1 border border-stone-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-stone-600" />
                            </div>
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">Description</label>
                        <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            placeholder="What does this skill enable?" />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">Prompt Fragment *</label>
                        <p className="text-xs text-stone-400 mb-2">Appended to the agent's system prompt. Use {"{param}"} for config placeholders.</p>
                        <textarea required value={form.prompt_fragment} onChange={e => setForm(f => ({ ...f, prompt_fragment: e.target.value }))}
                            rows={8} className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-stone-600 resize-y"
                            placeholder={"## Skill Name\nYou have been equipped with..."} />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-2">Required Tools</label>
                        <div className="flex flex-wrap gap-1.5">
                            {ALL_TOOL_IDS.map(id => (
                                <button key={id} type="button" onClick={() => toggleTool(id)}
                                    className={`px-2 py-1 rounded text-xs border transition-colors ${
                                        form.required_tool_ids.includes(id)
                                            ? "bg-stone-100 border-stone-400 text-stone-700"
                                            : "bg-stone-50 border-stone-200 text-stone-500 hover:border-stone-300"
                                    }`}>
                                    {id}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="flex gap-3 pt-2 border-t border-stone-100">
                        <button type="button" onClick={onClose} className="flex-1 px-4 py-2 border border-stone-200 rounded-lg text-stone-600 text-sm hover:bg-stone-50">Cancel</button>
                        <button type="submit" disabled={saving} className="flex-1 px-4 py-2 bg-stone-700 hover:bg-stone-700 rounded-lg text-white text-sm font-medium disabled:opacity-50">
                            {saving ? "Saving…" : skill ? "Update Skill" : "Create Skill"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ─── Skill Card ───────────────────────────────────────────────────────────────

function SkillCard({ skill, onAttach, onEdit, onDelete }: {
    skill: Skill;
    onAttach: () => void;
    onEdit: () => void;
    onDelete: () => void;
}) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="bg-white border border-stone-200 rounded-xl hover:shadow-md transition-shadow overflow-hidden">
            <div className="p-5">
                <div className="flex items-start gap-3">
                    <SkillIcon icon={skill.icon} color={skill.color} />
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="font-semibold text-stone-900 text-sm">{skill.name}</h3>
                            {skill.source === "builtin" && (
                                <span className="text-[10px] font-medium bg-stone-100 text-stone-700 border border-stone-300 px-1.5 py-0.5 rounded-full">Built-in</span>
                            )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-stone-500 capitalize">{skill.category}</span>
                            <span className="text-stone-300">·</span>
                            <span className="text-xs text-stone-400">v{skill.version}</span>
                        </div>
                    </div>
                </div>

                {skill.description && (
                    <p className="text-xs text-stone-600 mt-3 line-clamp-2 leading-relaxed">{skill.description}</p>
                )}

                {skill.required_tool_ids.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                        {skill.required_tool_ids.slice(0, 4).map(t => (
                            <span key={t} className="text-[10px] bg-stone-100 text-stone-500 px-1.5 py-0.5 rounded font-mono">{t}</span>
                        ))}
                        {skill.required_tool_ids.length > 4 && (
                            <span className="text-[10px] bg-stone-100 text-stone-400 px-1.5 py-0.5 rounded">+{skill.required_tool_ids.length - 4} more</span>
                        )}
                    </div>
                )}

                {expanded && (
                    <div className="mt-3 pt-3 border-t border-stone-100">
                        <p className="text-xs font-medium text-stone-500 mb-1.5">Prompt Fragment</p>
                        <pre className="text-[10px] text-stone-600 font-mono whitespace-pre-wrap leading-relaxed bg-stone-50 rounded-lg p-3 max-h-48 overflow-y-auto">
                            {skill.prompt_fragment}
                        </pre>
                    </div>
                )}

                <div className="flex items-center gap-2 mt-4">
                    <button onClick={onAttach}
                        className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-stone-700 text-white rounded-lg text-xs font-medium hover:bg-stone-700 transition-colors">
                        <Sparkles className="w-3.5 h-3.5" /> Attach to Agent
                    </button>
                    <button onClick={() => setExpanded(e => !e)}
                        className="px-2 py-1.5 border border-stone-200 rounded-lg text-stone-500 hover:bg-stone-50 text-xs"
                        title={expanded ? "Hide prompt" : "View prompt"}>
                        {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                    {skill.source === "custom" && (
                        <>
                            <button onClick={onEdit} className="px-2 py-1.5 border border-stone-200 rounded-lg text-stone-500 hover:bg-stone-50">
                                <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={onDelete} className="px-2 py-1.5 border border-red-200 rounded-lg text-red-400 hover:bg-red-50">
                                <Trash2 className="w-3.5 h-3.5" />
                            </button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SkillsPage() {
    const [skills, setSkills] = useState<Skill[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [category, setCategory] = useState("all");
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [attachTarget, setAttachTarget] = useState<Skill | null>(null);
    const [editTarget, setEditTarget] = useState<Skill | null | "new">(null);
    const [successMsg, setSuccessMsg] = useState("");
    const [reseeding, setReseeding] = useState(false);
    const importRef = useRef<HTMLInputElement>(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const params: Record<string, string> = {};
            if (category !== "all") params.category = category;
            if (search) params.search = search;
            setSkills(await skillsApi.list(params));
        } catch {}
        setLoading(false);
    }, [category, search]);

    useEffect(() => { load(); }, [load]);

    const notify = (msg: string) => { setSuccessMsg(msg); setTimeout(() => setSuccessMsg(""), 4000); };

    const handleDelete = async (skill: Skill) => {
        if (!confirm(`Delete "${skill.name}"? This will detach it from all agents.`)) return;
        try { await skillsApi.delete(skill.id); notify(`"${skill.name}" deleted.`); load(); }
        catch (err: any) { notify(err.message || "Delete failed"); }
    };

    const handleExport = async () => {
        if (selected.size === 0) { notify("Select at least one skill to export"); return; }
        try {
            const bundle = await skillsApi.exportBundle(Array.from(selected));
            const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a"); a.href = url; a.download = "skills-export.json"; a.click();
            URL.revokeObjectURL(url);
        } catch { notify("Export failed"); }
    };

    const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]; if (!file) return;
        try {
            const result = await skillsApi.importBundle(file);
            notify(`Imported ${result.created.length} skills, skipped ${result.skipped.length} duplicates.`);
            load();
        } catch { notify("Import failed — check file format"); }
        e.target.value = "";
    };

    const handleReseed = async () => {
        if (!confirm("Re-sync all built-in skills with the latest defaults?")) return;
        setReseeding(true);
        try {
            const r = await skillsApi.reseed();
            notify(`Reseeded: ${r.created.length} created, ${r.updated.length} updated.`);
            load();
        } catch { notify("Reseed failed"); }
        finally { setReseeding(false); }
    };

    const builtinCount = skills.filter(s => s.source === "builtin").length;
    const customCount = skills.filter(s => s.source === "custom").length;

    return (
        <div className="flex-1 flex flex-col min-h-0 overflow-auto bg-[#F8F9FA]">
            {/* Header */}
            <div className="bg-white border-b border-stone-200 px-6 py-4">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-xl font-bold text-stone-900 flex items-center gap-2">
                            <Sparkles className="w-5 h-5 text-stone-700" /> Skills
                        </h1>
                        <p className="text-sm text-stone-500 mt-0.5">
                            {loading ? "Loading…" : `${builtinCount} built-in · ${customCount} custom · Attach capabilities to agents`}
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        {selected.size > 0 && (
                            <button onClick={handleExport}
                                className="flex items-center gap-1.5 px-3 py-2 border border-stone-200 text-stone-600 rounded-xl text-sm font-medium hover:bg-stone-50">
                                <Download className="w-4 h-4" /> Export ({selected.size})
                            </button>
                        )}
                        <button onClick={() => importRef.current?.click()}
                            className="flex items-center gap-1.5 px-3 py-2 border border-stone-200 text-stone-600 rounded-xl text-sm font-medium hover:bg-stone-50">
                            <Upload className="w-4 h-4" /> Import
                        </button>
                        <button onClick={handleReseed} disabled={reseeding}
                            title="Re-sync built-in skills with latest defaults"
                            className="flex items-center gap-1.5 px-3 py-2 border border-stone-200 text-stone-600 rounded-xl text-sm font-medium hover:bg-stone-50 disabled:opacity-50">
                            <RefreshCw className={`w-4 h-4 ${reseeding ? "animate-spin" : ""}`} /> Reseed
                        </button>
                        <button onClick={() => setEditTarget("new")}
                            className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white rounded-xl text-sm font-medium hover:bg-stone-700 transition-colors">
                            <Plus className="w-4 h-4" /> New Skill
                        </button>
                        <input ref={importRef} type="file" accept=".json" className="hidden" onChange={handleImport} />
                    </div>
                </div>

                {/* Search + category filter */}
                <div className="flex items-center gap-3 mt-4">
                    <div className="relative flex-1 max-w-xs">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
                        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search skills…"
                            className="w-full pl-9 pr-3 py-2 border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 bg-stone-50" />
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                        {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                            <button key={k} onClick={() => setCategory(k)}
                                className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${
                                    category === k ? "bg-stone-700 text-white" : "bg-white border border-stone-200 text-stone-600 hover:bg-stone-50"
                                }`}>
                                {v}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Success Banner */}
            {successMsg && (
                <div className="mx-6 mt-4 flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl px-4 py-3 text-sm text-green-700">
                    <CheckCircle className="w-4 h-4 flex-shrink-0" /> {successMsg}
                </div>
            )}

            {/* Skill grid */}
            <div className="flex-1 p-6">
                {loading ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {Array.from({ length: 8 }).map((_, i) => (
                            <div key={i} className="bg-white border border-stone-200 rounded-xl p-5 animate-pulse">
                                <div className="flex items-start gap-3">
                                    <div className="w-10 h-10 bg-stone-100 rounded-xl" />
                                    <div className="flex-1 space-y-2">
                                        <div className="h-4 bg-stone-100 rounded w-3/4" />
                                        <div className="h-3 bg-stone-100 rounded w-1/3" />
                                    </div>
                                </div>
                                <div className="h-3 bg-stone-100 rounded mt-4 w-full" />
                                <div className="h-3 bg-stone-100 rounded mt-2 w-2/3" />
                            </div>
                        ))}
                    </div>
                ) : skills.length === 0 ? (
                    <div className="text-center py-20">
                        <Sparkles className="w-10 h-10 text-stone-300 mx-auto mb-3" />
                        <p className="text-stone-500 font-medium">No skills found</p>
                        <p className="text-stone-400 text-sm mt-1">
                            {search || category !== "all" ? "Try adjusting your filters" : "Click \"Reseed\" to load built-in skills, or create a custom one"}
                        </p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {skills.map(skill => (
                            <SkillCard
                                key={skill.id}
                                skill={skill}
                                onAttach={() => setAttachTarget(skill)}
                                onEdit={() => setEditTarget(skill)}
                                onDelete={() => handleDelete(skill)}
                            />
                        ))}
                    </div>
                )}
            </div>

            {/* Modals */}
            {attachTarget && (
                <AttachSkillModal skill={attachTarget} onClose={() => setAttachTarget(null)}
                    onDone={() => notify(`Skill attached successfully`)} />
            )}
            {editTarget !== null && (
                <SkillFormModal skill={editTarget === "new" ? null : editTarget} onClose={() => setEditTarget(null)}
                    onSaved={() => { load(); notify("Skill saved"); }} />
            )}
        </div>
    );
}
