"use client";

import { useEffect, useState, useCallback } from "react";
import {
    Activity, AlertTriangle, Bot, CheckCircle, Clock, Code,
    Cpu, RefreshCw, Save, Terminal, XCircle, Zap, Info,
} from "lucide-react";
import {
    agentsApi, monitorApi,
    type Agent, type MonitorUsageOverview, type MonitorMetrics,
    type MonitorAlert,
} from "@/lib/api";
import { wsClient } from "@/lib/ws";

// ─── Sub-components ──────────────────────────────────────────────────────────

function LogMessage({ message }: { message: string }) {
    try {
        const parsed = JSON.parse(message);
        if (typeof parsed === "object" && parsed !== null) {
            return (
                <div className="mt-2 bg-[#0d1117] rounded-lg border border-stone-800 overflow-hidden">
                    <div className="flex items-center px-3 py-1.5 bg-stone-800/50 border-b border-stone-800">
                        <Code className="w-3.5 h-3.5 text-stone-500 mr-1.5" />
                        <span className="text-[10px] font-medium text-stone-500 uppercase tracking-wider">Payload</span>
                    </div>
                    <pre className="p-3 text-[11px] font-mono text-stone-300 overflow-x-auto leading-relaxed">
                        {JSON.stringify(parsed, null, 2)}
                    </pre>
                </div>
            );
        }
    } catch (_) { /* not JSON */ }
    return <p className="text-stone-600 dark:text-stone-300 text-[13px] mt-1 leading-relaxed">{message}</p>;
}

function AlertBadge({ severity }: { severity: "warning" | "critical" }) {
    return severity === "critical" ? (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border border-red-200 dark:border-red-800">
            <XCircle className="w-3 h-3" /> Critical
        </span>
    ) : (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
            <AlertTriangle className="w-3 h-3" /> Warning
        </span>
    );
}

function MetricCard({
    label, value, sub, color,
}: { label: string; value: string | number; sub?: string; color: string }) {
    return (
        <div className="glass-card p-4 flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-md ${color}`}>
                <Activity className="w-5 h-5 text-white" />
            </div>
            <div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
                <p className="text-xs text-gray-400">{label}</p>
                {sub && <p className="text-[10px] text-gray-500 mt-0.5">{sub}</p>}
            </div>
        </div>
    );
}

// ─── Main page ───────────────────────────────────────────────────────────────

interface ActivityEvent {
    id: string;
    type: string;
    agent_name: string;
    message: string;
    timestamp: string;
}

export default function MonitorPage() {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [events, setEvents] = useState<ActivityEvent[]>([]);
    const [wsConnected, setWsConnected] = useState(false);
    const [usageOverview, setUsageOverview] = useState<MonitorUsageOverview | null>(null);
    const [metrics, setMetrics] = useState<MonitorMetrics | null>(null);
    const [alerts, setAlerts] = useState<MonitorAlert[]>([]);
    const [dismissedAlerts, setDismissedAlerts] = useState<Set<string>>(new Set());
    const [editingLimitKey, setEditingLimitKey] = useState<string | null>(null);
    const [editLimitValue, setEditLimitValue] = useState<number>(0);
    const [newLimitFields, setNewLimitFields] = useState({ provider: "", model: "", limit: 100 });
    const [isAddingLimit, setIsAddingLimit] = useState(false);
    const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());

    const loadAll = useCallback(async () => {
        await Promise.allSettled([
            agentsApi.list().then(setAgents),
            monitorApi.getUsage().then(setUsageOverview),
            monitorApi.getMetrics().then(setMetrics),
            monitorApi.getAlerts().then(d => setAlerts(d.alerts)),
        ]);
        setLastRefreshed(new Date());
    }, []);

    useEffect(() => {
        loadAll();
        const interval = setInterval(loadAll, 30_000);
        return () => clearInterval(interval);
    }, [loadAll]);

    useEffect(() => {
        wsClient.connect();
        const u1 = wsClient.on("connection", (d) => setWsConnected(d.status === "connected"));
        const u2 = wsClient.on("agent_status", (d) =>
            addEvent({ type: "status", agent_name: d.agent_id, message: `Status → ${d.status}` })
        );
        const u3 = wsClient.on("*", (d) => {
            if (d.type !== "pong" && d.type !== "connection")
                addEvent({ type: d.type, agent_name: d.agent_id || "system", message: JSON.stringify(d.data || {}) });
        });
        return () => { u1(); u2(); u3(); };
    }, []);

    function addEvent(e: Omit<ActivityEvent, "id" | "timestamp">) {
        setEvents(prev => [{
            ...e,
            id: `evt-${Date.now()}-${Math.random().toString(36).slice(2)}`,
            timestamp: new Date().toLocaleTimeString(),
        }, ...prev.slice(0, 99)]);
    }

    const handleSaveLimit = async (provider: string, model: string, override?: number) => {
        try {
            await monitorApi.updateLimit(provider, override ?? editLimitValue, model);
            setEditingLimitKey(null);
            setIsAddingLimit(false);
            monitorApi.getUsage().then(setUsageOverview);
        } catch { alert("Failed to update limit."); }
    };

    const activeAlerts = alerts.filter(a => !dismissedAlerts.has(a.id));
    const runningAgents = agents.filter(a => a.status === "running");

    // Helper: get agent name from id
    const agentName = (id: string) => agents.find(a => a.id === id)?.name ?? id.slice(0, 8) + "…";

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Monitor</h1>
                    <p className="text-gray-500 dark:text-gray-400 mt-1">
                        Health dashboard, metrics, and real-time alerts
                    </p>
                </div>
                <button
                    onClick={loadAll}
                    className="flex items-center gap-1.5 text-xs text-stone-500 hover:text-stone-700 dark:hover:text-stone-300 transition-colors"
                    title="Refresh now"
                >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>Refreshed {lastRefreshed.toLocaleTimeString()}</span>
                </button>
            </div>

            {/* ── Alerts panel ───────────────────────────────────────────── */}
            {activeAlerts.length > 0 && (
                <div className="space-y-2">
                    <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 text-amber-500" />
                        Active Alerts ({activeAlerts.length})
                    </h2>
                    {activeAlerts.map(alert => (
                        <div
                            key={alert.id}
                            className={`flex items-start gap-3 p-3.5 rounded-xl border text-sm ${
                                alert.severity === "critical"
                                    ? "bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-800"
                                    : "bg-amber-50 dark:bg-amber-900/10 border-amber-200 dark:border-amber-800"
                            }`}
                        >
                            {alert.severity === "critical"
                                ? <XCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                                : <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                            }
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-0.5">
                                    <span className="font-semibold text-gray-900 dark:text-white text-[13px]">{alert.title}</span>
                                    <AlertBadge severity={alert.severity} />
                                </div>
                                <p className="text-[12px] text-gray-600 dark:text-gray-400">{alert.message}</p>
                            </div>
                            <button
                                onClick={() => setDismissedAlerts(prev => new Set([...prev, alert.id]))}
                                className="text-stone-400 hover:text-stone-600 dark:hover:text-stone-200 text-xs"
                                title="Dismiss"
                            >
                                ✕
                            </button>
                        </div>
                    ))}
                </div>
            )}
            {activeAlerts.length === 0 && (
                <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-emerald-50 dark:bg-emerald-900/10 border border-emerald-200 dark:border-emerald-800 text-sm text-emerald-700 dark:text-emerald-400">
                    <CheckCircle className="w-4 h-4" />
                    All systems healthy — no active alerts.
                </div>
            )}

            {/* ── Stats row ──────────────────────────────────────────────── */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="glass-card p-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-stone-700 to-stone-900 flex items-center justify-center shadow-md">
                        <Activity className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-gray-900 dark:text-white">{metrics?.total_requests ?? "—"}</p>
                        <p className="text-xs text-gray-400">Requests Today</p>
                    </div>
                </div>

                <div className="glass-card p-4 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center shadow-md">
                        <Clock className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-gray-900 dark:text-white">
                            {metrics ? `${metrics.avg_latency_ms}ms` : "—"}
                        </p>
                        <p className="text-xs text-gray-400">Avg Latency</p>
                    </div>
                </div>

                <div className="glass-card p-4 flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-md ${
                        metrics && metrics.error_rate >= 0.2
                            ? "bg-gradient-to-br from-red-500 to-red-700"
                            : metrics && metrics.error_rate >= 0.05
                            ? "bg-gradient-to-br from-amber-500 to-amber-700"
                            : "bg-gradient-to-br from-emerald-500 to-emerald-700"
                    }`}>
                        <XCircle className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-gray-900 dark:text-white">
                            {metrics ? `${(metrics.error_rate * 100).toFixed(1)}%` : "—"}
                        </p>
                        <p className="text-xs text-gray-400">Error Rate</p>
                    </div>
                </div>

                <div className="glass-card p-4 flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-md ${
                        activeAlerts.some(a => a.severity === "critical")
                            ? "bg-gradient-to-br from-red-500 to-red-700"
                            : activeAlerts.length > 0
                            ? "bg-gradient-to-br from-amber-500 to-amber-700"
                            : "bg-gradient-to-br from-emerald-500 to-emerald-700"
                    }`}>
                        <AlertTriangle className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <p className="text-2xl font-bold text-gray-900 dark:text-white">{activeAlerts.length}</p>
                        <p className="text-xs text-gray-400">Active Alerts</p>
                    </div>
                </div>
            </div>

            {/* ── Agent Performance Table ────────────────────────────────── */}
            {metrics && metrics.agents.length > 0 && (
                <div className="glass-card p-6">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                        <Bot className="w-5 h-5 text-stone-600" />
                        Agent Performance (Today)
                    </h2>
                    <div className="overflow-x-auto rounded-lg border border-stone-200 dark:border-stone-700/50">
                        <table className="w-full text-sm text-left">
                            <thead className="bg-stone-50 dark:bg-stone-800/50 text-xs uppercase font-medium text-stone-500 dark:text-stone-400">
                                <tr>
                                    <th className="px-4 py-3">Agent</th>
                                    <th className="px-4 py-3">Requests</th>
                                    <th className="px-4 py-3">Errors</th>
                                    <th className="px-4 py-3">Error Rate</th>
                                    <th className="px-4 py-3">Avg Latency</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-stone-200 dark:divide-stone-700/50 bg-white dark:bg-surface-dark3">
                                {metrics.agents.map(ag => {
                                    const errPct = ag.error_rate * 100;
                                    return (
                                        <tr key={ag.agent_id} className="hover:bg-stone-50/50 dark:hover:bg-stone-800/20">
                                            <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                                                {agentName(ag.agent_id)}
                                                <span className="block text-[10px] font-mono text-stone-400 mt-0.5">{ag.agent_id.slice(0, 8)}…</span>
                                            </td>
                                            <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{ag.requests}</td>
                                            <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{ag.errors}</td>
                                            <td className="px-4 py-3">
                                                <span className={`font-semibold ${
                                                    errPct >= 20 ? "text-red-500" : errPct >= 5 ? "text-amber-500" : "text-emerald-600"
                                                }`}>
                                                    {errPct.toFixed(1)}%
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-gray-700 dark:text-gray-300 font-mono text-xs">
                                                {ag.avg_latency_ms}ms
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ── Recent Errors ──────────────────────────────────────────── */}
            {metrics && metrics.recent_errors.length > 0 && (
                <div className="glass-card p-6">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                        <XCircle className="w-5 h-5 text-red-500" />
                        Recent Errors
                    </h2>
                    <div className="space-y-2">
                        {metrics.recent_errors.map(err => (
                            <div key={err.trace_id} className="flex items-start gap-3 p-3 rounded-lg bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800/50">
                                <XCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                                <div className="flex-1 min-w-0">
                                    <p className="text-xs font-medium text-red-700 dark:text-red-400">{agentName(err.agent_id)}</p>
                                    <p className="text-xs text-red-600 dark:text-red-500 mt-0.5 truncate">{err.error_message ?? "Unknown error"}</p>
                                </div>
                                <span className="text-[10px] text-red-400 font-mono flex-shrink-0">
                                    {new Date(err.created_at).toLocaleTimeString()}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* ── LLM Usage & Limits ────────────────────────────────────── */}
            <div className="glass-card p-6">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Cpu className="w-5 h-5 text-stone-600" />
                        LLM Usage & Limits (Today)
                    </h2>
                    <button
                        onClick={() => monitorApi.getUsage().then(setUsageOverview)}
                        className="p-1.5 rounded-md hover:bg-stone-100 dark:hover:bg-stone-800 text-stone-500 transition-colors"
                        title="Refresh"
                    >
                        <RefreshCw className="w-4 h-4" />
                    </button>
                </div>

                {usageOverview ? (
                    <div className="overflow-x-auto rounded-lg border border-stone-200 dark:border-stone-700/50">
                        <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                            <thead className="bg-stone-50 dark:bg-stone-800/50 text-xs uppercase font-medium text-stone-700 dark:text-stone-300">
                                <tr>
                                    <th className="px-4 py-3">Provider / Model</th>
                                    <th className="px-4 py-3">Daily Limit</th>
                                    <th className="px-4 py-3">Status</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-stone-200 dark:divide-stone-700/50 bg-white dark:bg-surface-dark3">
                                {(() => {
                                    const modelPairs = new Set<string>();
                                    usageOverview.usages.forEach(u => modelPairs.add(`${u.provider}|${u.model}`));
                                    usageOverview.limits.forEach(l => { if (l.model !== "*") modelPairs.add(`${l.provider}|${l.model}`); });

                                    const rows = Array.from(modelPairs).map(combined => {
                                        const [provider, model] = combined.split("|");
                                        const usageRec = usageOverview.usages.find(u => u.provider === provider && u.model === model);
                                        const used = usageRec?.request_count ?? 0;
                                        const exactLimit = usageOverview.limits.find(l => l.provider === provider && l.model === model);
                                        const wildcardLimit = usageOverview.limits.find(l => l.provider === provider && l.model === "*");
                                        const dailyLimit = exactLimit?.daily_limit ?? wildcardLimit?.daily_limit ?? 100;
                                        return { provider, model, used, dailyLimit, isExplicit: !!exactLimit };
                                    });
                                    rows.sort((a, b) => a.provider.localeCompare(b.provider) || a.model.localeCompare(b.model));

                                    return rows.map(row => {
                                        const limitKey = `${row.provider}:${row.model}`;
                                        const progress = Math.min((row.used / row.dailyLimit) * 100, 100);
                                        return (
                                            <tr key={limitKey} className="hover:bg-stone-50/50 dark:hover:bg-stone-800/20">
                                                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white capitalize">
                                                    {row.provider}
                                                    <span className="block text-[11px] text-stone-500 normal-case font-mono mt-0.5">{row.model}</span>
                                                </td>
                                                <td className="px-4 py-3">
                                                    {editingLimitKey === limitKey ? (
                                                        <div className="flex items-center gap-2">
                                                            <input
                                                                type="number"
                                                                className="w-20 px-2 py-1 text-sm border rounded bg-white dark:bg-stone-900 border-stone-300 dark:border-stone-600 focus:ring-1 focus:ring-stone-600 outline-none"
                                                                value={editLimitValue}
                                                                onChange={e => setEditLimitValue(parseInt(e.target.value) || 0)}
                                                            />
                                                            <button onClick={() => handleSaveLimit(row.provider, row.model)} className="p-1 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 rounded">
                                                                <Save className="w-4 h-4" />
                                                            </button>
                                                            <button onClick={() => setEditingLimitKey(null)} className="text-xs text-stone-500 hover:underline">Cancel</button>
                                                        </div>
                                                    ) : (
                                                        <div className="cursor-pointer group flex items-center gap-2" onClick={() => { setEditingLimitKey(limitKey); setEditLimitValue(row.dailyLimit); }}>
                                                            <span className={row.used >= row.dailyLimit ? "text-red-500 font-bold" : "text-gray-900 dark:text-gray-200"}>
                                                                {row.used} / {row.dailyLimit}
                                                            </span>
                                                            <div className="w-24 h-1.5 bg-stone-200 dark:bg-stone-700 rounded-full overflow-hidden">
                                                                <div className={`h-full ${progress >= 100 ? "bg-red-500" : progress >= 80 ? "bg-amber-500" : "bg-stone-700"}`} style={{ width: `${progress}%` }} />
                                                            </div>
                                                            <div className="flex items-center gap-1">
                                                                {!row.isExplicit && <span title="Using provider wildcard limit"><Info className="w-3 h-3 text-stone-400" /></span>}
                                                                <span className="text-[10px] text-stone-400 opacity-0 group-hover:opacity-100 transition-opacity">Edit</span>
                                                            </div>
                                                        </div>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3">
                                                    {progress >= 100 ? (
                                                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                                                            <XCircle className="w-3 h-3" /> Exhausted
                                                        </span>
                                                    ) : progress >= 80 ? (
                                                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                                                            <AlertTriangle className="w-3 h-3" /> Near Limit
                                                        </span>
                                                    ) : (
                                                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                                                            <CheckCircle className="w-3 h-3" /> OK
                                                        </span>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    });
                                })()}
                                {/* Add New Limit Row */}
                                <tr className="bg-stone-50/30 dark:bg-stone-800/10">
                                    <td className="px-4 py-3" colSpan={3}>
                                        <details className="group" open={isAddingLimit} onToggle={e => setIsAddingLimit((e.target as HTMLDetailsElement).open)}>
                                            <summary className="text-xs font-medium text-stone-600 cursor-pointer hover:underline list-none flex items-center gap-1">
                                                + Add custom model limit
                                            </summary>
                                            <div className="mt-3 grid grid-cols-1 sm:grid-cols-4 gap-3">
                                                <input placeholder="Provider (e.g. groq)" className="px-2 py-1.5 text-xs border rounded bg-white dark:bg-stone-900 border-stone-300 dark:border-stone-600 outline-none" value={newLimitFields.provider} onChange={e => setNewLimitFields({ ...newLimitFields, provider: e.target.value })} />
                                                <input placeholder="Model Name" className="px-2 py-1.5 text-xs border rounded bg-white dark:bg-stone-900 border-stone-300 dark:border-stone-600 outline-none" value={newLimitFields.model} onChange={e => setNewLimitFields({ ...newLimitFields, model: e.target.value })} />
                                                <input type="number" placeholder="Daily Limit" className="px-2 py-1.5 text-xs border rounded bg-white dark:bg-stone-900 border-stone-300 dark:border-stone-600 outline-none" value={newLimitFields.limit} onChange={e => setNewLimitFields({ ...newLimitFields, limit: parseInt(e.target.value) || 0 })} />
                                                <button onClick={() => { if (newLimitFields.provider && newLimitFields.model) { handleSaveLimit(newLimitFields.provider, newLimitFields.model, newLimitFields.limit); setNewLimitFields({ provider: "", model: "", limit: 100 }); } else alert("Please fill all fields"); }} className="bg-stone-700 hover:bg-stone-700 text-white text-xs font-medium px-3 py-1.5 rounded transition-colors">
                                                    Add Limit
                                                </button>
                                            </div>
                                        </details>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <p className="text-center py-4 text-sm text-stone-500">Loading usage statistics…</p>
                )}
            </div>

            {/* ── Bottom row: Active Agents + Activity Feed ──────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Running Agents */}
                <div className="glass-card p-6">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                        <Bot className="w-5 h-5 text-stone-600" />
                        Active Agents
                        <span className="ml-auto text-xs font-normal text-stone-500">{runningAgents.length} running</span>
                    </h2>
                    {runningAgents.length === 0 ? (
                        <p className="text-sm text-gray-400 text-center py-8">No agents running</p>
                    ) : (
                        <div className="space-y-2">
                            {runningAgents.map(agent => (
                                <div key={agent.id} className="flex items-center gap-3 p-3 rounded-xl bg-surface-1 dark:bg-surface-dark2">
                                    <div className="status-dot status-dot-running" />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{agent.name}</p>
                                        <p className="text-xs text-gray-400 font-mono">{agent.llm_model}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Activity Feed */}
                <div className="lg:col-span-2 glass-card p-6">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                        <Activity className="w-5 h-5 text-stone-600" />
                        Activity Feed
                        <span className={`ml-auto flex items-center gap-1 text-xs font-normal ${wsConnected ? "text-emerald-500" : "text-stone-400"}`}>
                            <Zap className="w-3 h-3" /> {wsConnected ? "Live" : "Disconnected"}
                        </span>
                    </h2>
                    <div className="space-y-2 max-h-96 overflow-y-auto custom-scrollbar">
                        {events.length === 0 ? (
                            <p className="text-sm text-gray-400 text-center py-8">No activity yet. Events will appear here in real-time.</p>
                        ) : (
                            events.map(event => (
                                <div key={event.id} className="flex items-start gap-3.5 p-4 rounded-xl bg-white dark:bg-surface-dark3 border border-stone-200 dark:border-stone-800 shadow-sm hover:shadow-md transition-shadow animate-slide-up group">
                                    <div className="w-8 h-8 rounded-lg bg-surface-2 dark:bg-stone-800 flex items-center justify-center flex-shrink-0 mt-0.5 border border-stone-100 dark:border-stone-700/50">
                                        <Terminal className="w-4 h-4 text-stone-600" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center justify-between gap-2 mb-0.5">
                                            <div className="flex items-center gap-2">
                                                <span className="font-semibold text-stone-900 dark:text-white text-sm">{event.agent_name}</span>
                                                <span className="px-2 py-0.5 rounded border border-stone-200 dark:border-stone-700 bg-stone-50 dark:bg-stone-800/50 text-[10px] font-medium text-stone-500 uppercase tracking-wider">{event.type}</span>
                                            </div>
                                            <div className="flex items-center gap-1.5 text-xs text-stone-400">
                                                <Clock className="w-3.5 h-3.5" />
                                                <span className="font-mono">{event.timestamp}</span>
                                            </div>
                                        </div>
                                        <LogMessage message={event.message} />
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
