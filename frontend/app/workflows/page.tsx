"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Plus, Trash2, Play, Settings, LayoutGrid, List, GitMerge, Download, Upload, FileCode2, FileText } from "lucide-react";
import { workflowsApi, type WorkflowSummary as Workflow } from "@/lib/api";

type ViewMode = "grid" | "list";

export default function WorkflowsPage() {
    const [workflows, setWorkflows] = useState<Workflow[]>([]);
    const [loading, setLoading] = useState(true);
    const [view, setView] = useState<ViewMode>("list");
    const [importOpen, setImportOpen] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        loadWorkflows();
    }, []);

    async function loadWorkflows() {
        try {
            setWorkflows(await workflowsApi.list());
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }

    async function handleDelete(id: string) {
        if (!confirm("Are you sure?")) return;
        try {
            await workflowsApi.delete(id);
            setWorkflows(workflows.filter((w) => w.id !== id));
        } catch (err) {
            console.error(err);
        }
    }

    async function handleRun(id: string) {
        try {
            await workflowsApi.execute(id);
            alert("Workflow execution started!");
        } catch (err) {
            console.error(err);
            alert("Error executing workflow.");
        }
    }

    async function createWorkflow() {
        try {
            const wf = await workflowsApi.create({ name: "New Workflow", definition: { nodes: [], edges: [] } });
            window.location.href = `/workflows/${wf.id}`;
        } catch (err) {
            console.error(err);
        }
    }

    function handleExport(id: string, format: "json" | "markdown") {
        window.open(workflowsApi.exportUrl(id, format), "_blank");
    }

    async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
        const file = e.target.files?.[0];
        if (!file) return;
        const content = await file.text();
        const format = file.name.endsWith(".md") ? "markdown" : "json";
        try {
            const wf = await workflowsApi.import(content, format);
            setWorkflows((prev) => [wf, ...prev]);
            window.location.href = `/workflows/${wf.id}`;
        } catch (err: any) {
            alert("Import failed: " + (err?.message ?? "Unknown error"));
        } finally {
            e.target.value = "";
        }
    }

    async function handleImportText(content: string, format: "json" | "markdown") {
        try {
            const wf = await workflowsApi.import(content, format);
            setWorkflows((prev) => [wf, ...prev]);
            setImportOpen(false);
            window.location.href = `/workflows/${wf.id}`;
        } catch (err: any) {
            alert("Import failed: " + (err?.message ?? "Unknown error"));
        }
    }

    // ─── Render ─────────────────────────────────────────────────────────────

    if (loading) {
        return <div className="flex h-full items-center justify-center text-stone-500">Loading Workflows...</div>;
    }

    return (
        <div className="flex flex-col h-[calc(100vh-4rem)] animate-fade-in">
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-stone-900">Workflows</h1>
                    <p className="text-stone-500 mt-1">Design and schedule visual AI agent chains.</p>
                </div>
                <div className="flex items-center gap-3">
                    {/* View toggle */}
                    <div className="flex items-center bg-stone-100 rounded-lg p-0.5">
                        <button
                            onClick={() => setView("grid")}
                            className={`p-1.5 rounded-md transition-colors ${view === "grid" ? "bg-white shadow-sm text-stone-800" : "text-stone-400 hover:text-stone-600"}`}
                            title="Grid view"
                        >
                            <LayoutGrid size={16} />
                        </button>
                        <button
                            onClick={() => setView("list")}
                            className={`p-1.5 rounded-md transition-colors ${view === "list" ? "bg-white shadow-sm text-stone-800" : "text-stone-400 hover:text-stone-600"}`}
                            title="List view"
                        >
                            <List size={16} />
                        </button>
                    </div>
                    {/* Import */}
                    <input ref={fileInputRef} type="file" accept=".json,.md" className="hidden" onChange={handleImportFile} />
                    <button
                        onClick={() => setImportOpen(true)}
                        className="flex items-center gap-2 px-4 py-2 bg-white border border-stone-200 hover:bg-stone-50 text-stone-700 rounded-lg transition-colors font-medium shadow-sm"
                        title="Import workflow from JSON or Markdown"
                    >
                        <Upload size={16} />
                        Import
                    </button>
                    <button
                        onClick={createWorkflow}
                        className="flex items-center gap-2 px-4 py-2 bg-stone-800 hover:bg-stone-700 text-white rounded-lg transition-colors font-medium shadow-sm"
                    >
                        <Plus size={18} />
                        New Workflow
                    </button>
                </div>
            </div>

            {workflows.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-stone-200 rounded-xl bg-stone-50/50">
                    <Settings size={48} className="text-stone-300 mb-4" />
                    <h2 className="text-xl font-semibold text-stone-800 mb-2">No workflows yet</h2>
                    <p className="text-stone-500 mb-6 max-w-sm text-center">
                        Create a workflow to chain agents together and run them on a schedule.
                    </p>
                    <button
                        onClick={createWorkflow}
                        className="flex items-center gap-2 px-4 py-2 bg-white border border-stone-200 text-stone-700 hover:bg-stone-50 rounded-lg transition-colors font-medium shadow-sm"
                    >
                        <Plus size={18} />
                        Create Your First Workflow
                    </button>
                </div>
            ) : view === "grid" ? (
                /* ─── Grid View ─────────────────────────────────────────── */
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {workflows.map((wf) => (
                        <div
                            key={wf.id}
                            className={`group flex flex-col bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm transition-all duration-300 hover:shadow-md hover:border-stone-300 hover:-translate-y-0.5 ${!wf.is_active && "opacity-60 grayscale-[0.5]"}`}
                        >
                            <div className="p-5 flex-1">
                                <div className="flex justify-between items-start mb-3">
                                    <h3 className="text-lg font-bold text-stone-900 group-hover:text-stone-700 transition-colors">
                                        {wf.name}
                                    </h3>
                                    <StatusBadge active={wf.is_active} />
                                </div>
                                <p className="text-stone-500 text-sm line-clamp-2 min-h-[2.5rem] mb-4">
                                    {wf.description || "No description provided."}
                                </p>
                                <div className="flex items-center gap-2 text-xs font-semibold text-stone-400">
                                    <Settings size={14} className="text-stone-300" />
                                    <span>
                                        Schedule: {wf.schedule_interval ? `Every ${wf.schedule_interval}m` : "Manual"}
                                    </span>
                                </div>
                            </div>

                            <div className="bg-stone-50/50 p-3 mt-auto border-t border-stone-100 flex items-center justify-between">
                                <Link
                                    href={`/workflows/${wf.id}`}
                                    className="px-4 py-1.5 bg-white border border-stone-200 hover:bg-stone-50 text-stone-700 text-sm font-bold rounded-lg transition-all shadow-sm flex-1 text-center mr-2"
                                >
                                    Edit Canvas
                                </Link>
                                <div className="flex items-center gap-1">
                                    <button
                                        onClick={() => handleRun(wf.id)}
                                        className="p-2 text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg transition-colors"
                                        title="Run Workflow"
                                    >
                                        <Play size={16} className="fill-current" />
                                    </button>
                                    <button
                                        onClick={() => handleExport(wf.id, "markdown")}
                                        className="p-2 text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg transition-colors"
                                        title="Export as Markdown"
                                    >
                                        <FileText size={16} />
                                    </button>
                                    <button
                                        onClick={() => handleExport(wf.id, "json")}
                                        className="p-2 text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg transition-colors"
                                        title="Export as JSON"
                                    >
                                        <FileCode2 size={16} />
                                    </button>
                                    <button
                                        onClick={() => handleDelete(wf.id)}
                                        className="p-2 text-stone-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                                        title="Delete Workflow"
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                /* ─── List View ─────────────────────────────────────────── */
                <div className="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
                    {/* Table header */}
                    <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 items-center px-5 py-3 border-b border-stone-100 bg-stone-50/60 text-xs font-semibold text-stone-400 uppercase tracking-wider">
                        <span>Workflow</span>
                        <span className="w-20 text-center">Status</span>
                        <span className="w-28 text-center">Schedule</span>
                        <span className="w-24 text-center">Canvas</span>
                        <span className="w-28 text-center">Actions</span>
                    </div>

                    {workflows.map((wf, i) => (
                        <div
                            key={wf.id}
                            className={`grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 items-center px-5 py-3.5 transition-colors hover:bg-stone-50/60 ${i < workflows.length - 1 ? "border-b border-stone-100" : ""} ${!wf.is_active ? "opacity-60" : ""}`}
                        >
                            {/* Name + description */}
                            <div className="flex items-center gap-3 min-w-0">
                                <div className="w-8 h-8 rounded-lg bg-stone-100 flex items-center justify-center flex-shrink-0">
                                    <GitMerge size={14} className="text-stone-500" />
                                </div>
                                <div className="min-w-0">
                                    <p className="text-sm font-semibold text-stone-800 truncate">{wf.name}</p>
                                    <p className="text-xs text-stone-400 truncate">{wf.description || "No description"}</p>
                                </div>
                            </div>

                            {/* Status */}
                            <div className="w-20 flex justify-center">
                                <StatusBadge active={wf.is_active} />
                            </div>

                            {/* Schedule */}
                            <div className="w-28 text-center">
                                <span className="text-xs text-stone-500">
                                    {wf.schedule_interval ? `Every ${wf.schedule_interval}m` : "Manual"}
                                </span>
                            </div>

                            {/* Edit canvas */}
                            <div className="w-24 flex justify-center">
                                <Link
                                    href={`/workflows/${wf.id}`}
                                    className="px-3 py-1 bg-white border border-stone-200 hover:bg-stone-50 text-stone-600 text-xs font-semibold rounded-lg transition-colors shadow-sm"
                                >
                                    Edit
                                </Link>
                            </div>

                            {/* Actions */}
                            <div className="w-28 flex justify-center gap-1">
                                <button
                                    onClick={() => handleRun(wf.id)}
                                    className="p-1.5 text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg transition-colors"
                                    title="Run Workflow"
                                >
                                    <Play size={14} className="fill-current" />
                                </button>
                                <button
                                    onClick={() => handleExport(wf.id, "markdown")}
                                    className="p-1.5 text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg transition-colors"
                                    title="Export as Markdown"
                                >
                                    <FileText size={14} />
                                </button>
                                <button
                                    onClick={() => handleExport(wf.id, "json")}
                                    className="p-1.5 text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg transition-colors"
                                    title="Export as JSON"
                                >
                                    <FileCode2 size={14} />
                                </button>
                                <button
                                    onClick={() => handleDelete(wf.id)}
                                    className="p-1.5 text-stone-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                                    title="Delete Workflow"
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* ─── Import Modal ─────────────────────────────────────────── */}
            {importOpen && <ImportModal onClose={() => setImportOpen(false)} onImport={handleImportText} onFile={() => fileInputRef.current?.click()} />}
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Status Badge                                                             */
/* ────────────────────────────────────────────────────────────────────────── */

function StatusBadge({ active }: { active: boolean }) {
    return active ? (
        <span className="px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full bg-emerald-50 text-emerald-600 border border-emerald-100">
            Active
        </span>
    ) : (
        <span className="px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full bg-stone-100 text-stone-500 border border-stone-200">
            Inactive
        </span>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Import Modal                                                             */
/* ────────────────────────────────────────────────────────────────────────── */

function ImportModal({
    onClose,
    onImport,
    onFile,
}: {
    onClose: () => void;
    onImport: (content: string, format: "json" | "markdown") => void;
    onFile: () => void;
}) {
    const [tab, setTab] = useState<"paste" | "file">("paste");
    const [content, setContent] = useState("");
    const [format, setFormat] = useState<"markdown" | "json">("markdown");

    const PLACEHOLDER_MD = `# Workflow: My AI Pipeline

A brief description of what this workflow does.

**Schedule:** Every 60 minutes
**Active:** true

## Nodes

### 1. [input] Start
- id: input-001
- value: Analyze latest AI trends

### 2. [agent] Researcher
- id: agent-001
- agent_id: <your-agent-id>
- prompt: Research the following topic thoroughly: {input}
- max_retries: 2

### 3. [agent] Writer
- id: agent-002
- agent_id: <your-agent-id>
- prompt: Write a concise summary based on: {input}
- max_retries: 0

## Edges

Start --> Researcher
Researcher --> Writer`;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-fade-in">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 overflow-hidden">
                <div className="flex items-center justify-between px-6 py-4 border-b border-stone-100">
                    <div className="flex items-center gap-2">
                        <Upload size={18} className="text-stone-500" />
                        <h2 className="text-lg font-bold text-stone-900">Import Workflow</h2>
                    </div>
                    <button onClick={onClose} className="text-stone-400 hover:text-stone-600 text-xl leading-none">×</button>
                </div>

                <div className="p-6 space-y-4">
                    {/* Tabs */}
                    <div className="flex gap-1 bg-stone-100 rounded-lg p-0.5 w-fit">
                        <button
                            onClick={() => setTab("paste")}
                            className={`px-4 py-1.5 text-sm font-medium rounded-md transition-colors ${tab === "paste" ? "bg-white text-stone-800 shadow-sm" : "text-stone-500 hover:text-stone-700"}`}
                        >
                            Paste Text
                        </button>
                        <button
                            onClick={() => { onFile(); onClose(); }}
                            className="px-4 py-1.5 text-sm font-medium rounded-md text-stone-500 hover:text-stone-700 transition-colors"
                        >
                            Upload File (.json / .md)
                        </button>
                    </div>

                    {/* Format selector */}
                    <div className="flex items-center gap-3 text-sm">
                        <span className="text-stone-500 font-medium">Format:</span>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="radio" name="fmt" value="markdown" checked={format === "markdown"} onChange={() => setFormat("markdown")} className="accent-stone-700" />
                            <span className="text-stone-700">Markdown (Claude-generated)</span>
                        </label>
                        <label className="flex items-center gap-1.5 cursor-pointer">
                            <input type="radio" name="fmt" value="json" checked={format === "json"} onChange={() => setFormat("json")} className="accent-stone-700" />
                            <span className="text-stone-700">JSON (exported)</span>
                        </label>
                    </div>

                    {/* Textarea */}
                    <textarea
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                        placeholder={format === "markdown" ? PLACEHOLDER_MD : '{\n  "sutra_export": "workflow",\n  "version": 1,\n  ...\n}'}
                        rows={14}
                        className="w-full font-mono text-xs bg-stone-50 border border-stone-200 rounded-xl p-4 resize-none focus:outline-none focus:ring-2 focus:ring-stone-300 text-stone-800"
                    />

                    <p className="text-xs text-stone-400">
                        <strong>Tip:</strong> Ask Claude to design a workflow as Markdown using the format above, then paste it here. Use your actual agent IDs in the <code>agent_id</code> fields.
                    </p>
                </div>

                <div className="flex justify-end gap-3 px-6 py-4 border-t border-stone-100 bg-stone-50/50">
                    <button onClick={onClose} className="px-4 py-2 text-stone-600 hover:text-stone-800 text-sm font-medium transition-colors">
                        Cancel
                    </button>
                    <button
                        onClick={() => content.trim() && onImport(content, format)}
                        disabled={!content.trim()}
                        className="px-5 py-2 bg-stone-800 hover:bg-stone-700 disabled:opacity-40 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
                    >
                        Import Workflow
                    </button>
                </div>
            </div>
        </div>
    );
}
