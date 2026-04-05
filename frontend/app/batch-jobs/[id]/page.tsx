"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { ArrowLeft, Save, Loader2, CalendarClock, Bell, Mail, Send, Check } from "lucide-react";
import { batchJobsApi, jobsApi, BatchJob, Job } from "@/lib/api";

const DAYS_OF_WEEK = [
    { label: "Sun", value: "0" },
    { label: "Mon", value: "1" },
    { label: "Tue", value: "2" },
    { label: "Wed", value: "3" },
    { label: "Thu", value: "4" },
    { label: "Fri", value: "5" },
    { label: "Sat", value: "6" },
];

const HOURS = Array.from({ length: 24 }, (_, i) => {
    const h12 = i % 12 || 12;
    const ampm = i < 12 ? "AM" : "PM";
    return { label: `${h12}:00 ${ampm}`, value: String(i) };
});

const MINUTES = ["00", "15", "30", "45"].map((m) => ({ label: `:${m}`, value: m }));

function buildCron(useInterval: boolean, intervalMin: string, days: string[], hour: string, minute: string): string {
    if (useInterval) return `*/${intervalMin} * * * *`;
    const dayPart = days.length === 0 || days.length === 7 ? "*" : days.join(",");
    return `${parseInt(minute, 10)} ${hour} * * ${dayPart}`;
}

function parseCron(cron: string): { isInterval: boolean; intervalMin: string; days: string[]; hour: string; minute: string } {
    const parts = cron.split(" ");
    if (parts.length === 5 && parts[0].startsWith("*/")) {
        return { isInterval: true, intervalMin: parts[0].slice(2), days: ["1", "2", "3", "4", "5"], hour: "9", minute: "00" };
    }
    if (parts.length !== 5) return { isInterval: false, intervalMin: "30", days: ["1"], hour: "9", minute: "00" };
    const [min, h, , , dow] = parts;
    const days = dow === "*" ? DAYS_OF_WEEK.map((d) => d.value) : dow.split(",");
    return { isInterval: false, intervalMin: "30", days, hour: h, minute: String(parseInt(min, 10)).padStart(2, "0") };
}

export default function EditBatchJobPage() {
    const router = useRouter();
    const params = useParams();
    const id = params.id as string;

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [jobs, setJobs] = useState<Job[]>([]);

    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);
    const [executionMode, setExecutionMode] = useState<"parallel" | "sequential">("parallel");
    const [useInterval, setUseInterval] = useState(true);
    const [intervalMin, setIntervalMin] = useState("30");
    const [selectedDays, setSelectedDays] = useState<string[]>(["1", "2", "3", "4", "5"]);
    const [hour, setHour] = useState("9");
    const [minute, setMinute] = useState("00");
    const [notifyEmail, setNotifyEmail] = useState(false);
    const [emailAddr, setEmailAddr] = useState("");
    const [notifyTelegram, setNotifyTelegram] = useState(false);
    const [telegramChatId, setTelegramChatId] = useState("");

    useEffect(() => {
        Promise.all([batchJobsApi.get(id), jobsApi.list()]).then(([batch, jbs]) => {
            setJobs(jbs);
            setName(batch.name);
            setDescription(batch.description ?? "");
            setSelectedJobIds(batch.job_ids ?? []);
            setExecutionMode(batch.execution_mode as "parallel" | "sequential");
            const parsed = parseCron(batch.cron_expression);
            setUseInterval(parsed.isInterval);
            setIntervalMin(parsed.intervalMin);
            setSelectedDays(parsed.days);
            setHour(parsed.hour);
            setMinute(parsed.minute);
            setNotifyEmail(!!batch.notify_email);
            setEmailAddr(batch.notify_email ?? "");
            setNotifyTelegram(!!batch.notify_telegram_chat_id);
            setTelegramChatId(batch.notify_telegram_chat_id ?? "");
        }).finally(() => setLoading(false));
    }, [id]);

    function toggleJob(jid: string) {
        setSelectedJobIds((prev) =>
            prev.includes(jid) ? prev.filter((j) => j !== jid) : [...prev, jid]
        );
    }

    function toggleDay(val: string) {
        setSelectedDays((prev) =>
            prev.includes(val) ? prev.filter((d) => d !== val) : [...prev, val]
        );
    }

    const cronExpression = buildCron(useInterval, intervalMin, selectedDays, hour, minute);

    async function handleSave() {
        if (!name.trim()) return alert("Name is required.");
        if (selectedJobIds.length === 0) return alert("Select at least one job.");
        setSaving(true);
        try {
            await batchJobsApi.update(id, {
                name: name.trim(),
                description: description.trim() || undefined,
                job_ids: selectedJobIds,
                cron_expression: cronExpression,
                execution_mode: executionMode,
                notify_email: notifyEmail ? emailAddr : null,
                notify_telegram_chat_id: notifyTelegram ? telegramChatId : null,
            });
            router.push("/batch-jobs");
        } catch (err) {
            console.error(err);
            alert("Failed to save.");
        } finally {
            setSaving(false);
        }
    }

    if (loading) {
        return (
            <div className="flex h-full items-center justify-center text-gray-400">
                <Loader2 size={24} className="animate-spin mr-3" /> Loading…
            </div>
        );
    }

    return (
        <div className="max-w-2xl mx-auto py-8 px-4 space-y-8 animate-fade-in">
            <div className="flex items-center gap-4">
                <button onClick={() => router.push("/batch-jobs")} className="p-2 text-stone-400 hover:text-stone-600 hover:bg-stone-100 rounded-lg transition-colors">
                    <ArrowLeft size={20} />
                </button>
                <div>
                    <h1 className="text-2xl font-bold text-stone-900">Edit Batch Job</h1>
                    <p className="text-stone-500 text-sm">Update schedule, jobs, or execution settings.</p>
                </div>
            </div>

            <section className="bg-white border border-stone-200 rounded-xl p-6 space-y-4">
                <h2 className="font-semibold text-stone-800">Details</h2>
                <div>
                    <label className="block text-sm font-medium text-stone-700 mb-1">Name <span className="text-rose-500">*</span></label>
                    <input value={name} onChange={(e) => setName(e.target.value)} className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400" />
                </div>
                <div>
                    <label className="block text-sm font-medium text-stone-700 mb-1">Description</label>
                    <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400 resize-none" />
                </div>
            </section>

            <section className="bg-white border border-stone-200 rounded-xl p-6 space-y-4">
                <h2 className="font-semibold text-stone-800">Jobs</h2>
                <div className="space-y-2">
                    {jobs.map((job) => {
                        const checked = selectedJobIds.includes(job.id);
                        return (
                            <button key={job.id} onClick={() => toggleJob(job.id)}
                                className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-left transition-all ${checked ? "border-violet-300 bg-violet-50" : "border-stone-200 hover:border-stone-300 hover:bg-stone-50"}`}>
                                <div className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${checked ? "bg-violet-500 border-violet-500" : "border-stone-300"}`}>
                                    {checked && <Check size={10} className="text-white" strokeWidth={3} />}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="font-medium text-stone-800 text-sm">{job.name}</div>
                                    {job.description && <div className="text-stone-400 text-xs truncate">{job.description}</div>}
                                </div>
                                <span className="text-[10px] text-stone-400 font-mono uppercase">{job.execution_type}</span>
                            </button>
                        );
                    })}
                </div>
            </section>

            <section className="bg-white border border-stone-200 rounded-xl p-6 space-y-3">
                <h2 className="font-semibold text-stone-800">Execution Mode</h2>
                <div className="flex gap-3">
                    {(["parallel", "sequential"] as const).map((mode) => (
                        <button key={mode} onClick={() => setExecutionMode(mode)}
                            className={`flex-1 py-3 px-4 rounded-lg border text-sm font-medium transition-all ${executionMode === mode ? "border-violet-400 bg-violet-50 text-violet-700" : "border-stone-200 text-stone-600 hover:border-stone-300"}`}>
                            <div className="font-semibold capitalize">{mode}</div>
                            <div className="text-xs font-normal text-stone-400 mt-0.5">
                                {mode === "parallel" ? "All jobs run at the same time" : "Jobs run one after another in order"}
                            </div>
                        </button>
                    ))}
                </div>
            </section>

            <section className="bg-white border border-stone-200 rounded-xl p-6 space-y-4">
                <h2 className="font-semibold text-stone-800 flex items-center gap-2"><CalendarClock size={16} /> Schedule (Pacific Time)</h2>
                <div className="flex gap-3">
                    <button onClick={() => setUseInterval(true)} className={`flex-1 py-2.5 px-4 rounded-lg border text-sm font-medium transition-all ${useInterval ? "border-violet-400 bg-violet-50 text-violet-700" : "border-stone-200 text-stone-600 hover:border-stone-300"}`}>Interval</button>
                    <button onClick={() => setUseInterval(false)} className={`flex-1 py-2.5 px-4 rounded-lg border text-sm font-medium transition-all ${!useInterval ? "border-violet-400 bg-violet-50 text-violet-700" : "border-stone-200 text-stone-600 hover:border-stone-300"}`}>Specific time</button>
                </div>
                {useInterval ? (
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-2">Run every</label>
                        <select value={intervalMin} onChange={(e) => setIntervalMin(e.target.value)} className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400">
                            {["5", "10", "15", "30", "60"].map((m) => <option key={m} value={m}>{m} minutes</option>)}
                        </select>
                    </div>
                ) : (
                    <>
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-2">Days</label>
                            <div className="flex gap-1.5 flex-wrap">
                                {[{ label: "All" }, { label: "Weekdays" }, { label: "Weekend" }].map(({ label }) => (
                                    <button key={label} type="button" onClick={() => {
                                        if (label === "All") setSelectedDays(DAYS_OF_WEEK.map((d) => d.value));
                                        if (label === "Weekdays") setSelectedDays(["1", "2", "3", "4", "5"]);
                                        if (label === "Weekend") setSelectedDays(["0", "6"]);
                                    }} className="px-2.5 py-1 text-xs border border-stone-200 rounded-md text-stone-600 hover:bg-stone-100">{label}</button>
                                ))}
                                {DAYS_OF_WEEK.map((d) => (
                                    <button key={d.value} onClick={() => toggleDay(d.value)}
                                        className={`px-2.5 py-1 text-xs rounded-md border font-medium transition-all ${selectedDays.includes(d.value) ? "bg-violet-500 text-white border-violet-500" : "border-stone-200 text-stone-600 hover:bg-stone-50"}`}>
                                        {d.label}
                                    </button>
                                ))}
                            </div>
                        </div>
                        <div className="flex gap-4">
                            <div>
                                <label className="block text-sm font-medium text-stone-700 mb-1">Hour</label>
                                <select value={hour} onChange={(e) => setHour(e.target.value)} className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400">
                                    {HOURS.map((h) => <option key={h.value} value={h.value}>{h.label}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-stone-700 mb-1">Minute</label>
                                <select value={minute} onChange={(e) => setMinute(e.target.value)} className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400">
                                    {MINUTES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                                </select>
                            </div>
                        </div>
                    </>
                )}
                <div className="bg-stone-50 rounded-lg px-4 py-2 text-xs font-mono text-stone-500">
                    Cron: <span className="text-violet-600">{cronExpression}</span>
                </div>
            </section>

            <section className="bg-white border border-stone-200 rounded-xl p-6 space-y-4">
                <h2 className="font-semibold text-stone-800 flex items-center gap-2"><Bell size={16} /> Notifications</h2>
                <div>
                    <label className="flex items-center gap-3 cursor-pointer">
                        <input type="checkbox" checked={notifyEmail} onChange={(e) => setNotifyEmail(e.target.checked)} className="rounded" />
                        <span className="text-sm font-medium text-stone-700 flex items-center gap-1.5"><Mail size={14} /> Email</span>
                    </label>
                    {notifyEmail && <input value={emailAddr} onChange={(e) => setEmailAddr(e.target.value)} type="email" placeholder="you@example.com" className="mt-2 w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400" />}
                </div>
                <div>
                    <label className="flex items-center gap-3 cursor-pointer">
                        <input type="checkbox" checked={notifyTelegram} onChange={(e) => setNotifyTelegram(e.target.checked)} className="rounded" />
                        <span className="text-sm font-medium text-stone-700 flex items-center gap-1.5"><Send size={14} /> Telegram</span>
                    </label>
                    {notifyTelegram && <input value={telegramChatId} onChange={(e) => setTelegramChatId(e.target.value)} placeholder="Chat ID" className="mt-2 w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400" />}
                </div>
            </section>

            <div className="flex justify-end gap-3">
                <button onClick={() => router.push("/batch-jobs")} className="px-4 py-2 border border-stone-200 text-stone-700 hover:bg-stone-50 rounded-lg text-sm font-medium transition-colors">Cancel</button>
                <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-5 py-2 bg-violet-500 hover:bg-violet-600 text-white rounded-lg text-sm font-medium transition-colors shadow-lg shadow-violet-500/20 disabled:opacity-60">
                    {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                    Save Changes
                </button>
            </div>
        </div>
    );
}
