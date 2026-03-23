"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
    Plus,
    Trash2,
    Play,
    CalendarClock,
    CheckCircle,
    XCircle,
    Clock,
    Loader2,
    Pencil,
    Layers,
    AlertTriangle,
    ChevronDown,
    ChevronRight,
    History,
} from "lucide-react";
import { batchJobsApi, jobsApi, BatchJob, BatchJobRun, Job } from "@/lib/api";

function prettySchedule(cron: string): string {
    const parts = cron.split(" ");
    if (parts.length !== 5) return cron;
    const [minute, hour, , , dayOfWeek] = parts;
    const days: Record<string, string> = {
        "0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed",
        "4": "Thu", "5": "Fri", "6": "Sat",
    };
    if (minute === "*" || hour === "*") {
        // interval-style like */30
        if (minute.startsWith("*/")) return `Every ${minute.slice(2)} min`;
        return cron;
    }
    const dayNames = dayOfWeek === "*"
        ? "Daily"
        : dayOfWeek.split(",").map((d) => days[d] ?? d).join(", ");
    const h = parseInt(hour, 10);
    const ampm = h >= 12 ? "PM" : "AM";
    const h12 = h % 12 || 12;
    return `${dayNames} at ${h12}:${String(minute).padStart(2, "0")} ${ampm} PT`;
}

function StatusBadge({ status }: { status: string | null }) {
    if (!status) return <span className="text-stone-400 text-xs flex items-center gap-1"><Clock size={12} /> Never run</span>;
    if (status === "success") return <span className="text-emerald-600 text-xs flex items-center gap-1"><CheckCircle size={12} /> Success</span>;
    if (status === "partial") return <span className="text-amber-600 text-xs flex items-center gap-1"><AlertTriangle size={12} /> Partial</span>;
    if (status === "failed") return <span className="text-rose-600 text-xs flex items-center gap-1"><XCircle size={12} /> Failed</span>;
    if (status === "running") return <span className="text-indigo-600 text-xs flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Running</span>;
    return null;
}

function RunsDrawer({ batchId, jobMap }: { batchId: string; jobMap: Record<string, Job> }) {
    const [runs, setRuns] = useState<BatchJobRun[]>([]);
    const [loading, setLoading] = useState(true);
    const [expanded, setExpanded] = useState<string | null>(null);

    useEffect(() => {
        batchJobsApi.listRuns(batchId).then(setRuns).finally(() => setLoading(false));
    }, [batchId]);

    if (loading) return <div className="p-4 text-stone-400 text-sm flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Loading runs…</div>;
    if (runs.length === 0) return <div className="p-4 text-stone-400 text-sm">No runs yet.</div>;

    return (
        <div className="divide-y divide-stone-100">
            {runs.map((run) => {
                const isOpen = expanded === run.id;
                const resultEntries = Object.entries(run.results || {});
                const duration = run.completed_at
                    ? Math.round((new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000)
                    : null;

                return (
                    <div key={run.id}>
                        <button
                            onClick={() => setExpanded(isOpen ? null : run.id)}
                            className="w-full flex items-center justify-between px-4 py-3 hover:bg-stone-50 text-left"
                        >
                            <div className="flex items-center gap-3">
                                {isOpen ? <ChevronDown size={14} className="text-stone-400" /> : <ChevronRight size={14} className="text-stone-400" />}
                                <StatusBadge status={run.status} />
                                <span className="text-xs text-stone-500">
                                    {new Date(run.started_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
                                </span>
                            </div>
                            <div className="flex items-center gap-3 text-xs text-stone-400">
                                <span>{resultEntries.length} job{resultEntries.length !== 1 ? "s" : ""}</span>
                                {duration !== null && <span>{duration}s</span>}
                            </div>
                        </button>
                        {isOpen && (
                            <div className="bg-stone-50 px-6 pb-3">
                                <table className="w-full text-xs">
                                    <thead>
                                        <tr className="text-stone-400 uppercase tracking-wider">
                                            <th className="text-left py-1 font-medium">Job</th>
                                            <th className="text-left py-1 font-medium">Status</th>
                                            <th className="text-left py-1 font-medium">Duration</th>
                                            <th className="text-left py-1 font-medium">Error</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-stone-100">
                                        {resultEntries.map(([jid, res]) => (
                                            <tr key={jid}>
                                                <td className="py-1.5 text-stone-700 font-mono">
                                                    {jobMap[jid]?.name ?? jid.slice(0, 8) + "…"}
                                                </td>
                                                <td className="py-1.5">
                                                    <StatusBadge status={res.status} />
                                                </td>
                                                <td className="py-1.5 text-stone-500">{res.duration_ms}ms</td>
                                                <td className="py-1.5 text-rose-500 max-w-[200px] truncate">{res.error ?? "—"}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

export default function BatchJobsPage() {
    const [batchJobs, setBatchJobs] = useState<BatchJob[]>([]);
    const [jobs, setJobs] = useState<Job[]>([]);
    const [loading, setLoading] = useState(true);
    const [triggeringId, setTriggeringId] = useState<string | null>(null);
    const [runsOpenId, setRunsOpenId] = useState<string | null>(null);

    const jobMap = Object.fromEntries(jobs.map((j) => [j.id, j]));

    useEffect(() => {
        Promise.all([batchJobsApi.list(), jobsApi.list()])
            .then(([batches, jbs]) => {
                setBatchJobs(batches);
                setJobs(jbs);
            })
            .finally(() => setLoading(false));
    }, []);

    async function handleDelete(id: string) {
        if (!confirm("Delete this batch job?")) return;
        await batchJobsApi.delete(id);
        setBatchJobs((prev) => prev.filter((b) => b.id !== id));
    }

    async function handleToggle(batch: BatchJob) {
        await batchJobsApi.update(batch.id, { is_active: !batch.is_active });
        setBatchJobs((prev) =>
            prev.map((b) => b.id === batch.id ? { ...b, is_active: !b.is_active } : b)
        );
    }

    async function handleRun(id: string) {
        setTriggeringId(id);
        try {
            await batchJobsApi.run(id);
        } finally {
            setTriggeringId(null);
        }
    }

    if (loading) {
        return (
            <div className="flex h-full items-center justify-center text-gray-400">
                <Loader2 size={24} className="animate-spin mr-3" />
                Loading Batch Jobs…
            </div>
        );
    }

    return (
        <div className="flex flex-col h-[calc(100vh-4rem)] animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-stone-900">Batch Jobs</h1>
                    <p className="text-stone-500 mt-1">
                        Group multiple jobs into a single heartbeat schedule — run them all at once.
                    </p>
                </div>
                <Link
                    href="/batch-jobs/new"
                    className="flex items-center gap-2 px-4 py-2 bg-violet-500 hover:bg-violet-600 text-white rounded-lg transition-colors font-medium shadow-lg shadow-violet-500/20"
                >
                    <Plus size={18} />
                    New Batch Job
                </Link>
            </div>

            {batchJobs.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-stone-200 rounded-xl bg-stone-50/50">
                    <Layers size={48} className="text-stone-300 mb-4" />
                    <h2 className="text-xl font-semibold text-stone-800 mb-2">No batch jobs yet</h2>
                    <p className="text-stone-500 mb-6 max-w-sm text-center">
                        Create a batch job to run multiple agent jobs together on a single heartbeat schedule.
                    </p>
                    <Link
                        href="/batch-jobs/new"
                        className="flex items-center gap-2 px-4 py-2 bg-white border border-stone-200 text-stone-700 hover:bg-stone-50 rounded-lg transition-colors font-medium shadow-sm"
                    >
                        <Plus size={18} />
                        Create Your First Batch Job
                    </Link>
                </div>
            ) : (
                <div className="space-y-6 overflow-y-auto">
                    {batchJobs.map((batch) => (
                        <div
                            key={batch.id}
                            className={`bg-white border rounded-xl overflow-hidden transition-all shadow-sm ${
                                batch.is_active ? "border-stone-200" : "border-stone-100 opacity-60"
                            }`}
                        >
                            {/* Card header */}
                            <div className="p-5 flex items-start justify-between gap-4">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-3 mb-1">
                                        <h3 className="text-lg font-bold text-stone-800 truncate">{batch.name}</h3>
                                        <span className={`px-2 py-0.5 text-[10px] font-bold uppercase rounded-full border ${
                                            batch.execution_mode === "sequential"
                                                ? "bg-amber-50 text-amber-600 border-amber-100"
                                                : "bg-indigo-50 text-indigo-600 border-indigo-100"
                                        }`}>
                                            {batch.execution_mode}
                                        </span>
                                    </div>
                                    {batch.description && (
                                        <p className="text-stone-500 text-sm mb-2">{batch.description}</p>
                                    )}
                                    <div className="flex flex-wrap items-center gap-3">
                                        <span className="flex items-center gap-1.5 text-[11px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-lg px-2.5 py-1">
                                            <CalendarClock size={12} />
                                            {prettySchedule(batch.cron_expression)}
                                        </span>
                                        <span className="text-xs text-stone-500">
                                            {batch.job_ids.length} job{batch.job_ids.length !== 1 ? "s" : ""}
                                        </span>
                                        <StatusBadge status={batch.last_run_status} />
                                        {batch.last_run_at && (
                                            <span className="text-xs text-stone-400">
                                                Last: {new Date(batch.last_run_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
                                            </span>
                                        )}
                                    </div>
                                </div>

                                {/* Actions */}
                                <div className="flex items-center gap-2 flex-shrink-0">
                                    <button
                                        onClick={() => handleToggle(batch)}
                                        className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all border ${
                                            batch.is_active
                                                ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border-emerald-100"
                                                : "bg-stone-200 text-stone-600 hover:bg-stone-300 border-stone-300"
                                        }`}
                                    >
                                        {batch.is_active ? "Active" : "Paused"}
                                    </button>
                                    <button
                                        onClick={() => handleRun(batch.id)}
                                        disabled={triggeringId === batch.id}
                                        className="p-2 text-stone-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                                        title="Run Now"
                                    >
                                        {triggeringId === batch.id
                                            ? <Loader2 size={16} className="animate-spin" />
                                            : <Play size={16} className="fill-current" />}
                                    </button>
                                    <button
                                        onClick={() => setRunsOpenId(runsOpenId === batch.id ? null : batch.id)}
                                        className="p-2 text-stone-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-colors"
                                        title="Run History"
                                    >
                                        <History size={16} />
                                    </button>
                                    <Link
                                        href={`/batch-jobs/${batch.id}`}
                                        className="p-2 text-stone-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                                        title="Edit"
                                    >
                                        <Pencil size={16} />
                                    </Link>
                                    <button
                                        onClick={() => handleDelete(batch.id)}
                                        className="p-2 text-stone-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                                        title="Delete"
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </div>
                            </div>

                            {/* Member jobs pills */}
                            {batch.job_ids.length > 0 && (
                                <div className="px-5 pb-3 flex flex-wrap gap-2">
                                    {batch.job_ids.map((jid, idx) => (
                                        <span
                                            key={jid}
                                            className="flex items-center gap-1.5 px-2.5 py-1 bg-stone-100 text-stone-600 text-xs rounded-lg font-medium"
                                        >
                                            {batch.execution_mode === "sequential" && (
                                                <span className="text-stone-400 font-mono">{idx + 1}.</span>
                                            )}
                                            {jobMap[jid]?.name ?? jid.slice(0, 8) + "…"}
                                        </span>
                                    ))}
                                </div>
                            )}

                            {/* Run history drawer */}
                            {runsOpenId === batch.id && (
                                <div className="border-t border-stone-100">
                                    <div className="px-5 py-2 bg-stone-50 text-xs font-semibold text-stone-500 uppercase tracking-wider">
                                        Run History
                                    </div>
                                    <RunsDrawer batchId={batch.id} jobMap={jobMap} />
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
