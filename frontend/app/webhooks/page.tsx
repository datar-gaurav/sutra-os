"use client";

import { useState, useEffect } from "react";
import {
    Webhook,
    Plus,
    Trash2,
    Edit2,
    Play,
    RefreshCw,
    CheckCircle,
    XCircle,
    Clock,
    ChevronDown,
    ChevronRight,
    Eye,
    EyeOff,
    Loader2,
    AlertCircle,
    X,
    Copy,
    Check,
    ArrowDownToLine,
    ArrowUpFromLine,
    Terminal,
} from "lucide-react";
import {
    webhooksApi,
    triggersApi,
    agentsApi,
    WebhookSubscription,
    WebhookDelivery,
    Agent,
    AgentTrigger,
} from "@/lib/api";

type Tab = "inbound" | "outbound" | "deliveries";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STATUS_STYLES: Record<string, string> = {
    delivered: "bg-green-50 text-green-700 border-green-200",
    failed: "bg-red-50 text-red-700 border-red-200",
    pending: "bg-yellow-50 text-yellow-700 border-yellow-200",
};

const STATUS_ICON: Record<string, React.ReactNode> = {
    delivered: <CheckCircle className="w-3.5 h-3.5" />,
    failed: <XCircle className="w-3.5 h-3.5" />,
    pending: <Clock className="w-3.5 h-3.5" />,
};

function fmtDate(iso: string | null | undefined) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// ─── Copy button ──────────────────────────────────────────────────────────────

function CopyButton({ text, className = "" }: { text: string; className?: string }) {
    const [copied, setCopied] = useState(false);
    return (
        <button
            type="button"
            onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
            className={`shrink-0 text-gray-400 hover:text-stone-700 transition-colors ${className}`}
            title="Copy"
        >
            {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
        </button>
    );
}

// ─── Inbound webhook form ─────────────────────────────────────────────────────

interface InboundFormProps {
    initial?: AgentTrigger;
    agents: Agent[];
    onSave: (data: Partial<AgentTrigger>) => Promise<void>;
    onCancel: () => void;
}

function InboundForm({ initial, agents, onSave, onCancel }: InboundFormProps) {
    const [agentId, setAgentId] = useState(initial?.agent_id ?? "");
    const [name, setName] = useState(initial?.name ?? "");
    const [description, setDescription] = useState(initial?.description ?? "");
    const [prompt, setPrompt] = useState(
        initial?.prompt_template ??
        "An external system has sent you the following data:\n\n{payload}\n\nReview this information, take any necessary action, and summarise what you did."
    );
    const [isActive, setIsActive] = useState(initial?.is_active ?? true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (!agentId || !name) return;
        setSaving(true);
        setError("");
        try {
            await onSave({
                agent_id: agentId,
                name,
                description: description || undefined,
                trigger_type: "webhook",
                prompt_template: prompt,
                is_active: isActive,
            });
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setSaving(false);
        }
    }

    return (
        <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
                <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                    <AlertCircle className="w-4 h-4 shrink-0" />{error}
                </div>
            )}

            <div className="grid grid-cols-2 gap-4">
                {!initial && (
                    <div className="col-span-2">
                        <label className="block text-xs font-medium text-gray-600 mb-1">Agent *</label>
                        <select required value={agentId} onChange={e => setAgentId(e.target.value)}
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600">
                            <option value="">Select agent...</option>
                            {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                        </select>
                    </div>
                )}
                <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Name *</label>
                    <input required value={name} onChange={e => setName(e.target.value)}
                        placeholder="GitHub PR Opened"
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                </div>
                <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
                    <input value={description} onChange={e => setDescription(e.target.value)}
                        placeholder="Fires when a GitHub PR is opened"
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                </div>
            </div>

            <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                    Prompt Template *
                    <span className="ml-2 text-gray-400 font-normal normal-case">
                        Use <code className="font-mono bg-gray-100 px-1 rounded">{"{payload}"}</code> to embed the incoming JSON body
                    </span>
                </label>
                <textarea
                    required
                    value={prompt}
                    onChange={e => setPrompt(e.target.value)}
                    rows={5}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-stone-600 resize-y"
                />
            </div>

            <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} className="rounded" />
                Active
            </label>

            <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={onCancel}
                    className="px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
                <button type="submit" disabled={saving}
                    className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white text-sm rounded-lg hover:bg-stone-700 disabled:opacity-50">
                    {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                    {initial ? "Update" : "Create"} Webhook
                </button>
            </div>
        </form>
    );
}

// ─── Inbound webhook card ─────────────────────────────────────────────────────

function InboundCard({ trigger, agentName, onEdit, onDelete, onFire }: {
    trigger: AgentTrigger;
    agentName: string;
    onEdit: () => void;
    onDelete: () => void;
    onFire: () => Promise<void>;
}) {
    const [firing, setFiring] = useState(false);
    const [expanded, setExpanded] = useState(false);
    const url = `${API_BASE}/api/public/triggers/webhook/${trigger.webhook_token}`;

    async function handleFire() {
        setFiring(true);
        try { await onFire(); } finally { setTimeout(() => setFiring(false), 2000); }
    }

    const curlExample = `curl -X POST "${url}" \\
  -H "Content-Type: application/json" \\
  -d '{"event": "test", "data": {"key": "value"}}'`;

    return (
        <div className={`bg-white border rounded-xl ${trigger.is_active ? "border-gray-200" : "border-gray-100 opacity-60"}`}>
            {/* Header row */}
            <div className="flex items-start justify-between gap-4 p-4">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="font-medium text-gray-900 text-sm">{trigger.name}</span>
                        {!trigger.is_active && (
                            <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-500">Inactive</span>
                        )}
                        <span className="px-2 py-0.5 rounded-full text-xs bg-emerald-100 text-emerald-700 font-medium">
                            {agentName}
                        </span>
                    </div>
                    {trigger.description && (
                        <p className="text-xs text-gray-500 mb-2">{trigger.description}</p>
                    )}

                    {/* Webhook URL */}
                    <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 mt-2">
                        <code className="text-xs text-gray-600 font-mono flex-1 truncate">{url}</code>
                        <CopyButton text={url} />
                    </div>

                    {/* Stats */}
                    <div className="flex gap-4 mt-2 text-xs text-gray-400">
                        <span>Fired: <strong className="text-gray-600">{trigger.fire_count ?? 0}×</strong></span>
                        <span>Last: <strong className="text-gray-600">{fmtDate(trigger.last_fired_at)}</strong></span>
                        {trigger.last_error && (
                            <span className="text-red-400 flex items-center gap-1">
                                <XCircle className="w-3 h-3" /> Last run errored
                            </span>
                        )}
                    </div>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                    <button onClick={handleFire} disabled={firing} title="Test fire"
                        className="p-2 rounded-lg text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors">
                        {firing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                    </button>
                    <button onClick={() => setExpanded(e => !e)} title="Show setup instructions"
                        className="p-2 rounded-lg text-gray-400 hover:text-stone-700 hover:bg-stone-100 transition-colors">
                        <Terminal className="w-4 h-4" />
                    </button>
                    <button onClick={onEdit} title="Edit"
                        className="p-2 rounded-lg text-gray-400 hover:text-stone-700 hover:bg-stone-100 transition-colors">
                        <Edit2 className="w-4 h-4" />
                    </button>
                    <button onClick={onDelete} title="Delete"
                        className="p-2 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors">
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Setup panel */}
            {expanded && (
                <div className="border-t border-gray-100 p-4 space-y-4 bg-gray-50 rounded-b-xl">
                    {/* curl example */}
                    <div>
                        <div className="flex items-center justify-between mb-1">
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">curl example</p>
                            <CopyButton text={curlExample} />
                        </div>
                        <pre className="text-xs bg-gray-900 text-green-400 rounded-lg p-3 overflow-x-auto leading-relaxed">{curlExample}</pre>
                    </div>

                    {/* Prompt template */}
                    <div>
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Prompt template</p>
                        <pre className="text-xs bg-white border border-gray-200 rounded-lg p-3 whitespace-pre-wrap text-gray-600 leading-relaxed max-h-32 overflow-y-auto">
                            {trigger.prompt_template}
                        </pre>
                    </div>

                    {/* Last output */}
                    {trigger.last_output && (
                        <div>
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Last output</p>
                            <pre className="text-xs bg-white border border-gray-200 rounded-lg p-3 whitespace-pre-wrap text-gray-700 leading-relaxed max-h-32 overflow-y-auto">
                                {trigger.last_output}
                            </pre>
                        </div>
                    )}

                    {trigger.last_error && (
                        <div>
                            <p className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-1">Last error</p>
                            <pre className="text-xs bg-red-50 border border-red-200 rounded-lg p-3 whitespace-pre-wrap text-red-600 leading-relaxed max-h-24 overflow-y-auto">
                                {trigger.last_error}
                            </pre>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ─── Outbound subscription form ───────────────────────────────────────────────

interface SubFormProps {
    initial?: Partial<WebhookSubscription>;
    agents: Agent[];
    allEvents: string[];
    onSave: (data: Record<string, unknown>) => Promise<void>;
    onCancel: () => void;
}

function SubForm({ initial, agents, allEvents, onSave, onCancel }: SubFormProps) {
    const [name, setName] = useState(initial?.name ?? "");
    const [url, setUrl] = useState(initial?.url ?? "");
    const [secret, setSecret] = useState("");
    const [showSecret, setShowSecret] = useState(false);
    const [selectedEvents, setSelectedEvents] = useState<string[]>(initial?.events ?? ["*"]);
    const [agentId, setAgentId] = useState(initial?.agent_id ?? "");
    const [isActive, setIsActive] = useState(initial?.is_active ?? true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    const allSelected = selectedEvents.includes("*");

    function toggleEvent(ev: string) {
        if (ev === "*") { setSelectedEvents(["*"]); return; }
        setSelectedEvents(prev => {
            const without = prev.filter(e => e !== "*");
            return without.includes(ev) ? without.filter(e => e !== ev) : [...without, ev];
        });
    }

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setSaving(true);
        setError("");
        try {
            const data: Record<string, unknown> = { name, url, events: selectedEvents, is_active: isActive, agent_id: agentId || null };
            if (secret) data.secret = secret;
            await onSave(data);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setSaving(false);
        }
    }

    const nonWildcard = allEvents.filter(e => e !== "*");

    return (
        <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
                <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                    <AlertCircle className="w-4 h-4 shrink-0" />{error}
                </div>
            )}
            <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Name *</label>
                    <input required value={name} onChange={e => setName(e.target.value)}
                        placeholder="Zapier Task Notifications"
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                </div>
                <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Destination URL *</label>
                    <input required type="url" value={url} onChange={e => setUrl(e.target.value)}
                        placeholder="https://hooks.zapier.com/hooks/catch/..."
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-stone-600" />
                </div>
                <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                        Secret {initial ? "(leave blank to keep)" : "(optional)"}
                    </label>
                    <div className="relative">
                        <input type={showSecret ? "text" : "password"} value={secret}
                            onChange={e => setSecret(e.target.value)}
                            placeholder="HMAC-SHA256 signing secret"
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                        <button type="button" onClick={() => setShowSecret(s => !s)}
                            className="absolute right-2 top-2 text-gray-400 hover:text-gray-600">
                            {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                    </div>
                    <p className="text-xs text-gray-400 mt-1">Sent as <code className="font-mono">X-Sutra-Signature: sha256=…</code></p>
                </div>
                <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Agent scope</label>
                    <select value={agentId} onChange={e => setAgentId(e.target.value)}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600">
                        <option value="">All agents</option>
                        {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </select>
                </div>
            </div>

            <div>
                <label className="block text-xs font-medium text-gray-600 mb-2">Subscribe to events *</label>
                <div className="border border-gray-200 rounded-lg p-3 grid grid-cols-3 gap-2">
                    <label className="flex items-center gap-2 text-sm cursor-pointer col-span-3 font-medium text-stone-700">
                        <input type="checkbox" checked={allSelected} onChange={() => toggleEvent("*")} className="rounded" />
                        All events (*)
                    </label>
                    {nonWildcard.map(ev => (
                        <label key={ev} className="flex items-center gap-2 text-xs cursor-pointer text-gray-600">
                            <input type="checkbox" disabled={allSelected}
                                checked={allSelected || selectedEvents.includes(ev)}
                                onChange={() => toggleEvent(ev)} className="rounded" />
                            <code className="font-mono">{ev}</code>
                        </label>
                    ))}
                </div>
            </div>

            <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} className="rounded" />
                Active
            </label>

            <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={onCancel}
                    className="px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
                <button type="submit" disabled={saving || selectedEvents.length === 0}
                    className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white text-sm rounded-lg hover:bg-stone-700 disabled:opacity-50">
                    {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                    {initial ? "Update" : "Create"} Subscription
                </button>
            </div>
        </form>
    );
}

// ─── Delivery row ─────────────────────────────────────────────────────────────

function DeliveryRow({ delivery, subName, onRetry }: {
    delivery: WebhookDelivery;
    subName: string;
    onRetry: () => Promise<void>;
}) {
    const [expanded, setExpanded] = useState(false);
    const [retrying, setRetrying] = useState(false);

    async function handleRetry() {
        setRetrying(true);
        try { await onRetry(); } finally { setRetrying(false); }
    }

    const style = STATUS_STYLES[delivery.status] ?? STATUS_STYLES.pending;
    const icon = STATUS_ICON[delivery.status] ?? STATUS_ICON.pending;

    return (
        <>
            <tr className="hover:bg-gray-50 transition-colors cursor-pointer" onClick={() => setExpanded(e => !e)}>
                <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${style}`}>
                        {icon}{delivery.status}
                    </span>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-600">{delivery.event_type}</td>
                <td className="px-4 py-3 text-xs text-gray-500">{subName}</td>
                <td className="px-4 py-3 text-xs text-gray-500">{fmtDate(delivery.created_at)}</td>
                <td className="px-4 py-3 text-xs">
                    {delivery.response_status
                        ? <span className={delivery.response_status < 300 ? "text-green-600" : "text-red-600"}>HTTP {delivery.response_status}</span>
                        : "—"}
                </td>
                <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                        {delivery.status === "failed" && (
                            <button onClick={e => { e.stopPropagation(); handleRetry(); }} disabled={retrying}
                                className="p-1.5 rounded text-gray-400 hover:text-stone-700 hover:bg-stone-100 transition-colors" title="Retry">
                                {retrying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                            </button>
                        )}
                        {expanded ? <ChevronDown className="w-3.5 h-3.5 text-gray-400" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-400" />}
                    </div>
                </td>
            </tr>
            {expanded && (
                <tr className="bg-gray-50">
                    <td colSpan={6} className="px-4 pb-3 pt-0">
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <p className="text-xs font-semibold text-gray-500 mb-1">Payload sent</p>
                                <pre className="text-xs bg-gray-900 text-green-400 rounded-lg p-3 overflow-x-auto max-h-40">
                                    {JSON.stringify(delivery.payload, null, 2)}
                                </pre>
                            </div>
                            <div>
                                <p className="text-xs font-semibold text-gray-500 mb-1">Response</p>
                                <pre className="text-xs bg-gray-900 text-gray-300 rounded-lg p-3 overflow-x-auto max-h-40">
                                    {delivery.error || delivery.response_body || "—"}
                                </pre>
                            </div>
                        </div>
                    </td>
                </tr>
            )}
        </>
    );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function WebhooksPage() {
    const [tab, setTab] = useState<Tab>("inbound");
    const [agents, setAgents] = useState<Agent[]>([]);
    const [allEvents, setAllEvents] = useState<string[]>([]);

    // Inbound
    const [inbound, setInbound] = useState<AgentTrigger[]>([]);
    const [inboundLoading, setInboundLoading] = useState(false);
    const [showInboundForm, setShowInboundForm] = useState(false);
    const [editingInbound, setEditingInbound] = useState<AgentTrigger | null>(null);

    // Outbound subscriptions
    const [subs, setSubs] = useState<WebhookSubscription[]>([]);
    const [subsLoading, setSubsLoading] = useState(false);
    const [showSubForm, setShowSubForm] = useState(false);
    const [editingSub, setEditingSub] = useState<WebhookSubscription | null>(null);
    const [testing, setTesting] = useState<string | null>(null);
    const [testMsg, setTestMsg] = useState<string | null>(null);

    // Deliveries
    const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
    const [dlLoading, setDlLoading] = useState(false);
    const [dlSubFilter, setDlSubFilter] = useState("");
    const [dlStatusFilter, setDlStatusFilter] = useState("");

    useEffect(() => {
        agentsApi.list().then(setAgents).catch(() => {});
        webhooksApi.listEvents().then(r => setAllEvents(r.events)).catch(() => {});
    }, []);

    // Load inbound
    useEffect(() => {
        if (tab !== "inbound") return;
        setInboundLoading(true);
        triggersApi.list().then(all => setInbound(all.filter(t => t.trigger_type === "webhook")))
            .catch(() => {}).finally(() => setInboundLoading(false));
    }, [tab]);

    // Load outbound
    useEffect(() => {
        if (tab !== "outbound") return;
        setSubsLoading(true);
        webhooksApi.listSubscriptions().then(setSubs).catch(() => {}).finally(() => setSubsLoading(false));
    }, [tab]);

    // Load deliveries
    useEffect(() => {
        if (tab !== "deliveries") return;
        setDlLoading(true);
        webhooksApi.listDeliveries(dlSubFilter || undefined, dlStatusFilter || undefined, 100)
            .then(setDeliveries).catch(() => {}).finally(() => setDlLoading(false));
    }, [tab, dlSubFilter, dlStatusFilter]);

    // Inbound handlers
    async function handleSaveInbound(data: Partial<AgentTrigger>) {
        if (editingInbound) {
            const updated = await triggersApi.update(editingInbound.id, data);
            setInbound(t => t.map(x => x.id === updated.id ? updated : x));
        } else {
            const created = await triggersApi.create(data);
            setInbound(t => [created, ...t]);
        }
        setShowInboundForm(false);
        setEditingInbound(null);
    }

    async function handleDeleteInbound(id: string) {
        if (!confirm("Delete this inbound webhook?")) return;
        await triggersApi.delete(id);
        setInbound(t => t.filter(x => x.id !== id));
    }

    async function handleFireInbound(trigger: AgentTrigger) {
        await triggersApi.fire(trigger.id);
        setTimeout(async () => {
            const all = await triggersApi.list();
            setInbound(all.filter(t => t.trigger_type === "webhook"));
        }, 3000);
    }

    // Outbound handlers
    async function handleSaveSub(data: Record<string, unknown>) {
        if (editingSub) {
            const updated = await webhooksApi.updateSubscription(editingSub.id, data as Parameters<typeof webhooksApi.updateSubscription>[1]);
            setSubs(s => s.map(x => x.id === updated.id ? updated : x));
        } else {
            const created = await webhooksApi.createSubscription(data as Parameters<typeof webhooksApi.createSubscription>[0]);
            setSubs(s => [created, ...s]);
        }
        setShowSubForm(false);
        setEditingSub(null);
    }

    async function handleDeleteSub(id: string) {
        if (!confirm("Delete this subscription and all delivery history?")) return;
        await webhooksApi.deleteSubscription(id);
        setSubs(s => s.filter(x => x.id !== id));
    }

    async function handleTestSub(id: string) {
        setTesting(id);
        setTestMsg(null);
        try {
            const r = await webhooksApi.testSubscription(id);
            setTestMsg(r.message);
        } catch (err: unknown) {
            setTestMsg(`Error: ${err instanceof Error ? err.message : String(err)}`);
        } finally {
            setTimeout(() => setTesting(null), 2000);
        }
    }

    function agentName(id: string | null | undefined) {
        if (!id) return "All agents";
        return agents.find(a => a.id === id)?.name ?? id;
    }

    function subName(id: string) {
        return subs.find(s => s.id === id)?.name ?? id;
    }

    const tabs = [
        { id: "inbound" as Tab, label: "Inbound", icon: <ArrowDownToLine className="w-4 h-4" />, count: inbound.length },
        { id: "outbound" as Tab, label: "Outbound", icon: <ArrowUpFromLine className="w-4 h-4" />, count: subs.length },
        { id: "deliveries" as Tab, label: "Delivery Logs", icon: <Clock className="w-4 h-4" />, count: null },
    ];

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="border-b border-gray-100 bg-white px-6 py-4">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-indigo-50 rounded-lg flex items-center justify-center">
                        <Webhook className="w-5 h-5 text-indigo-600" />
                    </div>
                    <div>
                        <h1 className="text-lg font-semibold text-gray-900">Webhooks</h1>
                        <p className="text-xs text-gray-500">
                            Inbound: external systems trigger agents &nbsp;·&nbsp; Outbound: Sutra POSTs events to external URLs
                        </p>
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="border-b border-gray-100 bg-white px-6">
                <div className="flex gap-1">
                    {tabs.map(({ id, label, icon, count }) => (
                        <button key={id} onClick={() => setTab(id)}
                            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                                tab === id ? "border-stone-600 text-stone-700" : "border-transparent text-gray-500 hover:text-gray-700"
                            }`}>
                            {icon}{label}
                            {count != null && count > 0 && (
                                <span className="px-1.5 py-0.5 rounded-full text-xs bg-gray-100 text-gray-600">{count}</span>
                            )}
                        </button>
                    ))}
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6 bg-gray-50">

                {/* ── INBOUND ── */}
                {tab === "inbound" && (
                    <div className="space-y-4 max-w-4xl">
                        <div className="flex items-start justify-between gap-4">
                            <div className="space-y-1">
                                <p className="text-sm text-gray-600">
                                    Each inbound webhook has a unique URL. External systems POST JSON to it, and the target agent runs the configured prompt with <code className="font-mono text-xs bg-gray-100 px-1 rounded">{"{payload}"}</code> replaced by the request body.
                                </p>
                            </div>
                            <button
                                onClick={() => { setEditingInbound(null); setShowInboundForm(true); }}
                                className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white text-sm rounded-lg hover:bg-stone-700 shrink-0"
                            >
                                <Plus className="w-4 h-4" /> New Inbound Webhook
                            </button>
                        </div>

                        {showInboundForm && (
                            <div className="bg-white border border-gray-200 rounded-xl p-6">
                                <h3 className="text-sm font-semibold text-gray-800 mb-4">
                                    {editingInbound ? "Edit Inbound Webhook" : "New Inbound Webhook"}
                                </h3>
                                <InboundForm
                                    initial={editingInbound ?? undefined}
                                    agents={agents}
                                    onSave={handleSaveInbound}
                                    onCancel={() => { setShowInboundForm(false); setEditingInbound(null); }}
                                />
                            </div>
                        )}

                        {inboundLoading ? (
                            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
                        ) : inbound.length === 0 ? (
                            <div className="bg-white border border-dashed border-gray-200 rounded-xl p-12 text-center">
                                <ArrowDownToLine className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                                <p className="text-sm text-gray-500">No inbound webhooks yet.</p>
                                <p className="text-xs text-gray-400 mt-1">Create one to let external systems (GitHub, Stripe, Zapier…) trigger an agent.</p>
                                <button onClick={() => setShowInboundForm(true)}
                                    className="mt-4 px-4 py-2 bg-stone-700 text-white text-sm rounded-lg hover:bg-stone-700">
                                    Create First Webhook
                                </button>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {inbound.map(trigger => (
                                    <InboundCard
                                        key={trigger.id}
                                        trigger={trigger}
                                        agentName={agentName(trigger.agent_id)}
                                        onEdit={() => { setEditingInbound(trigger); setShowInboundForm(true); }}
                                        onDelete={() => handleDeleteInbound(trigger.id)}
                                        onFire={() => handleFireInbound(trigger)}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── OUTBOUND ── */}
                {tab === "outbound" && (
                    <div className="space-y-4 max-w-4xl">
                        <div className="flex items-center justify-between">
                            <p className="text-sm text-gray-600">
                                When Sutra emits an event, it POSTs the JSON payload to all matching active subscriptions.
                            </p>
                            <button
                                onClick={() => { setEditingSub(null); setShowSubForm(true); }}
                                className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white text-sm rounded-lg hover:bg-stone-700"
                            >
                                <Plus className="w-4 h-4" /> New Subscription
                            </button>
                        </div>

                        {testMsg && (
                            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-700 flex items-center justify-between">
                                <span>{testMsg}</span>
                                <button onClick={() => setTestMsg(null)}><X className="w-4 h-4" /></button>
                            </div>
                        )}

                        {showSubForm && (
                            <div className="bg-white border border-gray-200 rounded-xl p-6">
                                <h3 className="text-sm font-semibold text-gray-800 mb-4">
                                    {editingSub ? "Edit Subscription" : "New Outbound Subscription"}
                                </h3>
                                <SubForm
                                    initial={editingSub ?? undefined}
                                    agents={agents}
                                    allEvents={allEvents}
                                    onSave={handleSaveSub}
                                    onCancel={() => { setShowSubForm(false); setEditingSub(null); }}
                                />
                            </div>
                        )}

                        {subsLoading ? (
                            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
                        ) : subs.length === 0 ? (
                            <div className="bg-white border border-dashed border-gray-200 rounded-xl p-12 text-center">
                                <ArrowUpFromLine className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                                <p className="text-sm text-gray-500">No outbound subscriptions yet.</p>
                                <p className="text-xs text-gray-400 mt-1">Create one to start forwarding Sutra events to external services.</p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {subs.map(sub => (
                                    <div key={sub.id} className={`bg-white border rounded-xl p-4 ${sub.is_active ? "border-gray-200" : "border-gray-100 opacity-60"}`}>
                                        <div className="flex items-start justify-between gap-4">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap mb-1">
                                                    <span className="font-medium text-gray-900 text-sm">{sub.name}</span>
                                                    {!sub.is_active && <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-500">Inactive</span>}
                                                    <span className="px-2 py-0.5 rounded-full text-xs bg-indigo-100 text-indigo-700 font-medium">
                                                        {agentName(sub.agent_id)}
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 mt-2 mb-2">
                                                    <code className="text-xs text-gray-600 font-mono flex-1 truncate">{sub.url}</code>
                                                    <CopyButton text={sub.url} />
                                                </div>
                                                <div className="flex flex-wrap gap-1 mb-2">
                                                    {(sub.events ?? []).map(ev => (
                                                        <code key={ev} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-mono">{ev}</code>
                                                    ))}
                                                </div>
                                                <div className="flex gap-4 text-xs text-gray-400">
                                                    <span>Delivered: <strong className="text-gray-600">{sub.delivery_count}</strong></span>
                                                    <span>Failed: <strong className={sub.failure_count > 0 ? "text-red-500" : "text-gray-600"}>{sub.failure_count}</strong></span>
                                                    <span>Last: <strong className="text-gray-600">{fmtDate(sub.last_delivery_at)}</strong></span>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-1 shrink-0">
                                                <button onClick={() => handleTestSub(sub.id)} disabled={testing === sub.id}
                                                    className="p-2 rounded-lg text-gray-400 hover:text-stone-700 hover:bg-stone-100 transition-colors" title="Send test event">
                                                    {testing === sub.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                                                </button>
                                                <button onClick={() => { setEditingSub(sub); setShowSubForm(true); }}
                                                    className="p-2 rounded-lg text-gray-400 hover:text-stone-700 hover:bg-stone-100 transition-colors" title="Edit">
                                                    <Edit2 className="w-4 h-4" />
                                                </button>
                                                <button onClick={() => handleDeleteSub(sub.id)}
                                                    className="p-2 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors" title="Delete">
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── DELIVERY LOGS ── */}
                {tab === "deliveries" && (
                    <div className="space-y-4 max-w-5xl">
                        <div className="flex items-center gap-3">
                            <select value={dlSubFilter} onChange={e => setDlSubFilter(e.target.value)}
                                className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600">
                                <option value="">All subscriptions</option>
                                {subs.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                            </select>
                            <select value={dlStatusFilter} onChange={e => setDlStatusFilter(e.target.value)}
                                className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600">
                                <option value="">All statuses</option>
                                <option value="delivered">Delivered</option>
                                <option value="failed">Failed</option>
                                <option value="pending">Pending</option>
                            </select>
                            <button onClick={() => {
                                setDlLoading(true);
                                webhooksApi.listDeliveries(dlSubFilter || undefined, dlStatusFilter || undefined, 100)
                                    .then(setDeliveries).catch(() => {}).finally(() => setDlLoading(false));
                            }} className="p-2 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 transition-colors" title="Refresh">
                                <RefreshCw className="w-4 h-4" />
                            </button>
                        </div>

                        {dlLoading ? (
                            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
                        ) : deliveries.length === 0 ? (
                            <div className="bg-white border border-dashed border-gray-200 rounded-xl p-12 text-center">
                                <Clock className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                                <p className="text-sm text-gray-500">No outbound delivery logs yet.</p>
                            </div>
                        ) : (
                            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                                <table className="w-full text-sm">
                                    <thead className="bg-gray-50 border-b border-gray-100">
                                        <tr>
                                            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Status</th>
                                            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Event</th>
                                            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Subscription</th>
                                            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Time</th>
                                            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Response</th>
                                            <th className="px-4 py-3"></th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-50">
                                        {deliveries.map(d => (
                                            <DeliveryRow key={d.id} delivery={d} subName={subName(d.subscription_id)}
                                                onRetry={async () => {
                                                    await webhooksApi.retryDelivery(d.id);
                                                    setTimeout(() => {
                                                        webhooksApi.listDeliveries(dlSubFilter || undefined, dlStatusFilter || undefined, 100)
                                                            .then(setDeliveries).catch(() => {});
                                                    }, 2000);
                                                }} />
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
