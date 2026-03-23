"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
    Gauge,
    Plus,
    Trash2,
    Edit2,
    X,
    Loader2,
    AlertCircle,
    RefreshCw,
    Activity,
    Settings2,
    BarChart3,
    List,
    LayoutGrid,
    CloudDownload,
} from "lucide-react";
import { rateLimitsApi, llmsApi, type ModelRateLimit } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

interface RateLimitUsage {
    id: string;
    provider: string;
    model: string;
    label: string | null;
    limits: { rpm: number | null; rpd: number | null; tpm: number | null; tpd: number | null };
    current: { rpm: number; rpd: number; tpm: number; tpd: number };
}

type Tab = "config" | "usage";
type UsageView = "list" | "cards";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtNum(n: number | null | undefined): string {
    if (n == null) return "\u2014";
    return n.toLocaleString();
}

function pct(current: number, limit: number | null): number | null {
    if (!limit || limit <= 0) return null;
    return Math.min((current / limit) * 100, 100);
}

function barColor(p: number | null): string {
    if (p == null) return "bg-gray-200";
    if (p < 60) return "bg-emerald-500";
    if (p <= 85) return "bg-amber-400";
    return "bg-red-500";
}

function barTextColor(p: number | null): string {
    if (p == null) return "text-gray-400";
    if (p < 60) return "text-emerald-600";
    if (p <= 85) return "text-amber-600";
    return "text-red-600";
}

function maxUsagePct(u: RateLimitUsage): number {
    const pcts = [
        pct(u.current.rpm, u.limits.rpm),
        pct(u.current.rpd, u.limits.rpd),
        pct(u.current.tpm, u.limits.tpm),
        pct(u.current.tpd, u.limits.tpd),
    ].filter((v): v is number => v != null);
    return pcts.length ? Math.max(...pcts) : -1;
}

function UsageDot({ p }: { p: number | null }) {
    if (p == null) return <span className="w-2 h-2 rounded-full bg-gray-200 inline-block" />;
    const color = p < 60 ? "bg-emerald-500" : p <= 85 ? "bg-amber-400" : "bg-red-500";
    return <span className={`w-2 h-2 rounded-full ${color} inline-block`} />;
}

function MiniBar({ current, limit }: { current: number; limit: number | null }) {
    const p = pct(current, limit);
    return (
        <div className="flex items-center gap-2">
            <span className={`text-xs tabular-nums font-medium ${barTextColor(p)}`}>
                {fmtNum(current)}<span className="text-gray-300">/</span>{fmtNum(limit)}
            </span>
            {p != null && (
                <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${barColor(p)}`} style={{ width: `${p}%` }} />
                </div>
            )}
        </div>
    );
}

// ─── Form Modal ──────────────────────────────────────────────────────────────

interface FormModalProps {
    initial?: ModelRateLimit | null;
    onSave: (data: Partial<ModelRateLimit>) => Promise<void>;
    onClose: () => void;
}

const PROVIDERS = [
    { value: "openai", label: "OpenAI" },
    { value: "groq", label: "Groq" },
    { value: "google", label: "Google" },
    { value: "openrouter", label: "OpenRouter" },
    { value: "anthropic", label: "Anthropic" },
    { value: "ollama", label: "Ollama" },
    { value: "perplexity", label: "Perplexity" },
];

function FormModal({ initial, onSave, onClose }: FormModalProps) {
    const [form, setForm] = useState({
        provider: initial?.provider ?? "",
        model: initial?.model ?? "",
        label: initial?.label ?? "",
        requests_per_minute: initial?.requests_per_minute ?? "",
        requests_per_day: initial?.requests_per_day ?? "",
        tokens_per_minute: initial?.tokens_per_minute ?? "",
        tokens_per_day: initial?.tokens_per_day ?? "",
        refresh_interval_hours: initial?.refresh_interval_hours ?? 24,
    });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [availableModels, setAvailableModels] = useState<string[]>([]);
    const [loadingModels, setLoadingModels] = useState(false);
    const [modelSearch, setModelSearch] = useState("");

    const set = (k: string, v: unknown) => setForm(f => ({ ...f, [k]: v }));

    // Fetch models when provider changes
    useEffect(() => {
        if (!form.provider) {
            setAvailableModels([]);
            return;
        }
        setLoadingModels(true);
        setAvailableModels([]);

        const fetchModels = async () => {
            try {
                let models: string[] = [];
                switch (form.provider) {
                    case "groq": {
                        const res = await llmsApi.groqModels();
                        models = res.map(m => m.id);
                        break;
                    }
                    case "openrouter": {
                        const res = await llmsApi.openRouterModels();
                        models = res.map(m => m.id);
                        break;
                    }
                    case "google": {
                        const res = await llmsApi.googleModels();
                        models = res.map(m => m.id);
                        break;
                    }
                    case "ollama": {
                        const res = await llmsApi.ollamaModels();
                        models = res.map(m => m.name);
                        break;
                    }
                    case "perplexity": {
                        const res = await llmsApi.perplexityModels();
                        models = res.map(m => m.id);
                        break;
                    }
                    // openai and anthropic don't have dynamic model list endpoints
                    default:
                        break;
                }
                setAvailableModels(models);
            } catch {
                setAvailableModels([]);
            } finally {
                setLoadingModels(false);
            }
        };
        fetchModels();
    }, [form.provider]);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (!form.provider.trim() || !form.model.trim()) {
            setError("Provider and Model are required.");
            return;
        }
        setSaving(true);
        setError("");
        try {
            await onSave({
                provider: form.provider.trim(),
                model: form.model.trim(),
                label: form.label.trim() || null,
                requests_per_minute: form.requests_per_minute === "" ? null : Number(form.requests_per_minute),
                requests_per_day: form.requests_per_day === "" ? null : Number(form.requests_per_day),
                tokens_per_minute: form.tokens_per_minute === "" ? null : Number(form.tokens_per_minute),
                tokens_per_day: form.tokens_per_day === "" ? null : Number(form.tokens_per_day),
                refresh_interval_hours: Number(form.refresh_interval_hours) || 24,
            });
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <form
                onSubmit={handleSubmit}
                className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 space-y-4 relative"
            >
                <button
                    type="button"
                    onClick={onClose}
                    className="absolute top-4 right-4 text-gray-400 hover:text-gray-600"
                >
                    <X className="w-5 h-5" />
                </button>

                <h2 className="text-lg font-semibold text-gray-900">
                    {initial ? "Edit Rate Limit" : "Add Rate Limit"}
                </h2>

                {error && (
                    <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        {error}
                    </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Provider *</label>
                        <select
                            required
                            value={form.provider}
                            onChange={e => {
                                set("provider", e.target.value);
                                set("model", "");
                                setModelSearch("");
                            }}
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 bg-white"
                        >
                            <option value="">Select provider...</option>
                            {PROVIDERS.map(p => (
                                <option key={p.value} value={p.value}>{p.label}</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">
                            Model *
                            {loadingModels && <span className="ml-1 text-gray-400">(loading...)</span>}
                        </label>
                        {availableModels.length > 0 ? (
                            <div className="relative">
                                <input
                                    value={modelSearch || form.model}
                                    onChange={e => {
                                        setModelSearch(e.target.value);
                                        if (!e.target.value) set("model", "");
                                    }}
                                    placeholder="Search models..."
                                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                />
                                {modelSearch && (
                                    <div className="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg">
                                        {availableModels
                                            .filter(m => m.toLowerCase().includes(modelSearch.toLowerCase()))
                                            .slice(0, 20)
                                            .map(m => (
                                                <button
                                                    key={m}
                                                    type="button"
                                                    onClick={() => {
                                                        set("model", m);
                                                        setModelSearch("");
                                                    }}
                                                    className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 font-mono text-xs"
                                                >
                                                    {m}
                                                </button>
                                            ))}
                                        {availableModels.filter(m => m.toLowerCase().includes(modelSearch.toLowerCase())).length === 0 && (
                                            <div className="px-3 py-2 text-xs text-gray-400">No matching models</div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ) : (
                            <input
                                required
                                value={form.model}
                                onChange={e => set("model", e.target.value)}
                                placeholder={loadingModels ? "Loading models..." : form.provider ? "Type model name" : "Select provider first"}
                                disabled={loadingModels}
                                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 disabled:bg-gray-50 disabled:text-gray-400"
                            />
                        )}
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Label</label>
                        <input
                            value={form.label}
                            onChange={e => set("label", e.target.value)}
                            placeholder="Optional label"
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Refresh Interval (hrs)</label>
                        <input
                            type="number"
                            min={1}
                            value={form.refresh_interval_hours}
                            onChange={e => set("refresh_interval_hours", e.target.value)}
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                        />
                    </div>
                </div>

                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider pt-1">Limits</p>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Requests / Min (RPM)</label>
                        <input
                            type="number"
                            min={0}
                            value={form.requests_per_minute}
                            onChange={e => set("requests_per_minute", e.target.value)}
                            placeholder="No limit"
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Requests / Day (RPD)</label>
                        <input
                            type="number"
                            min={0}
                            value={form.requests_per_day}
                            onChange={e => set("requests_per_day", e.target.value)}
                            placeholder="No limit"
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Tokens / Min (TPM)</label>
                        <input
                            type="number"
                            min={0}
                            value={form.tokens_per_minute}
                            onChange={e => set("tokens_per_minute", e.target.value)}
                            placeholder="No limit"
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Tokens / Day (TPD)</label>
                        <input
                            type="number"
                            min={0}
                            value={form.tokens_per_day}
                            onChange={e => set("tokens_per_day", e.target.value)}
                            placeholder="No limit"
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                        />
                    </div>
                </div>

                <div className="flex justify-end gap-3 pt-2">
                    <button
                        type="button"
                        onClick={onClose}
                        className="px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50"
                    >
                        Cancel
                    </button>
                    <button
                        type="submit"
                        disabled={saving}
                        className="px-4 py-2 bg-stone-700 text-white rounded-lg text-sm hover:bg-stone-800 disabled:opacity-50 flex items-center gap-2"
                    >
                        {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                        {initial ? "Update" : "Create"}
                    </button>
                </div>
            </form>
        </div>
    );
}

// ─── Capacity Bar ────────────────────────────────────────────────────────────

function CapacityBar({ label, current, limit }: { label: string; current: number; limit: number | null }) {
    const p = pct(current, limit);
    return (
        <div className="space-y-1">
            <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">{label}</span>
                <span className={`font-medium ${barTextColor(p)}`}>
                    {fmtNum(current)} / {fmtNum(limit)}
                    {p != null && <span className="ml-1 text-[10px]">({p.toFixed(0)}%)</span>}
                </span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                {p != null && (
                    <div
                        className={`h-full rounded-full transition-all duration-500 ${barColor(p)}`}
                        style={{ width: `${p}%` }}
                    />
                )}
            </div>
        </div>
    );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function RateLimitsPage() {
    const [tab, setTab] = useState<Tab>("config");

    // Config state
    const [limits, setLimits] = useState<ModelRateLimit[]>([]);
    const [loading, setLoading] = useState(false);
    const [showModal, setShowModal] = useState(false);
    const [editing, setEditing] = useState<ModelRateLimit | null>(null);

    // Usage state
    const [usage, setUsage] = useState<RateLimitUsage[]>([]);
    const [usageLoading, setUsageLoading] = useState(false);
    const [usageView, setUsageView] = useState<UsageView>("list");
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Sync state
    const [syncing, setSyncing] = useState<string | null>(null);
    const [syncResult, setSyncResult] = useState<{ provider: string; synced: number } | null>(null);
    const [showSyncMenu, setShowSyncMenu] = useState(false);

    const SYNC_PROVIDERS = [
        { value: "groq", label: "Groq" },
        { value: "google", label: "Google" },
    ];

    async function handleSync(provider: string) {
        setShowSyncMenu(false);
        setSyncing(provider);
        setSyncResult(null);
        try {
            const result = await rateLimitsApi.sync(provider);
            setSyncResult({ provider: result.provider, synced: result.synced });
            loadLimits();
        } catch (err: unknown) {
            alert(`Sync failed: ${err instanceof Error ? err.message : String(err)}`);
        } finally {
            setSyncing(null);
        }
    }

    // ── Load configs ──
    const loadLimits = useCallback(() => {
        setLoading(true);
        rateLimitsApi.list()
            .then(setLimits)
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        if (tab === "config") loadLimits();
    }, [tab, loadLimits]);

    // ── Load usage with auto-refresh ──
    const loadUsage = useCallback(() => {
        setUsageLoading(true);
        rateLimitsApi.usage()
            .then(setUsage)
            .catch(() => {})
            .finally(() => setUsageLoading(false));
    }, []);

    useEffect(() => {
        if (tab !== "usage") {
            if (intervalRef.current) clearInterval(intervalRef.current);
            return;
        }
        loadUsage();
        intervalRef.current = setInterval(loadUsage, 10_000);
        return () => {
            if (intervalRef.current) clearInterval(intervalRef.current);
        };
    }, [tab, loadUsage]);

    // ── CRUD handlers ──
    async function handleSave(data: Partial<ModelRateLimit>) {
        if (editing) {
            const updated = await rateLimitsApi.update(editing.id, data);
            setLimits(l => l.map(x => x.id === updated.id ? updated : x));
        } else {
            const created = await rateLimitsApi.create(data);
            setLimits(l => [...l, created]);
        }
        setShowModal(false);
        setEditing(null);
    }

    async function handleDelete(id: string) {
        if (!confirm("Delete this rate limit configuration?")) return;
        await rateLimitsApi.delete(id);
        setLimits(l => l.filter(x => x.id !== id));
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="border-b border-gray-100 bg-white px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-orange-50 rounded-lg flex items-center justify-center">
                        <Gauge className="w-5 h-5 text-orange-600" />
                    </div>
                    <div>
                        <h1 className="text-lg font-semibold text-gray-900">Rate Limits</h1>
                        <p className="text-xs text-gray-500">Configure and monitor per-model rate limits across providers</p>
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="border-b border-gray-100 bg-white px-6">
                <div className="flex gap-1">
                    {[
                        { id: "config" as Tab, label: "Configuration", icon: Settings2 },
                        { id: "usage" as Tab, label: "Live Usage", icon: BarChart3 },
                    ].map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => setTab(id)}
                            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                                tab === id
                                    ? "border-stone-600 text-stone-700"
                                    : "border-transparent text-gray-500 hover:text-gray-700"
                            }`}
                        >
                            <Icon className="w-4 h-4" />
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6 bg-gray-50">

                {/* ── CONFIG TAB ── */}
                {tab === "config" && (
                    <div className="space-y-4 max-w-5xl">
                        {syncResult && (
                            <div className="flex items-center gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                                Synced {syncResult.synced} models from {syncResult.provider}.
                                <button onClick={() => setSyncResult(null)} className="ml-auto text-emerald-400 hover:text-emerald-600">
                                    <X className="w-3.5 h-3.5" />
                                </button>
                            </div>
                        )}

                        <div className="flex items-center justify-between">
                            <p className="text-sm text-gray-600">
                                Define rate limits per provider/model combination. Agents respect these limits when making LLM calls.
                            </p>
                            <div className="flex items-center gap-2">
                                {/* Sync from Provider */}
                                <div className="relative">
                                    <button
                                        onClick={() => setShowSyncMenu(v => !v)}
                                        disabled={!!syncing}
                                        className="flex items-center gap-2 px-3 py-2 border border-gray-200 text-sm rounded-lg hover:bg-white text-gray-600 hover:text-gray-900 disabled:opacity-50 transition-colors"
                                    >
                                        {syncing ? (
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                        ) : (
                                            <CloudDownload className="w-4 h-4" />
                                        )}
                                        {syncing ? `Syncing ${syncing}...` : "Sync from Provider"}
                                    </button>
                                    {showSyncMenu && (
                                        <div className="absolute right-0 mt-1 w-44 bg-white border border-gray-200 rounded-lg shadow-lg z-10">
                                            {SYNC_PROVIDERS.map(p => (
                                                <button
                                                    key={p.value}
                                                    onClick={() => handleSync(p.value)}
                                                    className="w-full text-left px-4 py-2 text-sm hover:bg-gray-50 first:rounded-t-lg last:rounded-b-lg"
                                                >
                                                    {p.label}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                                <button
                                    onClick={() => { setEditing(null); setShowModal(true); }}
                                    className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white text-sm rounded-lg hover:bg-stone-800"
                                >
                                    <Plus className="w-4 h-4" /> Add Limit
                                </button>
                            </div>
                        </div>

                        {loading ? (
                            <div className="flex items-center justify-center py-16 text-gray-400">
                                <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading...
                            </div>
                        ) : limits.length === 0 ? (
                            <div className="text-center py-16 text-gray-400">
                                <Gauge className="w-10 h-10 mx-auto mb-3 opacity-40" />
                                <p className="text-sm">No rate limits configured yet.</p>
                                <p className="text-xs mt-1">Click &quot;Add Limit&quot; to get started.</p>
                            </div>
                        ) : (
                            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            <th className="px-4 py-3">Provider</th>
                                            <th className="px-4 py-3">Model</th>
                                            <th className="px-4 py-3">Label</th>
                                            <th className="px-4 py-3 text-right">RPM</th>
                                            <th className="px-4 py-3 text-right">RPD</th>
                                            <th className="px-4 py-3 text-right">TPM</th>
                                            <th className="px-4 py-3 text-right">TPD</th>
                                            <th className="px-4 py-3 text-right">Refresh (hrs)</th>
                                            <th className="px-4 py-3 text-right">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                        {limits.map(limit => (
                                            <tr key={limit.id} className="hover:bg-gray-50/50 transition-colors">
                                                <td className="px-4 py-3 font-medium text-gray-900">{limit.provider}</td>
                                                <td className="px-4 py-3 text-gray-700 font-mono text-xs">{limit.model}</td>
                                                <td className="px-4 py-3 text-gray-500">{limit.label || "\u2014"}</td>
                                                <td className="px-4 py-3 text-right tabular-nums">{fmtNum(limit.requests_per_minute)}</td>
                                                <td className="px-4 py-3 text-right tabular-nums">{fmtNum(limit.requests_per_day)}</td>
                                                <td className="px-4 py-3 text-right tabular-nums">{fmtNum(limit.tokens_per_minute)}</td>
                                                <td className="px-4 py-3 text-right tabular-nums">{fmtNum(limit.tokens_per_day)}</td>
                                                <td className="px-4 py-3 text-right tabular-nums">{limit.refresh_interval_hours}h</td>
                                                <td className="px-4 py-3 text-right">
                                                    <div className="flex items-center justify-end gap-1">
                                                        <button
                                                            onClick={() => { setEditing(limit); setShowModal(true); }}
                                                            className="p-1.5 text-gray-400 hover:text-stone-700 hover:bg-gray-100 rounded-lg transition-colors"
                                                            title="Edit"
                                                        >
                                                            <Edit2 className="w-4 h-4" />
                                                        </button>
                                                        <button
                                                            onClick={() => handleDelete(limit.id)}
                                                            className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                                            title="Delete"
                                                        >
                                                            <Trash2 className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}

                        {showModal && (
                            <FormModal
                                initial={editing}
                                onSave={handleSave}
                                onClose={() => { setShowModal(false); setEditing(null); }}
                            />
                        )}
                    </div>
                )}

                {/* ── USAGE TAB ── */}
                {tab === "usage" && (() => {
                    const sorted = [...usage].sort((a, b) => maxUsagePct(b) - maxUsagePct(a));
                    return (
                    <div className="space-y-4 max-w-5xl">
                        <div className="flex items-center justify-between">
                            <p className="text-sm text-gray-600">
                                Real-time usage against configured limits. Auto-refreshes every 10 seconds.
                            </p>
                            <div className="flex items-center gap-2">
                                {/* View toggle */}
                                <div className="flex items-center border border-gray-200 rounded-lg overflow-hidden">
                                    <button
                                        onClick={() => setUsageView("list")}
                                        className={`p-1.5 transition-colors ${usageView === "list" ? "bg-stone-700 text-white" : "text-gray-400 hover:text-gray-700 hover:bg-gray-50"}`}
                                        title="List view"
                                    >
                                        <List className="w-4 h-4" />
                                    </button>
                                    <button
                                        onClick={() => setUsageView("cards")}
                                        className={`p-1.5 transition-colors ${usageView === "cards" ? "bg-stone-700 text-white" : "text-gray-400 hover:text-gray-700 hover:bg-gray-50"}`}
                                        title="Card view"
                                    >
                                        <LayoutGrid className="w-4 h-4" />
                                    </button>
                                </div>
                                <button
                                    onClick={loadUsage}
                                    disabled={usageLoading}
                                    className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 border border-gray-200 rounded-lg hover:bg-white transition-colors"
                                >
                                    <RefreshCw className={`w-4 h-4 ${usageLoading ? "animate-spin" : ""}`} />
                                    Refresh
                                </button>
                            </div>
                        </div>

                        {usageLoading && usage.length === 0 ? (
                            <div className="flex items-center justify-center py-16 text-gray-400">
                                <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading usage data...
                            </div>
                        ) : usage.length === 0 ? (
                            <div className="text-center py-16 text-gray-400">
                                <Activity className="w-10 h-10 mx-auto mb-3 opacity-40" />
                                <p className="text-sm">No usage data available.</p>
                                <p className="text-xs mt-1">Configure rate limits first, then usage will appear here.</p>
                            </div>
                        ) : usageView === "list" ? (
                            /* ── List view ── */
                            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                            <th className="px-4 py-3 w-6"></th>
                                            <th className="px-4 py-3">Provider</th>
                                            <th className="px-4 py-3">Model</th>
                                            <th className="px-4 py-3 text-right">RPM</th>
                                            <th className="px-4 py-3 text-right">RPD</th>
                                            <th className="px-4 py-3 text-right">TPM</th>
                                            <th className="px-4 py-3 text-right">TPD</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100">
                                        {sorted.map(u => {
                                            const mp = maxUsagePct(u);
                                            return (
                                                <tr key={u.id} className="hover:bg-gray-50/50 transition-colors">
                                                    <td className="px-4 py-3">
                                                        <UsageDot p={mp >= 0 ? mp : null} />
                                                    </td>
                                                    <td className="px-4 py-3 font-medium text-gray-900">{u.provider}</td>
                                                    <td className="px-4 py-3 text-gray-700 font-mono text-xs">{u.model}</td>
                                                    <td className="px-4 py-3 text-right"><MiniBar current={u.current.rpm} limit={u.limits.rpm} /></td>
                                                    <td className="px-4 py-3 text-right"><MiniBar current={u.current.rpd} limit={u.limits.rpd} /></td>
                                                    <td className="px-4 py-3 text-right"><MiniBar current={u.current.tpm} limit={u.limits.tpm} /></td>
                                                    <td className="px-4 py-3 text-right"><MiniBar current={u.current.tpd} limit={u.limits.tpd} /></td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            /* ── Card view ── */
                            <div className="grid gap-4 sm:grid-cols-1 md:grid-cols-2">
                                {sorted.map(u => {
                                    const mp = maxUsagePct(u);
                                    const borderClass =
                                        mp < 0
                                            ? "border-gray-200"
                                            : mp > 85
                                            ? "border-red-300"
                                            : mp > 60
                                            ? "border-amber-300"
                                            : "border-gray-200";

                                    return (
                                        <div
                                            key={u.id}
                                            className={`glass-card p-5 space-y-3 border ${borderClass}`}
                                        >
                                            <div className="flex items-center justify-between">
                                                <div>
                                                    <p className="text-sm font-semibold text-gray-900">{u.provider}</p>
                                                    <p className="text-xs font-mono text-gray-500">{u.model}</p>
                                                </div>
                                                {u.label && (
                                                    <span className="text-[10px] font-medium bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                                                        {u.label}
                                                    </span>
                                                )}
                                            </div>
                                            <div className="space-y-2">
                                                <CapacityBar label="RPM" current={u.current.rpm} limit={u.limits.rpm} />
                                                <CapacityBar label="RPD" current={u.current.rpd} limit={u.limits.rpd} />
                                                <CapacityBar label="TPM" current={u.current.tpm} limit={u.limits.tpm} />
                                                <CapacityBar label="TPD" current={u.current.tpd} limit={u.limits.tpd} />
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                    );
                })()}
            </div>
        </div>
    );
}
