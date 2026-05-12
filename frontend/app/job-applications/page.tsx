"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
    Briefcase,
    Building2,
    MapPin,
    ExternalLink,
    Search,
    RefreshCw,
    Play,
    RotateCcw,
    LayoutGrid,
    List as ListIcon,
    Trash2,
    X,
    FileText,
    Target,
    TrendingUp,
    Calendar,
    Save,
    Users,
    UserCircle,
    BookOpen,
    Pencil,
} from "lucide-react";
import {
    jobApplicationsApi,
    JOB_APP_STATUSES,
    envVarsApi,
    googleDriveApi,
    type JobApplication,
    type JobApplicationReviewEntry,
    type JobApplicationStats,
    type JobAppStatus,
} from "@/lib/api";
import DiscoveryTab from "./components/DiscoveryTab";

// ─── Status config ─────────────────────────────────────────────────────────────

const STATUS_META: Record<JobAppStatus, { label: string; color: string; ring: string; dot: string }> = {
    captured: {
        label: "Captured",
        color: "bg-stone-100 text-stone-600 border-stone-200",
        ring: "ring-stone-300",
        dot: "bg-stone-400",
    },
    resume_generated: {
        label: "Resume Ready",
        color: "bg-blue-50 text-blue-700 border-blue-200",
        ring: "ring-blue-200",
        dot: "bg-blue-500",
    },
    applied: {
        label: "Applied",
        color: "bg-indigo-50 text-indigo-700 border-indigo-200",
        ring: "ring-indigo-200",
        dot: "bg-indigo-500",
    },
    interviewing: {
        label: "Interviewing",
        color: "bg-amber-50 text-amber-700 border-amber-200",
        ring: "ring-amber-200",
        dot: "bg-amber-500",
    },
    offer: {
        label: "Offer",
        color: "bg-emerald-50 text-emerald-700 border-emerald-200",
        ring: "ring-emerald-200",
        dot: "bg-emerald-500",
    },
    rejected: {
        label: "Rejected",
        color: "bg-rose-50 text-rose-700 border-rose-200",
        ring: "ring-rose-200",
        dot: "bg-rose-500",
    },
    archived: {
        label: "Archived",
        color: "bg-stone-100 text-stone-500 border-stone-200",
        ring: "ring-stone-200",
        dot: "bg-stone-400",
    },
};

function timeAgo(iso: string | null): string {
    if (!iso) return "—";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
}

// ─── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
    label,
    value,
    icon: Icon,
    subtitle,
    accent,
}: {
    label: string;
    value: number | string;
    icon: any;
    subtitle?: string;
    accent: string;
}) {
    return (
        <div className="relative bg-white border border-stone-200 rounded-xl p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-2">
                <div className={`p-1.5 rounded-lg ${accent}`}>
                    <Icon className="w-3.5 h-3.5" />
                </div>
                <span className="text-[11px] font-medium text-stone-500 uppercase tracking-wider">
                    {label}
                </span>
            </div>
            <div className="text-2xl font-bold text-stone-900">{value}</div>
            {subtitle && <p className="text-[11px] text-stone-500 mt-1">{subtitle}</p>}
        </div>
    );
}

// ─── Status pill ───────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: JobAppStatus }) {
    const meta = STATUS_META[status];
    return (
        <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-medium border ${meta.color}`}
        >
            <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
            {meta.label}
        </span>
    );
}

function StatusSelect({
    value,
    onChange,
}: {
    value: JobAppStatus;
    onChange: (s: JobAppStatus) => void;
}) {
    return (
        <select
            value={value}
            onChange={(e) => onChange(e.target.value as JobAppStatus)}
            className="bg-white border border-stone-200 text-stone-800 text-xs rounded-md px-2 py-1 focus:border-indigo-500 focus:outline-none"
            onClick={(e) => e.stopPropagation()}
        >
            {JOB_APP_STATUSES.map((s) => (
                <option key={s} value={s}>
                    {STATUS_META[s].label}
                </option>
            ))}
        </select>
    );
}

// ─── Kanban ────────────────────────────────────────────────────────────────────

function Kanban({
    applications,
    onStatusChange,
    onOpen,
}: {
    applications: JobApplication[];
    onStatusChange: (id: string, s: JobAppStatus) => void;
    onOpen: (app: JobApplication) => void;
}) {
    const cols = JOB_APP_STATUSES.filter((s) => s !== "archived");
    const grouped: Record<string, JobApplication[]> = {};
    cols.forEach((c) => (grouped[c] = []));
    applications.forEach((a) => {
        if (a.status in grouped) grouped[a.status].push(a);
    });

    const onDragStart = (e: React.DragEvent, id: string) => {
        e.dataTransfer.setData("text/plain", id);
    };
    const onDragOver = (e: React.DragEvent) => e.preventDefault();
    const onDrop = (e: React.DragEvent, status: JobAppStatus) => {
        e.preventDefault();
        const id = e.dataTransfer.getData("text/plain");
        if (id) onStatusChange(id, status);
    };

    return (
        <div className="grid grid-cols-6 gap-3 overflow-x-auto">
            {cols.map((s) => (
                <div
                    key={s}
                    onDragOver={onDragOver}
                    onDrop={(e) => onDrop(e, s as JobAppStatus)}
                    className="bg-stone-50 border border-stone-200 rounded-xl p-3 min-w-[220px]"
                >
                    <div className="flex items-center justify-between mb-3">
                        <StatusBadge status={s as JobAppStatus} />
                        <span className="text-xs text-stone-500">{grouped[s].length}</span>
                    </div>
                    <div className="space-y-2">
                        {grouped[s].map((app) => (
                            <div
                                key={app.id}
                                draggable
                                onDragStart={(e) => onDragStart(e, app.id)}
                                onClick={() => onOpen(app)}
                                className="bg-white hover:bg-stone-50 border border-stone-200 hover:border-stone-300 rounded-lg p-2.5 cursor-pointer transition-colors shadow-sm"
                            >
                                <div className="text-xs font-semibold text-stone-900 line-clamp-2">
                                    {app.job_title}
                                </div>
                                <div className="text-[11px] text-stone-500 mt-1 flex items-center gap-1">
                                    <Building2 size={10} />
                                    {app.company || "—"}
                                </div>
                                {app.fit_score != null && (
                                    <div className="mt-2 flex items-center gap-1.5">
                                        <div className="flex-1 h-1 bg-stone-200 rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-gradient-to-r from-indigo-500 to-emerald-500"
                                                style={{ width: `${app.fit_score}%` }}
                                            />
                                        </div>
                                        <span className="text-[10px] text-stone-500">{app.fit_score}</span>
                                    </div>
                                )}
                                <div className="text-[10px] text-stone-400 mt-1.5">
                                    {timeAgo(app.created_at)}
                                </div>
                            </div>
                        ))}
                        {grouped[s].length === 0 && (
                            <div className="text-[11px] text-stone-400 text-center py-6 border border-dashed border-stone-200 rounded-lg">
                                Drop here
                            </div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}

// ─── Review loop panel ─────────────────────────────────────────────────────────

function ReviewLoopPanel({
    app,
    onPatch,
}: {
    app: JobApplication;
    onPatch: (patch: Partial<JobApplication>) => void;
}) {
    const [entries, setEntries] = useState<JobApplicationReviewEntry[]>(app.review_log || []);
    const [streaming, setStreaming] = useState(false);
    const [expanded, setExpanded] = useState<number | null>(null);
    const [retrying, setRetrying] = useState(false);

    const retry = async (reset: boolean) => {
        if (retrying) return;
        if (reset && !confirm("Reset will clear all prior review rounds and generated files. Continue?")) return;
        setRetrying(true);
        try {
            await jobApplicationsApi.retryReview(app.id, reset);
            if (reset) setEntries([]);
            onPatch({ status: "captured" });
        } catch (e) {
            console.error(e);
            alert("Retry failed — check backend logs.");
        } finally {
            setRetrying(false);
        }
    };

    useEffect(() => {
        setEntries(app.review_log || []);
    }, [app.id, app.review_log]);

    useEffect(() => {
        if (app.status !== "captured") return;
        const es = jobApplicationsApi.reviewStream(app.id);
        setStreaming(true);
        es.onmessage = (ev) => {
            try {
                const msg = JSON.parse(ev.data);
                if (msg.type === "log") {
                    setEntries((prev) => [...prev, msg.entry as JobApplicationReviewEntry]);
                } else if (msg.type === "done" || msg.type === "timeout" || msg.type === "error") {
                    es.close();
                    setStreaming(false);
                }
            } catch { /* ignore */ }
        };
        es.onerror = () => {
            es.close();
            setStreaming(false);
        };
        return () => {
            es.close();
            setStreaming(false);
        };
    }, [app.id, app.status]);

    return (
        <div>
            <div className="flex items-center justify-between mb-2">
                <div className="text-xs uppercase tracking-wider text-stone-500 flex items-center gap-1.5">
                    <Target size={12} /> Review Loop
                    {streaming && (
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            live
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2 text-xs text-stone-500">
                    <label htmlFor="rounds">Rounds:</label>
                    <input
                        id="rounds"
                        type="number"
                        min={0}
                        max={5}
                        value={app.review_rounds}
                        onChange={(e) => {
                            const n = Math.max(0, Math.min(5, Number(e.target.value) || 0));
                            onPatch({ review_rounds: n });
                        }}
                        className="w-14 bg-white border border-stone-200 rounded-md px-2 py-1 text-xs text-stone-900 focus:border-indigo-500 focus:outline-none"
                    />
                    <button
                        onClick={() => retry(false)}
                        disabled={retrying || streaming}
                        title="Rerun the review loop, appending new rounds"
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-stone-200 hover:border-indigo-400 hover:text-indigo-600 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        <Play size={11} /> Retry
                    </button>
                    <button
                        onClick={() => retry(true)}
                        disabled={retrying || streaming}
                        title="Clear prior rounds and generated files, then rerun"
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-stone-200 hover:border-amber-400 hover:text-amber-600 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                        <RotateCcw size={11} /> Reset &amp; Retry
                    </button>
                </div>
            </div>

            {entries.length === 0 ? (
                <div className="text-[11px] text-stone-400 border border-dashed border-stone-200 rounded-lg p-4 text-center">
                    No review rounds yet. Builder + Critic will run when a job is captured (set Rounds above 0).
                </div>
            ) : (
                <div className="space-y-2">
                    {entries.map((e, i) => {
                        const isBuilder = e.role === "builder";
                        const isSystem = e.role === "system";
                        const isCritic = e.role === "critic";
                        const isOpen = expanded === i;
                        const label = isBuilder ? "Builder" : isSystem ? "System" : "Critic";
                        const tone = isBuilder
                            ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                            : isSystem
                                ? "bg-rose-50 text-rose-700 border-rose-200"
                                : "bg-amber-50 text-amber-700 border-amber-200";
                        const critic = isCritic && typeof e.content === "object" && e.content
                            ? (e.content as Record<string, unknown>)
                            : null;
                        const systemMsg = isSystem && typeof e.content === "object" && e.content
                            ? ((e.content as Record<string, unknown>).message as string) || ""
                            : "";
                        return (
                            <div
                                key={i}
                                className="bg-white border border-stone-200 rounded-lg shadow-sm"
                            >
                                <button
                                    onClick={() => setExpanded(isOpen ? null : i)}
                                    className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left"
                                >
                                    <div className="flex items-center gap-2 min-w-0">
                                        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${tone}`}>
                                            {label}
                                        </span>
                                        <span className="text-[11px] text-stone-500">
                                            Round {e.round} · {e.agent}
                                        </span>
                                        {critic?.status === "approved" && (
                                            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border bg-emerald-50 text-emerald-700 border-emerald-200">
                                                approved
                                            </span>
                                        )}
                                    </div>
                                    <span className="text-[10px] text-stone-400">
                                        {isOpen ? "hide" : "show"}
                                    </span>
                                </button>
                                {isSystem && systemMsg && (
                                    <div className="px-3 pb-3 text-[11px] text-rose-700 border-t border-rose-100 pt-2">
                                        {systemMsg}
                                    </div>
                                )}
                                {isOpen && !isSystem && (
                                    <div className="px-3 pb-3 border-t border-stone-100">
                                        {critic ? (
                                            <CriticSummary feedback={critic} />
                                        ) : (
                                            <pre className="text-[11px] text-stone-700 whitespace-pre-wrap max-h-96 overflow-y-auto font-mono">
                                                {typeof e.content === "string"
                                                    ? e.content
                                                    : JSON.stringify(e.content, null, 2)}
                                            </pre>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

function CriticSummary({ feedback }: { feedback: Record<string, unknown> }) {
    const section = (title: string, items: unknown) => {
        const arr = Array.isArray(items) ? items : [];
        if (arr.length === 0) return null;
        return (
            <div className="mt-2">
                <div className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">
                    {title}
                </div>
                <ul className="space-y-1">
                    {arr.map((item, i) => (
                        <li key={i} className="text-[11px] text-stone-700">
                            {typeof item === "string"
                                ? item
                                : JSON.stringify(item)}
                        </li>
                    ))}
                </ul>
            </div>
        );
    };
    return (
        <div className="pt-2">
            {typeof feedback.overall_assessment === "string" && (
                <div className="text-xs text-stone-700 italic">
                    {feedback.overall_assessment}
                </div>
            )}
            {section("Priority fixes", feedback.priority_fixes)}
            {section("Fabrication flags", feedback.fabrication_flags)}
            {section("AI-tone flags", feedback.ai_tone_flags)}
            {section("Alignment issues", feedback.alignment_issues)}
            {section("Missing keywords", feedback.missing_keywords)}
            {section("LaTeX issues", feedback.latex_issues)}
        </div>
    );
}

// ─── Master Resume picker ──────────────────────────────────────────────────────

const MASTER_RESUME_ENV_KEY = "MASTER_RESUME_DRIVE_FILE_ID";

interface DriveFileRow {
    id: string;
    name: string;
    mimeType: string;
    modifiedTime: string;
}

function MasterResumePicker() {
    const [fileId, setFileId] = useState<string>("");
    const [fileName, setFileName] = useState<string>("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState("resume");
    const [results, setResults] = useState<DriveFileRow[]>([]);
    const [searching, setSearching] = useState(false);

    const refresh = useCallback(async () => {
        try {
            const items = await envVarsApi.list();
            const row = items.find((i) => i.key === MASTER_RESUME_ENV_KEY);
            const id = row?.is_set ? row.masked_value : "";
            setFileId(id);
            if (id) {
                try {
                    const meta = await googleDriveApi.getFileMetadata(id);
                    setFileName(meta.name);
                } catch {
                    setFileName("(file not found in Drive)");
                }
            } else {
                setFileName("");
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { void refresh(); }, [refresh]);

    const runSearch = useCallback(async (q: string) => {
        setSearching(true);
        try {
            const files = await googleDriveApi.searchFiles(q);
            setResults(files);
        } catch {
            setResults([]);
        } finally {
            setSearching(false);
        }
    }, []);

    useEffect(() => {
        if (!open) return;
        const t = setTimeout(() => { void runSearch(query); }, 250);
        return () => clearTimeout(t);
    }, [open, query, runSearch]);

    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [open]);

    async function pick(file: DriveFileRow) {
        setSaving(true);
        try {
            await envVarsApi.upsert([{ key: MASTER_RESUME_ENV_KEY, value: file.id }]);
            setFileId(file.id);
            setFileName(file.name);
            setOpen(false);
        } catch (e) {
            console.error(e);
            alert("Failed to save master resume id — check backend logs.");
        } finally {
            setSaving(false);
        }
    }

    if (loading) return null;

    const hasFile = !!fileId;

    return (
        <>
            <button
                onClick={() => setOpen(true)}
                disabled={saving}
                title={hasFile
                    ? `Master resume: ${fileName}\nClick to change`
                    : "Pick your master resume from Google Drive — used as ground truth by the Resume Critic"}
                className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm shadow-sm border transition-colors disabled:opacity-50 ${
                    hasFile
                        ? "bg-white border-stone-200 hover:border-indigo-400 text-stone-700"
                        : "bg-amber-50 border-amber-300 hover:border-amber-400 text-amber-800"
                }`}
            >
                <BookOpen size={14} className={hasFile ? "text-indigo-500" : "text-amber-600"} />
                <span className="text-[12px] uppercase tracking-wider text-stone-500">Master:</span>
                <span className="max-w-[200px] truncate font-medium">
                    {hasFile ? (fileName || fileId) : "Set master resume…"}
                </span>
                <Pencil size={12} className="text-stone-400" />
            </button>

            {open && (
                <div
                    className="fixed inset-0 z-50 bg-stone-900/40 flex items-start justify-center p-8"
                    onClick={() => setOpen(false)}
                >
                    <div
                        className="bg-white rounded-xl shadow-xl border border-stone-200 w-full max-w-xl max-h-[80vh] flex flex-col"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between px-4 py-3 border-b border-stone-200">
                            <div className="flex items-center gap-2 text-stone-800">
                                <BookOpen size={16} className="text-indigo-500" />
                                <span className="font-medium text-sm">Select your master resume</span>
                            </div>
                            <button
                                onClick={() => setOpen(false)}
                                className="p-1 rounded-md hover:bg-stone-100 text-stone-500"
                                aria-label="Close"
                            >
                                <X size={16} />
                            </button>
                        </div>

                        <div className="px-4 py-3 border-b border-stone-100">
                            <div className="relative">
                                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                                <input
                                    autoFocus
                                    type="text"
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    placeholder="Search your Google Drive…"
                                    className="w-full bg-white border border-stone-200 rounded-lg pl-9 pr-3 py-2 text-sm placeholder-stone-400 focus:border-indigo-500 focus:outline-none"
                                />
                            </div>
                            <p className="text-[11px] text-stone-500 mt-2">
                                Pick the document the Resume Critic should treat as ground truth (Google Doc, .md, or .txt).
                            </p>
                        </div>

                        <div className="flex-1 overflow-y-auto px-2 py-2">
                            {searching && (
                                <div className="text-[11px] text-stone-500 text-center py-4">Searching…</div>
                            )}
                            {!searching && results.length === 0 && (
                                <div className="text-[11px] text-stone-400 text-center py-6">
                                    No matching files. Try a different search term.
                                </div>
                            )}
                            {results.map((f) => {
                                const isSelected = f.id === fileId;
                                return (
                                    <button
                                        key={f.id}
                                        onClick={() => pick(f)}
                                        disabled={saving}
                                        className={`w-full text-left px-3 py-2 rounded-lg flex items-start gap-2 transition-colors ${
                                            isSelected
                                                ? "bg-indigo-50 border border-indigo-200"
                                                : "hover:bg-stone-50 border border-transparent"
                                        }`}
                                    >
                                        <FileText size={14} className="text-stone-400 mt-0.5 shrink-0" />
                                        <div className="min-w-0 flex-1">
                                            <div className="text-sm text-stone-800 truncate">{f.name}</div>
                                            <div className="text-[11px] text-stone-500">
                                                {f.mimeType.split(".").pop()} · {timeAgo(f.modifiedTime)}
                                            </div>
                                        </div>
                                        {isSelected && (
                                            <span className="text-[10px] text-indigo-600 self-center">current</span>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}

// ─── Details drawer ────────────────────────────────────────────────────────────

function Drawer({
    app,
    onClose,
    onPatch,
    onDelete,
}: {
    app: JobApplication;
    onClose: () => void;
    onPatch: (patch: Partial<JobApplication>) => void;
    onDelete: () => void;
}) {
    const [notes, setNotes] = useState(app.notes || "");
    const [dirty, setDirty] = useState(false);

    useEffect(() => {
        setNotes(app.notes || "");
        setDirty(false);
    }, [app.id]);

    const saveNotes = () => {
        onPatch({ notes });
        setDirty(false);
    };

    return (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
            <div
                className="w-full max-w-2xl bg-white border-l border-stone-200 h-full overflow-y-auto shadow-xl"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="sticky top-0 bg-white/95 backdrop-blur-sm border-b border-stone-200 p-4 flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                        <Briefcase className="w-5 h-5 text-indigo-500 shrink-0" />
                        <div className="min-w-0">
                            <h2 className="text-lg font-semibold text-stone-900 truncate">{app.job_title}</h2>
                            <p className="text-xs text-stone-500 truncate">{app.company || "—"}</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 rounded-lg hover:bg-stone-100 text-stone-500"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                <div className="p-4 space-y-5">
                    {/* Status + quick actions */}
                    <div className="flex items-center gap-3 flex-wrap">
                        <StatusSelect value={app.status} onChange={(s) => onPatch({ status: s })} />
                        {app.job_url && (
                            <a
                                href={app.job_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-700"
                            >
                                <ExternalLink size={12} /> LinkedIn
                            </a>
                        )}
                        {app.resume_drive_url && (
                            <a
                                href={app.resume_drive_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1.5 text-xs text-emerald-600 hover:text-emerald-700"
                            >
                                <FileText size={12} /> Tailored Resume
                            </a>
                        )}
                        {app.analysis_drive_url && (
                            <a
                                href={app.analysis_drive_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-700"
                            >
                                <Target size={12} /> Fit Analysis
                            </a>
                        )}
                        <button
                            onClick={() => {
                                if (confirm("Delete this application?")) onDelete();
                            }}
                            className="ml-auto p-1.5 rounded-md text-rose-500 hover:bg-rose-50"
                        >
                            <Trash2 size={14} />
                        </button>
                    </div>

                    {/* Meta grid */}
                    <div className="grid grid-cols-2 gap-3">
                        <div className="bg-stone-50 border border-stone-200 rounded-lg p-3">
                            <div className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">
                                Location
                            </div>
                            <div className="text-sm text-stone-900 flex items-center gap-1.5">
                                <MapPin size={12} className="text-stone-400" />
                                {app.location || "—"}
                            </div>
                        </div>
                        <div className="bg-stone-50 border border-stone-200 rounded-lg p-3">
                            <div className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">
                                Salary
                            </div>
                            <div className="text-sm text-stone-900">{app.salary || "—"}</div>
                        </div>
                        <div className="bg-stone-50 border border-stone-200 rounded-lg p-3">
                            <div className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">
                                Fit Score
                            </div>
                            <div className="text-sm text-stone-900">
                                {app.fit_score != null ? `${app.fit_score}/100` : "—"}
                            </div>
                        </div>
                        <div className="bg-stone-50 border border-stone-200 rounded-lg p-3">
                            <div className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">
                                Captured
                            </div>
                            <div className="text-sm text-stone-900">{timeAgo(app.created_at)}</div>
                        </div>
                    </div>

                    {/* People */}
                    {app.people && app.people.length > 0 && (
                        <div>
                            <div className="text-xs uppercase tracking-wider text-stone-500 mb-2 flex items-center gap-1.5">
                                <Users size={12} /> People to reach out to
                            </div>
                            <div className="space-y-2">
                                {app.people.map((p, i) => {
                                    const roleLabel =
                                        p.role === "hiring_manager"
                                            ? { text: "Hiring Team", color: "bg-emerald-50 text-emerald-700 border-emerald-200" }
                                            : p.role === "poster"
                                                ? { text: "Job Poster", color: "bg-indigo-50 text-indigo-700 border-indigo-200" }
                                                : { text: "Connection", color: "bg-blue-50 text-blue-700 border-blue-200" };
                                    return (
                                        <a
                                            key={i}
                                            href={p.profile_url}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="flex items-start gap-3 bg-stone-50 hover:bg-stone-100 border border-stone-200 hover:border-stone-300 rounded-lg p-3 transition-colors"
                                        >
                                            <UserCircle className="w-8 h-8 text-stone-400 shrink-0" />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <span className="text-sm font-medium text-stone-900">{p.name}</span>
                                                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] border ${roleLabel.color}`}>
                                                        {roleLabel.text}
                                                    </span>
                                                </div>
                                                {p.title && (
                                                    <div className="text-xs text-stone-500 mt-0.5 truncate">{p.title}</div>
                                                )}
                                            </div>
                                            <ExternalLink size={12} className="text-stone-400 shrink-0 mt-1" />
                                        </a>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Review loop */}
                    <ReviewLoopPanel app={app} onPatch={onPatch} />

                    {/* Notes */}
                    <div>
                        <div className="flex items-center justify-between mb-2">
                            <div className="text-xs uppercase tracking-wider text-stone-500">Notes</div>
                            {dirty && (
                                <button
                                    onClick={saveNotes}
                                    className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700"
                                >
                                    <Save size={12} /> Save
                                </button>
                            )}
                        </div>
                        <textarea
                            value={notes}
                            onChange={(e) => {
                                setNotes(e.target.value);
                                setDirty(true);
                            }}
                            onBlur={() => dirty && saveNotes()}
                            placeholder="Interview prep, recruiter name, follow-up reminders…"
                            rows={6}
                            className="w-full bg-white border border-stone-200 focus:border-indigo-500 rounded-lg p-3 text-sm text-stone-900 placeholder-stone-400 focus:outline-none"
                        />
                    </div>

                    {/* Description */}
                    <div>
                        <div className="text-xs uppercase tracking-wider text-stone-500 mb-2">
                            Job Description
                        </div>
                        <div className="bg-stone-50 border border-stone-200 rounded-lg p-3 text-sm text-stone-700 whitespace-pre-wrap max-h-96 overflow-y-auto">
                            {app.job_description || "—"}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function JobApplicationsPage() {
    const [apps, setApps] = useState<JobApplication[]>([]);
    const [stats, setStats] = useState<JobApplicationStats | null>(null);
    const [view, setView] = useState<"table" | "kanban">("table");
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState<string>("");
    const [selected, setSelected] = useState<JobApplication | null>(null);
    const [tab, setTab] = useState<"pipeline" | "discover">(() => {
        if (typeof window !== "undefined") {
            const stored = localStorage.getItem("job_applications_tab");
            if (stored === "discover" || stored === "pipeline") return stored;
        }
        return "pipeline";
    });

    const switchTab = (t: "pipeline" | "discover") => {
        setTab(t);
        localStorage.setItem("job_applications_tab", t);
    };
    const [pendingSelectAppId, setPendingSelectAppId] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [list, s] = await Promise.all([
                jobApplicationsApi.list({ status: statusFilter || undefined, search: search || undefined }),
                jobApplicationsApi.stats(),
            ]);
            setApps(list);
            setStats(s);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, [statusFilter, search]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        if (!pendingSelectAppId) return;
        const found = apps.find((a) => a.id === pendingSelectAppId);
        if (found) {
            setSelected(found);
            setPendingSelectAppId(null);
        }
    }, [apps, pendingSelectAppId]);

    const patch = async (id: string, data: Partial<JobApplication>) => {
        const updated = await jobApplicationsApi.update(id, data);
        setApps((prev) => prev.map((a) => (a.id === id ? updated : a)));
        if (selected?.id === id) setSelected(updated);
        jobApplicationsApi.stats().then(setStats).catch(() => {});
    };

    const remove = async (id: string) => {
        await jobApplicationsApi.delete(id);
        setApps((prev) => prev.filter((a) => a.id !== id));
        if (selected?.id === id) setSelected(null);
        jobApplicationsApi.stats().then(setStats).catch(() => {});
    };

    const filtered = useMemo(() => apps, [apps]);

    return (
        <div className="min-h-screen bg-surface-1 text-stone-900">
            <div className="max-w-[1600px] mx-auto p-6 space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold text-stone-900 flex items-center gap-2">
                            <Briefcase className="text-indigo-500" /> Job Applications
                        </h1>
                        <p className="text-sm text-stone-500 mt-1">
                            {tab === "pipeline"
                                ? "Jobs captured from LinkedIn via the Sutra Chrome extension."
                                : "Discover fresh postings across ATS feeds, filtered for H-1B sponsors."}
                        </p>
                    </div>
                    {tab === "pipeline" && (
                        <div className="flex items-center gap-2">
                            <MasterResumePicker />
                            <button
                                onClick={load}
                                className="inline-flex items-center gap-2 px-3 py-1.5 bg-white border border-stone-200 hover:border-stone-300 rounded-lg text-sm text-stone-700 shadow-sm"
                            >
                                <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
                            </button>
                        </div>
                    )}
                </div>

                {/* Tab strip */}
                <div className="inline-flex bg-stone-100 border border-stone-200 rounded-lg p-0.5">
                    <button
                        onClick={() => switchTab("pipeline")}
                        className={`px-4 py-1.5 text-sm rounded-md transition-colors ${
                            tab === "pipeline"
                                ? "bg-white text-stone-900 shadow-sm"
                                : "text-stone-500 hover:text-stone-700"
                        }`}
                    >
                        Pipeline
                    </button>
                    <button
                        onClick={() => switchTab("discover")}
                        className={`px-4 py-1.5 text-sm rounded-md transition-colors ${
                            tab === "discover"
                                ? "bg-white text-stone-900 shadow-sm"
                                : "text-stone-500 hover:text-stone-700"
                        }`}
                    >
                        Discover
                    </button>
                </div>

                {tab === "discover" ? (
                    <DiscoveryTab
                        onAppliedJump={(applicationId) => {
                            setPendingSelectAppId(applicationId);
                            switchTab("pipeline");
                            load();
                        }}
                    />
                ) : (
                    <>
                {/* Stats */}
                {stats && (
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                        <StatCard
                            label="Total"
                            value={stats.total}
                            icon={Briefcase}
                            accent="bg-indigo-50 text-indigo-600"
                        />
                        <StatCard
                            label="This Week"
                            value={stats.this_week}
                            icon={Calendar}
                            accent="bg-blue-50 text-blue-600"
                        />
                        <StatCard
                            label="Applied"
                            value={
                                (stats.by_status.applied || 0) +
                                (stats.by_status.interviewing || 0) +
                                (stats.by_status.offer || 0) +
                                (stats.by_status.rejected || 0)
                            }
                            icon={FileText}
                            accent="bg-emerald-50 text-emerald-600"
                        />
                        <StatCard
                            label="Interviewing"
                            value={stats.by_status.interviewing || 0}
                            icon={Target}
                            accent="bg-amber-50 text-amber-600"
                        />
                        <StatCard
                            label="Response Rate"
                            value={`${stats.response_rate}%`}
                            icon={TrendingUp}
                            accent="bg-rose-50 text-rose-600"
                            subtitle="Interviews ÷ Applied+"
                        />
                    </div>
                )}

                {/* Filters */}
                <div className="flex items-center gap-2 flex-wrap">
                    <div className="relative flex-1 min-w-[220px] max-w-md">
                        <Search
                            size={14}
                            className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400"
                        />
                        <input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search title, company, description, notes…"
                            className="w-full bg-white border border-stone-200 rounded-lg pl-9 pr-3 py-2 text-sm placeholder-stone-400 focus:border-indigo-500 focus:outline-none"
                        />
                    </div>
                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        className="bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-700 focus:border-indigo-500 focus:outline-none"
                    >
                        <option value="">All statuses</option>
                        {JOB_APP_STATUSES.map((s) => (
                            <option key={s} value={s}>
                                {STATUS_META[s].label}
                            </option>
                        ))}
                    </select>
                    <div className="ml-auto inline-flex bg-stone-100 border border-stone-200 rounded-lg p-0.5">
                        <button
                            onClick={() => setView("table")}
                            className={`px-3 py-1.5 text-xs rounded-md inline-flex items-center gap-1.5 ${
                                view === "table" ? "bg-white text-stone-900 shadow-sm" : "text-stone-500"
                            }`}
                        >
                            <ListIcon size={14} /> Table
                        </button>
                        <button
                            onClick={() => setView("kanban")}
                            className={`px-3 py-1.5 text-xs rounded-md inline-flex items-center gap-1.5 ${
                                view === "kanban" ? "bg-white text-stone-900 shadow-sm" : "text-stone-500"
                            }`}
                        >
                            <LayoutGrid size={14} /> Kanban
                        </button>
                    </div>
                </div>

                {/* Main view */}
                {view === "table" ? (
                    <div className="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
                        <table className="w-full text-sm">
                            <thead className="bg-stone-50 border-b border-stone-200">
                                <tr className="text-left text-[11px] uppercase tracking-wider text-stone-500">
                                    <th className="px-4 py-2.5 font-medium">Role</th>
                                    <th className="px-4 py-2.5 font-medium">Company</th>
                                    <th className="px-4 py-2.5 font-medium">Location</th>
                                    <th className="px-4 py-2.5 font-medium">Status</th>
                                    <th className="px-4 py-2.5 font-medium">Fit</th>
                                    <th className="px-4 py-2.5 font-medium">Resume</th>
                                    <th className="px-4 py-2.5 font-medium">Contacts</th>
                                    <th className="px-4 py-2.5 font-medium">Captured</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((a) => (
                                    <tr
                                        key={a.id}
                                        onClick={() => setSelected(a)}
                                        className="border-b border-stone-100 hover:bg-stone-50 cursor-pointer"
                                    >
                                        <td className="px-4 py-3 font-medium text-stone-900 max-w-[280px] truncate">
                                            {a.job_title}
                                        </td>
                                        <td className="px-4 py-3 text-stone-700">{a.company || "—"}</td>
                                        <td className="px-4 py-3 text-stone-500">{a.location || "—"}</td>
                                        <td className="px-4 py-3">
                                            <StatusSelect
                                                value={a.status}
                                                onChange={(s) => patch(a.id, { status: s })}
                                            />
                                        </td>
                                        <td className="px-4 py-3 text-stone-700">
                                            {a.fit_score != null ? `${a.fit_score}` : "—"}
                                        </td>
                                        <td className="px-4 py-3">
                                            {a.resume_drive_url ? (
                                                <a
                                                    href={a.resume_drive_url}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    onClick={(e) => e.stopPropagation()}
                                                    className="inline-flex items-center gap-1 text-xs text-emerald-600 hover:text-emerald-700"
                                                >
                                                    <FileText size={12} /> Open
                                                </a>
                                            ) : (
                                                <span className="text-stone-400 text-xs">—</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3">
                                            {a.people && a.people.length > 0 ? (
                                                <span className="inline-flex items-center gap-1 text-xs text-stone-700">
                                                    <Users size={12} className="text-stone-400" />
                                                    {a.people.length}
                                                </span>
                                            ) : (
                                                <span className="text-stone-400 text-xs">—</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-stone-400 text-xs">
                                            {timeAgo(a.created_at)}
                                        </td>
                                    </tr>
                                ))}
                                {filtered.length === 0 && (
                                    <tr>
                                        <td
                                            colSpan={8}
                                            className="px-4 py-12 text-center text-stone-400 text-sm"
                                        >
                                            {loading ? "Loading…" : "No job applications yet. Capture one from LinkedIn with the Sutra extension."}
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <Kanban
                        applications={filtered}
                        onStatusChange={(id, s) => patch(id, { status: s })}
                        onOpen={(a) => setSelected(a)}
                    />
                )}
                    </>
                )}
            </div>

            {selected && (
                <Drawer
                    app={selected}
                    onClose={() => setSelected(null)}
                    onPatch={(p) => patch(selected.id, p)}
                    onDelete={() => remove(selected.id)}
                />
            )}
        </div>
    );
}
