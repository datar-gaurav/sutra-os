"use client";

import { useEffect, useState } from "react";
import {
    Zap, Plus, X, Check, Loader2, Trash2, Edit3,
    Globe, Clock, MousePointer, Copy, Play,
    AlertCircle, CheckCircle2,
} from "lucide-react";
import { agentsApi, triggersApi, type Agent, type AgentTrigger, type TriggerType } from "@/lib/api";

// ─── Helpers ─────────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TYPE_CONFIG: Record<TriggerType, { label: string; icon: React.ReactNode; color: string }> = {
    webhook:  { label: "Webhook",  icon: <Globe className="w-4 h-4" />,         color: "text-blue-600 bg-blue-50 border-blue-200" },
    schedule: { label: "Schedule", icon: <Clock className="w-4 h-4" />,         color: "text-violet-600 bg-violet-50 border-violet-200" },
    manual:   { label: "Manual",   icon: <MousePointer className="w-4 h-4" />, color: "text-stone-600 bg-stone-50 border-stone-200" },
};

function fmtDate(iso: string | null) {
    if (!iso) return "Never";
    return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// ─── Trigger Modal ────────────────────────────────────────────────────────────
function TriggerModal({
    trigger,
    agents,
    defaultAgentId,
    onClose,
    onSave,
}: {
    trigger?: AgentTrigger | null;
    agents: Agent[];
    defaultAgentId?: string;
    onClose: () => void;
    onSave: (data: Partial<AgentTrigger>) => Promise<void>;
}) {
    const [agentId, setAgentId] = useState(trigger?.agent_id || defaultAgentId || "");
    const [name, setName] = useState(trigger?.name || "");
    const [description, setDescription] = useState(trigger?.description || "");
    const [type, setType] = useState<TriggerType>(trigger?.trigger_type || "manual");
    const [cron, setCron] = useState(trigger?.cron_expression || "0 9 * * 1");
    const [prompt, setPrompt] = useState(
        trigger?.prompt_template ||
        "You have been triggered. Review your goals and in-progress tasks, then produce a brief status report and propose your next action."
    );
    const [saving, setSaving] = useState(false);

    async function handleSave() {
        if (!name || !agentId) return;
        setSaving(true);
        try {
            await onSave({
                agent_id: agentId,
                name,
                description: description || undefined,
                trigger_type: type,
                cron_expression: type === "schedule" ? cron : undefined,
                prompt_template: prompt,
            });
            onClose();
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between mb-5">
                    <h2 className="text-lg font-semibold text-stone-900">{trigger ? "Edit Trigger" : "New Trigger"}</h2>
                    <button onClick={onClose} className="p-1.5 hover:bg-stone-100 rounded-lg"><X className="w-4 h-4" /></button>
                </div>

                <div className="space-y-4">
                    {!trigger && (
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Agent *</label>
                            <select className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" value={agentId} onChange={e => setAgentId(e.target.value)}>
                                <option value="">Select agent...</option>
                                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                            </select>
                        </div>
                    )}

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Name *</label>
                        <input className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" value={name} onChange={e => setName(e.target.value)} placeholder="Daily Morning Check-in" />
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Trigger Type</label>
                        <div className="flex gap-2">
                            {(Object.keys(TYPE_CONFIG) as TriggerType[]).map(t => (
                                <button
                                    key={t}
                                    onClick={() => setType(t)}
                                    className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-medium rounded-lg border transition-all ${type === t ? TYPE_CONFIG[t].color + " ring-1 ring-offset-1 ring-current" : "border-stone-200 text-stone-500 hover:bg-stone-50"}`}
                                >
                                    {TYPE_CONFIG[t].icon}{TYPE_CONFIG[t].label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {type === "schedule" && (
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Cron Expression</label>
                            <input
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={cron}
                                onChange={e => setCron(e.target.value)}
                                placeholder="0 9 * * 1"
                            />
                            <p className="text-[10px] text-stone-400 mt-1">Format: minute hour day month weekday (e.g. "0 9 * * 1" = Mon 9am)</p>
                        </div>
                    )}

                    {type === "webhook" && (
                        <div className="bg-blue-50 border border-blue-100 rounded-lg px-3 py-2 text-xs text-blue-700">
                            A unique webhook URL will be generated. Use <code className="font-mono">{"{payload}"}</code> in the prompt template to include the request body.
                        </div>
                    )}

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Prompt Template</label>
                        <textarea
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 resize-none h-28 font-mono"
                            value={prompt}
                            onChange={e => setPrompt(e.target.value)}
                            placeholder="What should the agent do when triggered?"
                        />
                        <p className="text-[10px] text-stone-400 mt-1">Use <code className="font-mono">{"{payload}"}</code> to include incoming webhook data.</p>
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Description (optional)</label>
                        <input className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" value={description} onChange={e => setDescription(e.target.value)} placeholder="What does this trigger do?" />
                    </div>
                </div>

                <div className="flex gap-3 mt-6">
                    <button onClick={onClose} className="flex-1 py-2 border border-stone-200 rounded-lg text-sm text-stone-600 hover:bg-stone-50">Cancel</button>
                    <button onClick={handleSave} disabled={!name || !agentId || saving} className="flex-1 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50 flex items-center justify-center gap-2">
                        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                        {trigger ? "Save" : "Create Trigger"}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Trigger Card ─────────────────────────────────────────────────────────────
function TriggerCard({
    trigger,
    agentName,
    onEdit,
    onDelete,
    onFire,
}: {
    trigger: AgentTrigger;
    agentName: string;
    onEdit: () => void;
    onDelete: () => void;
    onFire: () => Promise<void>;
}) {
    const [firing, setFiring] = useState(false);
    const [copied, setCopied] = useState(false);
    const cfg = TYPE_CONFIG[trigger.trigger_type];
    const webhookUrl = `${API_BASE}/api/public/triggers/webhook/${trigger.webhook_token}`;

    async function handleFire() {
        setFiring(true);
        await onFire();
        setTimeout(() => setFiring(false), 3000);
    }

    function copyWebhook() {
        navigator.clipboard.writeText(webhookUrl);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }

    return (
        <div className={`bg-white border rounded-xl shadow-sm p-4 ${trigger.is_active ? "border-stone-200" : "border-stone-100 opacity-60"}`}>
            <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                    <div className={`shrink-0 p-2 rounded-lg border ${cfg.color}`}>
                        {cfg.icon}
                    </div>
                    <div className="min-w-0">
                        <h3 className="font-semibold text-stone-800 text-sm">{trigger.name}</h3>
                        <p className="text-[10px] text-stone-400 mt-0.5">{agentName} · {cfg.label}</p>
                        {trigger.description && <p className="text-xs text-stone-500 mt-1">{trigger.description}</p>}
                        {trigger.trigger_type === "schedule" && trigger.cron_expression && (
                            <p className="text-[10px] font-mono text-stone-400 mt-1">⏱ {trigger.cron_expression}</p>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                    <button
                        onClick={handleFire}
                        disabled={firing}
                        title="Fire now"
                        className="p-1.5 text-stone-400 hover:text-green-600 hover:bg-green-50 rounded-lg border border-transparent hover:border-green-200 transition-all"
                    >
                        {firing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    </button>
                    <button onClick={onEdit} className="p-1.5 text-stone-400 hover:text-stone-600 hover:bg-stone-100 rounded-lg"><Edit3 className="w-4 h-4" /></button>
                    <button onClick={onDelete} className="p-1.5 text-stone-400 hover:text-red-500 hover:bg-red-50 rounded-lg"><Trash2 className="w-4 h-4" /></button>
                </div>
            </div>

            {/* Webhook URL */}
            {trigger.trigger_type === "webhook" && (
                <div className="mt-3 flex items-center gap-2 bg-stone-50 rounded-lg px-3 py-2">
                    <code className="text-[10px] text-stone-500 font-mono flex-1 truncate">{webhookUrl}</code>
                    <button onClick={copyWebhook} className="shrink-0 text-stone-400 hover:text-stone-700">
                        {copied ? <CheckCircle2 className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                </div>
            )}

            {/* Stats */}
            <div className="mt-3 flex items-center gap-4 text-[10px] text-stone-400">
                <span>Fired: <strong className="text-stone-600">{trigger.fire_count}</strong>×</span>
                <span>Last: <strong className="text-stone-600">{fmtDate(trigger.last_fired_at)}</strong></span>
                {trigger.last_error && (
                    <span className="flex items-center gap-1 text-red-400">
                        <AlertCircle className="w-3 h-3" /> Error
                    </span>
                )}
            </div>

            {/* Last output */}
            {trigger.last_output && (
                <div className="mt-2 bg-stone-900 text-stone-300 text-[10px] font-mono rounded-lg px-3 py-2 max-h-16 overflow-hidden leading-relaxed line-clamp-3">
                    {trigger.last_output}
                </div>
            )}
        </div>
    );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function TriggersPage() {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [triggers, setTriggers] = useState<AgentTrigger[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedAgent, setSelectedAgent] = useState("");
    const [modal, setModal] = useState<{ open: boolean; trigger?: AgentTrigger | null }>({ open: false });

    async function loadAll() {
        setLoading(true);
        try {
            const [a, t] = await Promise.all([agentsApi.list(), triggersApi.list(selectedAgent || undefined)]);
            setAgents(a);
            setTriggers(t);
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => { loadAll(); }, [selectedAgent]);

    const agentMap = Object.fromEntries(agents.map(a => [a.id, a.name]));

    async function handleSave(data: Partial<AgentTrigger>) {
        if (modal.trigger) {
            const updated = await triggersApi.update(modal.trigger.id, data);
            setTriggers(prev => prev.map(t => t.id === updated.id ? updated : t));
        } else {
            const created = await triggersApi.create(data);
            setTriggers(prev => [created, ...prev]);
        }
    }

    async function handleDelete(id: string) {
        if (!confirm("Delete this trigger?")) return;
        await triggersApi.delete(id);
        setTriggers(prev => prev.filter(t => t.id !== id));
    }

    async function handleFire(trigger: AgentTrigger) {
        await triggersApi.fire(trigger.id);
        // Refresh after a delay
        setTimeout(async () => {
            const t = await triggersApi.list(selectedAgent || undefined);
            setTriggers(t);
        }, 5000);
    }

    if (loading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="w-6 h-6 animate-spin text-stone-600" /></div>;
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-6 py-4 border-b border-stone-200 bg-white flex items-center justify-between gap-4">
                <div>
                    <h1 className="text-xl font-semibold text-stone-900 flex items-center gap-2">
                        <Zap className="w-5 h-5 text-stone-600" />
                        Event Triggers
                    </h1>
                    <p className="text-sm text-stone-500">Webhook, scheduled, and manual triggers for proactive agent behavior</p>
                </div>
                <div className="flex items-center gap-2">
                    <select
                        className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                        value={selectedAgent}
                        onChange={e => setSelectedAgent(e.target.value)}
                    >
                        <option value="">All agents</option>
                        {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </select>
                    <button
                        onClick={() => setModal({ open: true, trigger: null })}
                        className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700"
                    >
                        <Plus className="w-4 h-4" /> New Trigger
                    </button>
                </div>
            </div>

            {/* Type legend */}
            <div className="px-6 py-3 border-b border-stone-100 bg-white flex gap-4">
                {(Object.entries(TYPE_CONFIG) as [TriggerType, typeof TYPE_CONFIG[TriggerType]][]).map(([k, v]) => (
                    <div key={k} className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${v.color}`}>
                        {v.icon}{v.label}
                    </div>
                ))}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
                <div className="max-w-3xl space-y-4">
                    {triggers.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-20 text-stone-400">
                            <Zap className="w-14 h-14 mb-3 opacity-20" />
                            <p className="text-sm font-medium">No triggers yet</p>
                            <p className="text-xs mt-1">Create webhook, schedule, or manual triggers to activate agents proactively</p>
                            <button onClick={() => setModal({ open: true })} className="mt-4 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700">
                                Create First Trigger
                            </button>
                        </div>
                    ) : (
                        triggers.map(trigger => (
                            <TriggerCard
                                key={trigger.id}
                                trigger={trigger}
                                agentName={agentMap[trigger.agent_id] || trigger.agent_id}
                                onEdit={() => setModal({ open: true, trigger })}
                                onDelete={() => handleDelete(trigger.id)}
                                onFire={() => handleFire(trigger)}
                            />
                        ))
                    )}
                </div>
            </div>

            {modal.open && (
                <TriggerModal
                    trigger={modal.trigger}
                    agents={agents}
                    defaultAgentId={selectedAgent}
                    onClose={() => setModal({ open: false })}
                    onSave={handleSave}
                />
            )}
        </div>
    );
}
