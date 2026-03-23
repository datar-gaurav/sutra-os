"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { CalendarClock, ArrowLeft, Save, Loader2, Info, Bell, Mail, Send } from "lucide-react";
import { jobsApi, agentsApi, workflowsApi } from "@/lib/api";

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

interface AgentOption { id: string; name: string; }
interface WorkflowOption { id: string; name: string; }

function buildCron(days: string[], hour: string, minute: string): string {
    const dayPart = days.length === 0 || days.length === 7 ? "*" : days.join(",");
    return `${parseInt(minute, 10)} ${hour} * * ${dayPart}`;
}

function parseCron(cron: string): { days: string[]; hour: string; minute: string } {
    const parts = cron.split(" ");
    if (parts.length !== 5) return { days: ["1"], hour: "9", minute: "00" };
    const [min, h, , , dow] = parts;
    const days = dow === "*" ? DAYS_OF_WEEK.map((d) => d.value) : dow.split(",");
    return { days, hour: h, minute: String(parseInt(min, 10)).padStart(2, "0") };
}

export default function EditJobPage() {
    const router = useRouter();
    const params = useParams();
    const jobId = params.id as string;

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [agents, setAgents] = useState<AgentOption[]>([]);
    const [workflows, setWorkflows] = useState<WorkflowOption[]>([]);

    // Form state
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [executionType, setExecutionType] = useState<"prompt" | "workflow" | "n8n_workflow">("prompt");
    const [agentId, setAgentId] = useState("");
    const [promptText, setPromptText] = useState("");
    const [workflowId, setWorkflowId] = useState("");
    const [n8nWebhookUrl, setN8nWebhookUrl] = useState("");
    const [isActive, setIsActive] = useState(true);

    // Schedule
    const [selectedDays, setSelectedDays] = useState<string[]>([]);
    const [hour, setHour] = useState("9");
    const [minute, setMinute] = useState("00");

    // Notifications
    const [notifyEnabled, setNotifyEnabled] = useState(false);
    const [notifyEmail, setNotifyEmail] = useState("");
    const [notifyTelegramEnabled, setNotifyTelegramEnabled] = useState(false);
    const [notifyTelegramChatId, setNotifyTelegramChatId] = useState("");

    useEffect(() => {
        if (!jobId) return;

        async function init() {
            try {
                // Load options
                const [agentsRes, workflowsRes, jobRes] = await Promise.all([
                    agentsApi.list(),
                    workflowsApi.list(),
                    jobsApi.get(jobId),
                ]);

                setAgents(agentsRes);
                setWorkflows(workflowsRes);

                // Populate form
                setName(jobRes.name);
                setDescription(jobRes.description || "");
                setExecutionType(jobRes.execution_type as "prompt" | "workflow" | "n8n_workflow");
                setIsActive(jobRes.is_active);

                if (jobRes.execution_type === "prompt") {
                    setAgentId(jobRes.target_id || "");
                    setPromptText(jobRes.prompt_text || "");
                } else if (jobRes.execution_type === "workflow") {
                    setWorkflowId(jobRes.target_id || "");
                } else if (jobRes.execution_type === "n8n_workflow") {
                    setN8nWebhookUrl(jobRes.n8n_webhook_url || "");
                }

                // Parse schedule
                const { days, hour, minute } = parseCron(jobRes.cron_expression);
                setSelectedDays(days);
                setHour(hour);
                setMinute(minute);

                // Notifications
                if (jobRes.notify_email) {
                    setNotifyEnabled(true);
                    setNotifyEmail(jobRes.notify_email);
                }
                if (jobRes.notify_telegram_chat_id) {
                    setNotifyTelegramEnabled(true);
                    setNotifyTelegramChatId(jobRes.notify_telegram_chat_id);
                }

                setLoading(false);
            } catch (err) {
                console.error(err);
                alert("Failed to load job details.");
                router.push("/jobs");
            }
        }

        init();
    }, [jobId, router]);

    function toggleDay(value: string) {
        setSelectedDays((prev) =>
            prev.includes(value) ? prev.filter((d) => d !== value) : [...prev, value]
        );
    }

    function selectAll() { setSelectedDays(DAYS_OF_WEEK.map((d) => d.value)); }
    function selectWeekdays() { setSelectedDays(["1", "2", "3", "4", "5"]); }
    function selectWeekend() { setSelectedDays(["0", "6"]); }

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();

        if (!name.trim()) { alert("Please enter a job name."); return; }
        if (selectedDays.length === 0) { alert("Please select at least one day."); return; }

        const cron = buildCron(selectedDays, hour, minute);

        const payload: Record<string, unknown> = {
            name,
            description: description || null,
            execution_type: executionType,
            cron_expression: cron,
            timezone: "America/Los_Angeles",
            is_active: isActive,
            notify_email: notifyEnabled && notifyEmail.trim() ? notifyEmail.trim() : null,
            notify_telegram_chat_id: notifyTelegramEnabled && notifyTelegramChatId.trim() ? notifyTelegramChatId.trim() : null,
        };

        if (executionType === "prompt") {
            payload.target_id = agentId || null;
            payload.prompt_text = promptText;
        } else if (executionType === "workflow") {
            payload.target_id = workflowId;
        } else if (executionType === "n8n_workflow") {
            payload.n8n_webhook_url = n8nWebhookUrl;
        }

        setSaving(true);
        try {
            await jobsApi.update(jobId, payload);
            router.push("/jobs");
        } catch (err) {
            console.error(err);
            alert("An error occurred while saving.");
        } finally {
            setSaving(false);
        }
    }

    const cronPreview = buildCron(selectedDays, hour, minute);

    if (loading) {
        return (
            <div className="flex h-full items-center justify-center text-gray-400">
                <Loader2 size={24} className="animate-spin mr-3" />
                Loading Job Details...
            </div>
        );
    }

    return (
        <div className="max-w-2xl mx-auto animate-fade-in">
            {/* Header */}
            <div className="flex items-center gap-4 mb-8">
                <button
                    onClick={() => router.back()}
                    className="p-2 rounded-lg hover:bg-stone-100 text-stone-400 transition-colors"
                >
                    <ArrowLeft size={20} />
                </button>
                <div>
                    <h1 className="text-3xl font-bold text-stone-900">
                        Edit Job
                    </h1>
                    <p className="text-stone-500 mt-0.5">Update your scheduled job settings.</p>
                </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
                {/* Basic Info */}
                <div className="bg-white border border-stone-200 shadow-sm rounded-xl p-6 space-y-4">
                    <h2 className="text-xs font-bold text-stone-500 uppercase tracking-widest">Job Details</h2>
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1.5">Name *</label>
                        <input
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all"
                            required
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1.5">Description</label>
                        <textarea
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            rows={2}
                            className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all resize-none"
                        />
                    </div>
                </div>

                {/* Execution Type */}
                <div className="bg-white border border-stone-200 shadow-sm rounded-xl p-6 space-y-4">
                    <h2 className="text-xs font-bold text-stone-500 uppercase tracking-widest">Execution Type</h2>
                    <div className="grid grid-cols-3 gap-3">
                        {(["prompt", "workflow", "n8n_workflow"] as const).map((type) => {
                            const labels: Record<string, string> = {
                                prompt: "Agent Prompt",
                                workflow: "Workflow",
                                n8n_workflow: "n8n Workflow",
                            };
                            return (
                                <button
                                    key={type}
                                    type="button"
                                    onClick={() => setExecutionType(type)}
                                    className={`p-3 rounded-xl border text-left transition-all ${executionType === type
                                        ? "bg-violet-50 border-violet-600 text-violet-800 shadow-md shadow-violet-200"
                                        : "bg-stone-50 border-stone-200 text-stone-600 hover:bg-stone-100"
                                        }`}
                                >
                                    <div className="font-semibold text-sm">{labels[type]}</div>
                                </button>
                            );
                        })}
                    </div>

                    {executionType === "prompt" && (
                        <div className="space-y-3 pt-2">
                            <div>
                                <label className="block text-sm font-medium text-stone-700 mb-1.5">Agent</label>
                                <select
                                    value={agentId}
                                    onChange={(e) => setAgentId(e.target.value)}
                                    className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all"
                                >
                                    <option value="">— Select Agent (optional) —</option>
                                    {agents.map((a) => (
                                        <option key={a.id} value={a.id}>{a.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-stone-700 mb-1.5">Prompt *</label>
                                <textarea
                                    value={promptText}
                                    onChange={(e) => setPromptText(e.target.value)}
                                    rows={3}
                                    required
                                    className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all resize-none"
                                />
                            </div>
                        </div>
                    )}

                    {executionType === "workflow" && (
                        <div className="pt-2">
                            <label className="block text-sm font-medium text-stone-700 mb-1.5">Workflow *</label>
                            <select
                                value={workflowId}
                                onChange={(e) => setWorkflowId(e.target.value)}
                                required
                                className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all"
                            >
                                <option value="">— Select Workflow —</option>
                                {workflows.map((w) => (
                                    <option key={w.id} value={w.id}>{w.name}</option>
                                ))}
                            </select>
                        </div>
                    )}

                    {executionType === "n8n_workflow" && (
                        <div className="pt-2">
                            <label className="block text-sm font-medium text-stone-700 mb-1.5">n8n Webhook URL *</label>
                            <input
                                type="url"
                                value={n8nWebhookUrl}
                                onChange={(e) => setN8nWebhookUrl(e.target.value)}
                                required
                                className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all"
                            />
                        </div>
                    )}
                </div>

                {/* Schedule */}
                <div className="bg-white border border-stone-200 shadow-sm rounded-xl p-6 space-y-4">
                    <h2 className="text-xs font-bold text-stone-500 uppercase tracking-widest">Schedule (Pacific Time)</h2>

                    <div>
                        <div className="flex items-center justify-between mb-2">
                            <label className="text-sm font-medium text-stone-700">Days of Week</label>
                            <div className="flex gap-2 text-xs">
                                <button type="button" onClick={selectAll} className="text-violet-600 hover:underline">All</button>
                                <button type="button" onClick={selectWeekdays} className="text-violet-600 hover:underline">Weekdays</button>
                                <button type="button" onClick={selectWeekend} className="text-violet-600 hover:underline">Weekend</button>
                            </div>
                        </div>
                        <div className="flex gap-2">
                            {DAYS_OF_WEEK.map((day) => (
                                <button
                                    key={day.value}
                                    type="button"
                                    onClick={() => toggleDay(day.value)}
                                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all border ${selectedDays.includes(day.value)
                                        ? "bg-violet-600 border-violet-600 text-white shadow-md shadow-violet-100"
                                        : "bg-stone-50 border-stone-200 text-stone-500 hover:bg-stone-100"
                                        }`}
                                >
                                    {day.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-2">Time</label>
                        <div className="flex gap-3">
                            <select
                                value={hour}
                                onChange={(e) => setHour(e.target.value)}
                                className="flex-1 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all"
                            >
                                {HOURS.map((h) => (
                                    <option key={h.value} value={h.value}>{h.label}</option>
                                ))}
                            </select>
                            <select
                                value={minute}
                                onChange={(e) => setMinute(e.target.value)}
                                className="w-28 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all"
                            >
                                {MINUTES.map((m) => (
                                    <option key={m.value} value={m.value}>{m.label}</option>
                                ))}
                            </select>
                        </div>
                    </div>

                    <div className="flex items-center gap-2 bg-stone-50 border border-stone-100 rounded-lg px-3 py-2">
                        <Info size={13} className="text-stone-400 flex-shrink-0" />
                        <span className="text-xs text-stone-500">Cron expression:&nbsp;</span>
                        <code className="text-xs text-violet-600 font-mono font-bold">{cronPreview}</code>
                    </div>
                </div>

                {/* Notifications */}
                <div className="bg-white border border-stone-200 shadow-sm rounded-xl p-6 space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                            <div className="p-1.5 bg-indigo-50 rounded-lg border border-indigo-100">
                                <Bell size={15} className="text-indigo-600" />
                            </div>
                            <div>
                                <h2 className="text-xs font-bold text-stone-500 uppercase tracking-widest">Email Notifications</h2>
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={() => setNotifyEnabled(!notifyEnabled)}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-all duration-300 focus:outline-none ${notifyEnabled ? "bg-indigo-600" : "bg-stone-200"}`}
                        >
                            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-md transition-all duration-300 ${notifyEnabled ? "translate-x-6" : "translate-x-1"}`} />
                        </button>
                    </div>

                    {notifyEnabled && (
                        <div className="animate-fade-in pt-1">
                            <label className="block text-sm font-medium text-stone-700 mb-1.5 flex items-center gap-1.5">
                                <Mail size={14} className="text-stone-400" />
                                Email Address *
                            </label>
                            <input
                                type="email"
                                value={notifyEmail}
                                onChange={(e) => setNotifyEmail(e.target.value)}
                                required={notifyEnabled}
                                className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 focus:outline-none focus:ring-2 focus:ring-indigo-500/10 focus:border-indigo-500 transition-all"
                            />
                        </div>
                    )}
                </div>

                {/* Telegram Notifications */}
                <div className="bg-white border border-stone-200 shadow-sm rounded-xl p-6 space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                            <div className="p-1.5 bg-sky-50 rounded-lg border border-sky-100">
                                <Send size={15} className="text-sky-600" />
                            </div>
                            <div>
                                <h2 className="text-xs font-bold text-stone-500 uppercase tracking-widest">Telegram Notifications</h2>
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={() => setNotifyTelegramEnabled(!notifyTelegramEnabled)}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-all duration-300 focus:outline-none ${notifyTelegramEnabled ? "bg-sky-600" : "bg-stone-200"}`}
                        >
                            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-md transition-all duration-300 ${notifyTelegramEnabled ? "translate-x-6" : "translate-x-1"}`} />
                        </button>
                    </div>

                    {notifyTelegramEnabled && (
                        <div className="animate-fade-in pt-1">
                            <label className="block text-sm font-medium text-stone-700 mb-1.5 flex items-center gap-1.5">
                                <Send size={14} className="text-stone-400" />
                                Telegram Chat ID *
                            </label>
                            <input
                                type="text"
                                value={notifyTelegramChatId}
                                onChange={(e) => setNotifyTelegramChatId(e.target.value)}
                                required={notifyTelegramEnabled}
                                className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 focus:outline-none focus:ring-2 focus:ring-sky-500/10 focus:border-sky-500 transition-all"
                            />
                        </div>
                    )}
                </div>

                {/* Submit */}
                <div className="flex items-center justify-end gap-3 pb-6">
                    <button
                        type="button"
                        onClick={() => router.back()}
                        className="px-4 py-2 rounded-lg border border-stone-200 text-stone-500 hover:bg-stone-50 transition-colors font-medium"
                    >
                        Cancel
                    </button>
                    <button
                        type="submit"
                        disabled={saving}
                        className="flex items-center gap-2 px-6 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-semibold shadow-lg shadow-violet-200 transition-all active:scale-[0.98] disabled:opacity-60"
                    >
                        {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                        {saving ? "Saving..." : "Save Changes"}
                    </button>
                </div>
            </form>
        </div>
    );
}
