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
    LayoutGrid,
    List,
} from "lucide-react";
import { jobsApi, Job } from "@/lib/api";

const executionTypeLabel: Record<string, string> = {
    prompt: "Agent Prompt",
    workflow: "Internal Workflow",
    n8n_workflow: "n8n Workflow",
    docker_script: "Docker Script",
};

const executionTypeColor: Record<string, string> = {
    prompt: "bg-indigo-50 text-indigo-600 border-indigo-100",
    workflow: "bg-teal-50 text-teal-600 border-teal-100",
    n8n_workflow: "bg-orange-50 text-orange-600 border-orange-100",
    docker_script: "bg-blue-50 text-blue-600 border-blue-100",
};

function StatusIcon({ status }: { status: string | null }) {
    if (!status) return <Clock size={14} className="text-stone-400" />;
    if (status === "success") return <CheckCircle size={14} className="text-emerald-500" />;
    if (status === "failed") return <XCircle size={14} className="text-rose-500" />;
    if (status === "running") return <Loader2 size={14} className="text-indigo-500 animate-spin" />;
    return <Clock size={14} className="text-stone-400" />;
}

/** Humanize a cron expression into something more readable */
function prettySchedule(cron: string): string {
    const parts = cron.split(" ");
    if (parts.length !== 5) return cron;
    const [minute, hour, , , dayOfWeek] = parts;
    const days: Record<string, string> = { "0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed", "4": "Thu", "5": "Fri", "6": "Sat" };
    const dayNames = dayOfWeek === "*"
        ? "Daily"
        : dayOfWeek.split(",").map((d) => days[d] ?? d).join(", ");

    const h = parseInt(hour, 10);
    const ampm = h >= 12 ? "PM" : "AM";
    const h12 = h % 12 || 12;
    const timeStr = `${h12}:${String(minute).padStart(2, "0")} ${ampm} PT`;
    return `${dayNames} at ${timeStr}`;
}

export default function JobsPage() {
    const [jobs, setJobs] = useState<Job[]>([]);
    const [loading, setLoading] = useState(true);
    const [triggeringId, setTriggeringId] = useState<string | null>(null);
    const [viewMode, setViewMode] = useState<"grid" | "list">("list");

    useEffect(() => {
        loadJobs();
    }, []);

    async function loadJobs() {
        try {
            const data = await jobsApi.list();
            setJobs(data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }

    async function handleDelete(id: string) {
        if (!confirm("Delete this job?")) return;
        try {
            await jobsApi.delete(id);
            setJobs(jobs.filter((j) => j.id !== id));
        } catch (err) {
            console.error(err);
        }
    }

    async function handleToggle(job: Job) {
        try {
            await jobsApi.update(job.id, { is_active: !job.is_active });
            setJobs(jobs.map((j) => j.id === job.id ? { ...j, is_active: !j.is_active } : j));
        } catch (err) {
            console.error(err);
        }
    }

    async function handleRun(id: string) {
        setTriggeringId(id);
        try {
            await jobsApi.run(id);
            alert("Job triggered successfully!");
        } catch (err) {
            console.error(err);
            alert("Error triggering job.");
        } finally {
            setTriggeringId(null);
        }
    }

    if (loading) {
        return (
            <div className="flex h-full items-center justify-center text-gray-400">
                <Loader2 size={24} className="animate-spin mr-3" />
                Loading Jobs...
            </div>
        );
    }

    return (
        <div className="flex flex-col h-[calc(100vh-4rem)] animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-bold text-stone-900">
                        Scheduled Jobs
                    </h1>
                    <p className="text-stone-500 mt-1">
                        Run agent prompts, workflows, or n8n integrations on a schedule.
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    {/* View Toggle */}
                    <div className="flex bg-stone-100 p-0.5 rounded-lg border border-stone-200 mr-2">
                        <button
                            onClick={() => setViewMode("list")}
                            className={`p-1.5 rounded-md transition-all ${viewMode === "list" ? "bg-white text-stone-800 shadow-sm" : "text-stone-400 hover:text-stone-600"}`}
                            title="List View"
                        >
                            <List size={16} />
                        </button>
                        <button
                            onClick={() => setViewMode("grid")}
                            className={`p-1.5 rounded-md transition-all ${viewMode === "grid" ? "bg-white text-stone-800 shadow-sm" : "text-stone-400 hover:text-stone-600"}`}
                            title="Grid View"
                        >
                            <LayoutGrid size={16} />
                        </button>
                    </div>
                    <Link
                        href="/jobs/new"
                        className="flex items-center gap-2 px-4 py-2 bg-stone-800 hover:bg-stone-700 text-white rounded-lg transition-colors font-medium shadow-sm"
                    >
                        <Plus size={18} />
                        New Job
                    </Link>
                </div>
            </div>

            {jobs.length === 0 ? (
                <div className="flex-1 flex flex-col items-center justify-center border-2 border-dashed border-stone-200 rounded-xl bg-stone-50/50">
                    <CalendarClock size={48} className="text-stone-300 mb-4" />
                    <h2 className="text-xl font-semibold text-stone-800 mb-2">No scheduled jobs yet</h2>
                    <p className="text-stone-500 mb-6 max-w-sm text-center">
                        Create a job to run agent prompts or workflows on a recurring Pacific Time schedule.
                    </p>
                    <Link
                        href="/jobs/new"
                        className="flex items-center gap-2 px-4 py-2 bg-white border border-stone-200 text-stone-700 hover:bg-stone-50 rounded-lg transition-colors font-medium shadow-sm"
                    >
                        <Plus size={18} />
                        Create Your First Job
                    </Link>
                </div>
            ) : viewMode === "grid" ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 overflow-y-auto pr-2 pb-8">
                    {jobs.map((job) => (
                        <div
                            key={job.id}
                            className={`group flex flex-col bg-white border rounded-xl overflow-hidden transition-all duration-300 hover:shadow-xl hover:-translate-y-0.5 ${job.is_active
                                ? "border-stone-200 hover:border-indigo-300 shadow-sm"
                                : "border-stone-100 opacity-60 grayscale-[0.5]"
                                }`}
                        >
                            <div className="p-5 flex-1">
                                <div className="flex justify-between items-start mb-3">
                                    <h3 className="text-lg font-bold text-stone-800 group-hover:text-indigo-600 transition-colors line-clamp-1">
                                        {job.name}
                                    </h3>
                                    <span
                                        className={`ml-2 flex-shrink-0 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full border ${executionTypeColor[job.execution_type] ?? "bg-stone-100 text-stone-500 border-stone-200"}`}
                                    >
                                        {executionTypeLabel[job.execution_type] ?? job.execution_type}
                                    </span>
                                </div>
                                {job.description && (
                                    <p className="text-stone-500 text-sm line-clamp-2 mb-4 min-h-[2.5rem]">
                                        {job.description}
                                    </p>
                                )}

                                {/* Schedule pill */}
                                <div className="flex items-center gap-2 text-[11px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-lg px-2.5 py-1.5 w-fit mb-4">
                                    <CalendarClock size={12} />
                                    <span className="font-mono uppercase">{prettySchedule(job.cron_expression)}</span>
                                </div>

                                {/* Last run info */}
                                <div className="flex items-center gap-1.5 text-xs text-stone-400">
                                    <StatusIcon status={job.last_run_status} />
                                    <span>
                                        {job.last_run_at
                                            ? `Last run: ${new Date(job.last_run_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}`
                                            : "Never run"}
                                    </span>
                                </div>
                            </div>

                            <div className="bg-stone-50/50 p-3 mt-auto border-t border-stone-100 flex items-center justify-between gap-2">
                                {/* Enable/Disable toggle */}
                                <button
                                    onClick={() => handleToggle(job)}
                                    className={`flex-1 px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${job.is_active
                                        ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-100"
                                        : "bg-stone-200 text-stone-600 hover:bg-stone-300 border border-stone-300"
                                        }`}
                                >
                                    {job.is_active ? "Active" : "Paused"}
                                </button>

                                {/* Run now */}
                                <button
                                    onClick={() => handleRun(job.id)}
                                    disabled={triggeringId === job.id}
                                    className="p-2 text-stone-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors group/run"
                                    title="Run Now"
                                >
                                    {triggeringId === job.id
                                        ? <Loader2 size={16} className="animate-spin" />
                                        : <Play size={16} className="fill-current group-hover/run:scale-110 transition-transform" />}
                                </button>

                                {/* Edit */}
                                <Link
                                    href={`/jobs/${job.id}`}
                                    className="p-2 text-stone-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                                    title="Edit Job"
                                >
                                    <Pencil size={16} />
                                </Link>

                                {/* Delete */}
                                <button
                                    onClick={() => handleDelete(job.id)}
                                    className="p-2 text-stone-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                                    title="Delete Job"
                                >
                                    <Trash2 size={16} />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm flex-1 mb-8 overflow-y-auto">
                    <table className="w-full text-left">
                        <thead className="bg-stone-50/60 border-b border-stone-100 sticky top-0 z-10">
                            <tr>
                                <th className="px-6 py-4 text-[11px] font-bold text-stone-400 uppercase tracking-wider">Job</th>
                                <th className="px-6 py-4 text-[11px] font-bold text-stone-400 uppercase tracking-wider text-center">Status</th>
                                <th className="px-6 py-4 text-[11px] font-bold text-stone-400 uppercase tracking-wider text-center">Schedule</th>
                                <th className="px-6 py-4 text-[11px] font-bold text-stone-400 uppercase tracking-wider text-center">Type</th>
                                <th className="px-6 py-4 text-[11px] font-bold text-stone-400 uppercase tracking-wider text-center">Last Run</th>
                                <th className="px-6 py-4 text-[11px] font-bold text-stone-400 uppercase tracking-wider text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-stone-100">
                            {jobs.map((job) => (
                                <tr
                                    key={job.id}
                                    className={`group hover:bg-stone-50/60 transition-colors ${!job.is_active ? "opacity-60 grayscale-[0.5]" : ""}`}
                                >
                                    <td className="px-6 py-4">
                                        <div className="flex items-center gap-3">
                                            <div className="w-8 h-8 rounded-lg bg-stone-100 flex items-center justify-center flex-shrink-0">
                                                <CalendarClock size={14} className="text-stone-500" />
                                            </div>
                                            <div className="flex flex-col min-w-0">
                                                <span className="text-sm font-semibold text-stone-800 truncate">
                                                    {job.name}
                                                </span>
                                                {job.description && (
                                                    <span className="text-xs text-stone-400 truncate mt-0.5">
                                                        {job.description}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <button
                                            onClick={() => handleToggle(job)}
                                            className={`px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full border transition-all ${job.is_active
                                                ? "bg-emerald-50 text-emerald-600 border-emerald-100 hover:bg-emerald-100"
                                                : "bg-stone-100 text-stone-500 border-stone-200 hover:bg-stone-200"
                                                }`}
                                        >
                                            {job.is_active ? "Active" : "Paused"}
                                        </button>
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <div className="flex items-center justify-center gap-1.5 text-xs text-stone-500">
                                            <span className="font-medium">{prettySchedule(job.cron_expression)}</span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <span
                                            className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full border ${executionTypeColor[job.execution_type] ?? "bg-stone-100 text-stone-500 border-stone-200"}`}
                                        >
                                            {executionTypeLabel[job.execution_type] ?? job.execution_type}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <div className="flex items-center justify-center gap-1.5 text-xs text-stone-400">
                                            <StatusIcon status={job.last_run_status} />
                                            <span>
                                                {job.last_run_at
                                                    ? new Date(job.last_run_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })
                                                    : "Never"}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <div className="flex items-center justify-end gap-1">
                                            <button
                                                onClick={() => handleRun(job.id)}
                                                disabled={triggeringId === job.id}
                                                className="p-1.5 text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg transition-colors group/run"
                                                title="Run Now"
                                            >
                                                {triggeringId === job.id
                                                    ? <Loader2 size={14} className="animate-spin" />
                                                    : <Play size={14} className="fill-current group-hover/run:scale-110 transition-transform" />}
                                            </button>
                                            <Link
                                                href={`/jobs/${job.id}`}
                                                className="p-1.5 text-stone-400 hover:text-stone-700 hover:bg-stone-100 rounded-lg transition-colors px-2.5 py-1 bg-white border border-stone-200 text-xs font-semibold rounded-lg shadow-sm"
                                            >
                                                Edit
                                            </Link>
                                            <button
                                                onClick={() => handleDelete(job.id)}
                                                className="p-1.5 text-stone-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                                                title="Delete Job"
                                            >
                                                <Trash2 size={14} />
                                            </button>
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
