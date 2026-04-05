"use client";

import { useEffect, useState } from "react";
import {
    DollarSign, TrendingUp, Loader2, RefreshCw, AlertTriangle,
    PlusCircle, Trash2, BarChart3, Settings, CheckCircle,
    ChevronDown, ChevronUp,
} from "lucide-react";
import {
    financialsApi, agentsApi,
    type CostOverview, type TrendData, type Budget, type BudgetStatus, type ModelPricingRow, type Agent,
} from "@/lib/api";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmt(usd: number): string {
    if (usd === 0) return "$0.00";
    if (usd < 0.0001) return `$${usd.toExponential(2)}`;
    if (usd < 0.01) return `$${usd.toFixed(6)}`;
    return `$${usd.toFixed(4)}`;
}

function fmtNum(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
}

function ProgressBar({ pct, alert }: { pct: number; alert: number }) {
    const filled = Math.min(pct * 100, 100);
    const color = pct >= 1.0 ? "bg-red-500" : pct >= alert ? "bg-amber-500" : "bg-green-500";
    return (
        <div className="w-full h-2 bg-stone-100 rounded-full overflow-hidden">
            <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${filled}%` }} />
        </div>
    );
}

// ─── Mini sparkline (CSS bars) ────────────────────────────────────────────────

function SparkLine({ data }: { data: { date: string; cost_usd: number }[] }) {
    const max = Math.max(...data.map(d => d.cost_usd), 0.000001);
    return (
        <div className="flex items-end gap-px h-12 w-full">
            {data.map((d, i) => (
                <div
                    key={i}
                    className="flex-1 bg-stone-500 rounded-t opacity-80 hover:opacity-100 transition-opacity"
                    style={{ height: `${Math.max((d.cost_usd / max) * 100, 2)}%` }}
                    title={`${d.date}: ${fmt(d.cost_usd)}`}
                />
            ))}
        </div>
    );
}

// ─── Budget Card ──────────────────────────────────────────────────────────────

function BudgetCard({
    budget,
    status,
    agentMap,
    onDelete,
}: {
    budget: Budget;
    status: BudgetStatus | null;
    agentMap: Record<string, string>;
    onDelete: (id: string) => void;
}) {
    const pct = status?.utilization_pct ?? 0;
    const agentName = budget.agent_id ? (agentMap[budget.agent_id] ?? budget.agent_id.slice(0, 8)) : null;

    return (
        <div className={`bg-white rounded-xl border shadow-sm p-4 space-y-3 ${status?.is_over_budget ? "border-red-200" : status?.is_near_threshold ? "border-amber-200" : "border-stone-200"}`}>
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                    <h3 className="font-semibold text-stone-900 truncate">{budget.name}</h3>
                    <p className="text-xs text-stone-500 capitalize">
                        {budget.scope}{agentName ? ` · ${agentName}` : ""} · {budget.period}
                    </p>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                    {status?.is_over_budget && (
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200">Over budget</span>
                    )}
                    {status?.is_near_threshold && !status?.is_over_budget && (
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 border border-amber-200">Near limit</span>
                    )}
                    <button
                        onClick={() => onDelete(budget.id)}
                        className="p-1 rounded hover:bg-red-50 text-stone-400 hover:text-red-500 transition-colors"
                    >
                        <Trash2 className="w-3.5 h-3.5" />
                    </button>
                </div>
            </div>

            {status ? (
                <>
                    <ProgressBar pct={pct} alert={budget.alert_threshold_pct} />
                    <div className="flex items-center justify-between text-xs text-stone-600">
                        <span className="font-medium">{fmt(status.spent_usd)} spent</span>
                        <span className="text-stone-400">of {fmt(budget.limit_usd)} limit ({Math.round(pct * 100)}%)</span>
                    </div>
                </>
            ) : (
                <div className="text-xs text-stone-400">Loading status…</div>
            )}
        </div>
    );
}

// ─── Add Budget Modal ─────────────────────────────────────────────────────────

function AddBudgetModal({
    agents,
    onSave,
    onClose,
}: {
    agents: Agent[];
    onSave: (data: any) => Promise<void>;
    onClose: () => void;
}) {
    const [form, setForm] = useState({
        name: "",
        scope: "agent",
        agent_id: "",
        period: "monthly",
        limit_usd: "",
        alert_threshold_pct: "0.8",
    });
    const [saving, setSaving] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setSaving(true);
        try {
            await onSave({
                ...form,
                limit_usd: parseFloat(form.limit_usd),
                alert_threshold_pct: parseFloat(form.alert_threshold_pct),
                agent_id: form.scope === "agent" ? form.agent_id || null : null,
            });
            onClose();
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
                <div className="px-6 py-4 border-b border-stone-200">
                    <h2 className="text-lg font-semibold text-stone-900">New Budget</h2>
                </div>
                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Name</label>
                        <input
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            required
                            value={form.name}
                            onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                            placeholder="e.g. CEO Agent Monthly Budget"
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Scope</label>
                            <select
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={form.scope}
                                onChange={e => setForm(f => ({ ...f, scope: e.target.value }))}
                            >
                                <option value="agent">Agent</option>
                                <option value="team">Team</option>
                                <option value="org">Org-wide</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Period</label>
                            <select
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={form.period}
                                onChange={e => setForm(f => ({ ...f, period: e.target.value }))}
                            >
                                <option value="daily">Daily</option>
                                <option value="weekly">Weekly</option>
                                <option value="monthly">Monthly</option>
                            </select>
                        </div>
                    </div>
                    {form.scope === "agent" && (
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Agent</label>
                            <select
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={form.agent_id}
                                onChange={e => setForm(f => ({ ...f, agent_id: e.target.value }))}
                            >
                                <option value="">All agents</option>
                                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                            </select>
                        </div>
                    )}
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Limit (USD)</label>
                            <input
                                type="number" step="0.01" min="0.01" required
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={form.limit_usd}
                                onChange={e => setForm(f => ({ ...f, limit_usd: e.target.value }))}
                                placeholder="10.00"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Alert at (%)</label>
                            <input
                                type="number" step="0.05" min="0.1" max="1" required
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={form.alert_threshold_pct}
                                onChange={e => setForm(f => ({ ...f, alert_threshold_pct: e.target.value }))}
                            />
                        </div>
                    </div>
                    <div className="flex gap-2 pt-2">
                        <button type="button" onClick={onClose} className="flex-1 py-2 text-sm rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50">Cancel</button>
                        <button type="submit" disabled={saving} className="flex-1 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-700 disabled:opacity-50 flex items-center justify-center gap-2">
                            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                            Create
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const PERIODS = [
    { value: "day", label: "Today" },
    { value: "week", label: "This Week" },
    { value: "month", label: "This Month" },
    { value: "all", label: "All Time" },
];

export default function FinancialsPage() {
    const [tab, setTab] = useState<"overview" | "budgets" | "pricing">("overview");
    const [period, setPeriod] = useState("month");
    const [overview, setOverview] = useState<CostOverview | null>(null);
    const [trends, setTrends] = useState<TrendData | null>(null);
    const [budgets, setBudgets] = useState<Budget[]>([]);
    const [budgetStatuses, setBudgetStatuses] = useState<Record<string, BudgetStatus>>({});
    const [pricing, setPricing] = useState<ModelPricingRow[]>([]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [showAddBudget, setShowAddBudget] = useState(false);
    const [budgetAlerts, setBudgetAlerts] = useState<any[]>([]);

    const agentMap: Record<string, string> = {};
    for (const a of agents) agentMap[a.id] = a.name;

    async function loadOverview() {
        const [ov, tr, ag] = await Promise.all([
            financialsApi.overview(period),
            financialsApi.trends(30),
            agentsApi.list(),
        ]);
        setOverview(ov);
        setTrends(tr);
        setAgents(ag);
    }

    async function loadBudgets() {
        const [bl, alerts] = await Promise.all([
            financialsApi.listBudgets(),
            financialsApi.getBudgetAlerts(),
        ]);
        setBudgets(bl);
        setBudgetAlerts(alerts.alerts);
        // Load statuses in parallel
        const statuses: Record<string, BudgetStatus> = {};
        await Promise.all(
            bl.map(async b => {
                try {
                    statuses[b.id] = await financialsApi.getBudgetStatus(b.id);
                } catch {}
            })
        );
        setBudgetStatuses(statuses);
    }

    async function loadPricing() {
        setPricing(await financialsApi.listPricing());
    }

    async function loadAll(showSpin = false) {
        if (showSpin) setRefreshing(true);
        try {
            await Promise.all([loadOverview(), loadBudgets(), loadPricing()]);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }

    useEffect(() => { loadAll(); }, [period]);

    async function handleAddBudget(data: any) {
        await financialsApi.createBudget(data);
        await loadBudgets();
    }

    async function handleDeleteBudget(id: string) {
        await financialsApi.deleteBudget(id);
        setBudgets(prev => prev.filter(b => b.id !== id));
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
                        <DollarSign className="w-5 h-5 text-green-600" />
                        Financial Management
                        {budgetAlerts.length > 0 && (
                            <span className="bg-amber-500 text-white text-xs font-bold px-2 py-0.5 rounded-full">{budgetAlerts.length}</span>
                        )}
                    </h1>
                    <p className="text-sm text-stone-500">Track LLM costs, manage budgets, and control spending</p>
                </div>
                <button
                    onClick={() => loadAll(true)}
                    disabled={refreshing}
                    className="p-2 rounded-lg border border-stone-200 hover:bg-stone-50 text-stone-500"
                >
                    <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
                </button>
            </div>

            {/* Budget alerts banner */}
            {budgetAlerts.length > 0 && (
                <div className="px-6 py-2 bg-amber-50 border-b border-amber-100 flex items-center gap-2 flex-wrap">
                    <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                    <span className="text-sm text-amber-800 font-medium">Budget alerts:</span>
                    {budgetAlerts.map(a => (
                        <span key={a.budget_id} className={`text-xs px-2 py-0.5 rounded-full border font-medium ${a.is_over_budget ? "bg-red-100 text-red-700 border-red-200" : "bg-amber-100 text-amber-700 border-amber-200"}`}>
                            {a.name}: {Math.round(a.utilization_pct * 100)}% used
                        </span>
                    ))}
                </div>
            )}

            {/* Tabs */}
            <div className="px-6 pt-4 bg-white border-b border-stone-200 flex items-center gap-1">
                {[
                    { key: "overview", label: "Cost Overview", icon: BarChart3 },
                    { key: "budgets", label: "Budgets", icon: DollarSign },
                    { key: "pricing", label: "Model Pricing", icon: Settings },
                ].map(t => (
                    <button
                        key={t.key}
                        onClick={() => setTab(t.key as any)}
                        className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${tab === t.key ? "border-stone-600 text-stone-700" : "border-transparent text-stone-500 hover:text-stone-700"}`}
                    >
                        <t.icon className="w-4 h-4" />
                        {t.label}
                    </button>
                ))}
            </div>

            <div className="flex-1 overflow-y-auto p-6">

                {/* ── COST OVERVIEW ── */}
                {tab === "overview" && overview && (
                    <div className="space-y-6 max-w-5xl">
                        {/* Period selector */}
                        <div className="flex gap-2">
                            {PERIODS.map(p => (
                                <button
                                    key={p.value}
                                    onClick={() => setPeriod(p.value)}
                                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${period === p.value ? "bg-stone-700 text-white border-stone-600" : "border-stone-200 text-stone-600 hover:bg-stone-50"}`}
                                >
                                    {p.label}
                                </button>
                            ))}
                        </div>

                        {/* Summary cards */}
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                            <div className="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
                                <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide">Total Spend</p>
                                <p className="text-2xl font-bold text-stone-900 mt-1">{fmt(overview.total_cost_usd)}</p>
                                <p className="text-xs text-stone-400 mt-0.5">{PERIODS.find(p2 => p2.value === period)?.label}</p>
                            </div>
                            <div className="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
                                <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide">Total Tokens</p>
                                <p className="text-2xl font-bold text-stone-900 mt-1">{fmtNum(overview.total_tokens)}</p>
                                <p className="text-xs text-stone-400 mt-0.5">across all agents</p>
                            </div>
                            <div className="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
                                <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide">Active Agents</p>
                                <p className="text-2xl font-bold text-stone-900 mt-1">{overview.by_agent.length}</p>
                                <p className="text-xs text-stone-400 mt-0.5">with tracked usage</p>
                            </div>
                        </div>

                        {/* Trend chart */}
                        {trends && (
                            <div className="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
                                <div className="flex items-center justify-between mb-3">
                                    <h2 className="text-sm font-semibold text-stone-700 flex items-center gap-1.5">
                                        <TrendingUp className="w-4 h-4 text-stone-600" /> Daily Cost Trend (30 days)
                                    </h2>
                                </div>
                                <SparkLine data={trends.data} />
                                <div className="flex justify-between text-xs text-stone-400 mt-1">
                                    <span>{trends.data[0]?.date}</span>
                                    <span>{trends.data[trends.data.length - 1]?.date}</span>
                                </div>
                            </div>
                        )}

                        {/* Cost by agent */}
                        <div className="bg-white rounded-xl border border-stone-200 shadow-sm">
                            <div className="px-4 py-3 border-b border-stone-100">
                                <h2 className="text-sm font-semibold text-stone-700">Cost by Agent</h2>
                            </div>
                            {overview.by_agent.length === 0 ? (
                                <p className="px-4 py-6 text-sm text-stone-400 text-center">No cost data yet — token counts are captured on new conversations</p>
                            ) : (
                                <table className="w-full text-sm">
                                    <thead className="bg-stone-50">
                                        <tr>
                                            <th className="text-left px-4 py-2 text-xs font-semibold text-stone-500 uppercase tracking-wide">Agent</th>
                                            <th className="text-right px-4 py-2 text-xs font-semibold text-stone-500 uppercase tracking-wide">Cost (USD)</th>
                                            <th className="text-right px-4 py-2 text-xs font-semibold text-stone-500 uppercase tracking-wide">Share</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-stone-50">
                                        {overview.by_agent.map((a, i) => {
                                            const share = overview.total_cost_usd > 0 ? a.cost_usd / overview.total_cost_usd : 0;
                                            return (
                                                <tr key={a.agent_id} className="hover:bg-stone-50">
                                                    <td className="px-4 py-2.5 font-medium text-stone-800">
                                                        {i === 0 && <span className="mr-1.5 text-amber-500">★</span>}
                                                        {a.agent_name}
                                                    </td>
                                                    <td className="px-4 py-2.5 text-right font-mono text-stone-700">{fmt(a.cost_usd)}</td>
                                                    <td className="px-4 py-2.5 text-right text-stone-500">{Math.round(share * 100)}%</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            )}
                        </div>

                        {/* Cost by provider */}
                        {overview.by_provider.length > 0 && (
                            <div className="bg-white rounded-xl border border-stone-200 shadow-sm">
                                <div className="px-4 py-3 border-b border-stone-100">
                                    <h2 className="text-sm font-semibold text-stone-700">Cost by Provider / Model</h2>
                                </div>
                                <table className="w-full text-sm">
                                    <thead className="bg-stone-50">
                                        <tr>
                                            <th className="text-left px-4 py-2 text-xs font-semibold text-stone-500 uppercase tracking-wide">Provider / Model</th>
                                            <th className="text-right px-4 py-2 text-xs font-semibold text-stone-500 uppercase tracking-wide">Cost (USD)</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-stone-50">
                                        {overview.by_provider.map(p => (
                                            <tr key={p.provider_model} className="hover:bg-stone-50">
                                                <td className="px-4 py-2.5 font-mono text-stone-700">{p.provider_model}</td>
                                                <td className="px-4 py-2.5 text-right font-mono text-stone-700">{fmt(p.cost_usd)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                )}

                {/* ── BUDGETS ── */}
                {tab === "budgets" && (
                    <div className="space-y-4 max-w-3xl">
                        <div className="flex items-center justify-between">
                            <p className="text-sm text-stone-500">{budgets.length} budget{budgets.length !== 1 ? "s" : ""} configured</p>
                            <button
                                onClick={() => setShowAddBudget(true)}
                                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg bg-stone-700 text-white hover:bg-stone-700"
                            >
                                <PlusCircle className="w-4 h-4" /> New Budget
                            </button>
                        </div>

                        {budgets.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-48 text-stone-400">
                                <DollarSign className="w-10 h-10 mb-2 opacity-30" />
                                <p className="text-sm">No budgets yet — create one to start tracking spend limits</p>
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                {budgets.map(b => (
                                    <BudgetCard
                                        key={b.id}
                                        budget={b}
                                        status={budgetStatuses[b.id] ?? null}
                                        agentMap={agentMap}
                                        onDelete={handleDeleteBudget}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── MODEL PRICING ── */}
                {tab === "pricing" && (
                    <div className="space-y-4 max-w-4xl">
                        <p className="text-sm text-stone-500">
                            Pricing is used to compute USD cost from token counts. Built-in defaults are shown in grey — override by clicking on a row.
                        </p>
                        <div className="bg-white rounded-xl border border-stone-200 shadow-sm overflow-hidden">
                            <table className="w-full text-sm">
                                <thead className="bg-stone-50">
                                    <tr>
                                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Provider</th>
                                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Model</th>
                                        <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Input / 1K</th>
                                        <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Output / 1K</th>
                                        <th className="px-4 py-2.5"></th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-stone-50">
                                    {pricing.map((row, i) => (
                                        <PricingRow key={`${row.provider}/${row.model}`} row={row} onSave={async (inp, out) => {
                                            await financialsApi.upsertPricing(row.provider, row.model, { input_cost_per_1k: inp, output_cost_per_1k: out });
                                            await loadPricing();
                                        }} />
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>

            {showAddBudget && (
                <AddBudgetModal agents={agents} onSave={handleAddBudget} onClose={() => setShowAddBudget(false)} />
            )}
        </div>
    );
}

// ─── Pricing Row with inline edit ────────────────────────────────────────────

function PricingRow({ row, onSave }: { row: ModelPricingRow; onSave: (inp: number, out: number) => Promise<void> }) {
    const [editing, setEditing] = useState(false);
    const [inp, setInp] = useState(String(row.input_cost_per_1k));
    const [out, setOut] = useState(String(row.output_cost_per_1k));
    const [saving, setSaving] = useState(false);

    async function handleSave() {
        setSaving(true);
        try {
            await onSave(parseFloat(inp), parseFloat(out));
            setEditing(false);
        } finally {
            setSaving(false);
        }
    }

    return (
        <tr className={`hover:bg-stone-50 ${!row.is_custom ? "text-stone-400" : "text-stone-800"}`}>
            <td className="px-4 py-2.5 font-medium">{row.provider}</td>
            <td className="px-4 py-2.5 font-mono text-xs">{row.model}</td>
            <td className="px-4 py-2.5 text-right font-mono text-xs">
                {editing ? (
                    <input
                        className="w-24 border border-stone-200 rounded px-2 py-0.5 text-xs text-right focus:outline-none focus:ring-1 focus:ring-stone-600"
                        value={inp}
                        onChange={e => setInp(e.target.value)}
                    />
                ) : `$${row.input_cost_per_1k}`}
            </td>
            <td className="px-4 py-2.5 text-right font-mono text-xs">
                {editing ? (
                    <input
                        className="w-24 border border-stone-200 rounded px-2 py-0.5 text-xs text-right focus:outline-none focus:ring-1 focus:ring-stone-600"
                        value={out}
                        onChange={e => setOut(e.target.value)}
                    />
                ) : `$${row.output_cost_per_1k}`}
            </td>
            <td className="px-4 py-2.5 text-right">
                {editing ? (
                    <div className="flex gap-1 justify-end">
                        <button onClick={() => setEditing(false)} className="text-xs px-2 py-0.5 rounded border border-stone-200 hover:bg-stone-50">Cancel</button>
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="text-xs px-2 py-0.5 rounded bg-stone-700 text-white hover:bg-stone-700 disabled:opacity-50 flex items-center gap-1"
                        >
                            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : null} Save
                        </button>
                    </div>
                ) : (
                    <button
                        onClick={() => setEditing(true)}
                        className="text-xs px-2 py-0.5 rounded border border-stone-200 text-stone-500 hover:bg-stone-50"
                    >
                        Override
                    </button>
                )}
            </td>
        </tr>
    );
}
