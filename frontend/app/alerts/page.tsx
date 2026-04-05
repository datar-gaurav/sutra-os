"use client";

import { useState, useEffect, useCallback } from "react";
import {
    Bell, AlertTriangle, AlertCircle, Info, Check, CheckCheck,
    RefreshCw, Shield, Clock, ChevronDown, ChevronRight, Settings2,
    Plus, Trash2, ToggleLeft, ToggleRight,
} from "lucide-react";
import { alertsApi, AlertRecord, AlertRule, AlertSummary } from "@/lib/api";
import { wsClient } from "@/lib/ws";

// ── Severity helpers ─────────────────────────────────────────────────────────

const SEVERITY_CONFIG = {
    critical: { icon: AlertCircle, color: "text-red-600", bg: "bg-red-50 border-red-200", badge: "bg-red-100 text-red-700" },
    warning: { icon: AlertTriangle, color: "text-amber-600", bg: "bg-amber-50 border-amber-200", badge: "bg-amber-100 text-amber-700" },
    info: { icon: Info, color: "text-blue-600", bg: "bg-blue-50 border-blue-200", badge: "bg-blue-100 text-blue-700" },
};

const STATUS_TABS = ["firing", "acknowledged", "resolved", "all"] as const;

// ── Main Page ────────────────────────────────────────────────────────────────

export default function AlertsPage() {
    const [alerts, setAlerts] = useState<AlertRecord[]>([]);
    const [rules, setRules] = useState<AlertRule[]>([]);
    const [summary, setSummary] = useState<AlertSummary | null>(null);
    const [statusFilter, setStatusFilter] = useState<string>("firing");
    const [expandedId, setExpandedId] = useState<string | null>(null);
    const [showRules, setShowRules] = useState(false);
    const [loading, setLoading] = useState(true);

    const fetchAlerts = useCallback(async () => {
        try {
            const params: Record<string, string> = {};
            if (statusFilter !== "all") params.status = statusFilter;
            const data = await alertsApi.list(params);
            setAlerts(data);
        } catch { /* ignore */ }
    }, [statusFilter]);

    const fetchSummary = useCallback(async () => {
        try {
            const data = await alertsApi.summary();
            setSummary(data);
        } catch { /* ignore */ }
    }, []);

    const fetchRules = useCallback(async () => {
        try {
            const data = await alertsApi.listRules();
            setRules(data);
        } catch { /* ignore */ }
    }, []);

    useEffect(() => {
        setLoading(true);
        Promise.all([fetchAlerts(), fetchSummary(), fetchRules()]).finally(() => setLoading(false));
    }, [fetchAlerts, fetchSummary, fetchRules]);

    // Real-time WebSocket updates
    useEffect(() => {
        const unsub1 = wsClient.on("alert_fired", () => {
            fetchAlerts();
            fetchSummary();
        });
        const unsub2 = wsClient.on("alert_resolved", () => {
            fetchAlerts();
            fetchSummary();
        });
        return () => { unsub1(); unsub2(); };
    }, [fetchAlerts, fetchSummary]);

    async function handleAcknowledge(id: string) {
        await alertsApi.acknowledge(id);
        fetchAlerts();
        fetchSummary();
    }

    async function handleResolve(id: string) {
        await alertsApi.resolve(id);
        fetchAlerts();
        fetchSummary();
    }

    async function handleAcknowledgeAll() {
        await alertsApi.acknowledgeAll();
        fetchAlerts();
        fetchSummary();
    }

    async function handleToggleRule(rule: AlertRule) {
        await alertsApi.updateRule(rule.id, { is_active: !rule.is_active });
        fetchRules();
    }

    async function handleDeleteRule(id: string) {
        if (!confirm("Delete this alert rule?")) return;
        await alertsApi.deleteRule(id);
        fetchRules();
    }

    return (
        <div className="p-6 max-w-6xl mx-auto space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Bell className="w-6 h-6 text-stone-700" />
                    <h1 className="text-2xl font-bold text-stone-800">Alerts</h1>
                    {summary && summary.firing_count > 0 && (
                        <span className="bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                            {summary.firing_count} firing
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => { fetchAlerts(); fetchSummary(); }}
                        className="p-2 rounded-lg hover:bg-stone-100 text-stone-500"
                        title="Refresh"
                    >
                        <RefreshCw className="w-4 h-4" />
                    </button>
                    {summary && summary.firing_count > 0 && (
                        <button
                            onClick={handleAcknowledgeAll}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-stone-800 text-white rounded-lg hover:bg-stone-700"
                        >
                            <CheckCheck className="w-4 h-4" />
                            Acknowledge All
                        </button>
                    )}
                </div>
            </div>

            {/* Summary Cards */}
            {summary && (
                <div className="grid grid-cols-4 gap-4">
                    <SummaryCard label="Firing" count={summary.firing_count} color="text-red-600" bg="bg-red-50" />
                    <SummaryCard label="Critical" count={summary.critical_count} color="text-red-700" bg="bg-red-50" />
                    <SummaryCard label="Warning" count={summary.warning_count} color="text-amber-600" bg="bg-amber-50" />
                    <SummaryCard label="Acknowledged" count={summary.acknowledged_count} color="text-blue-600" bg="bg-blue-50" />
                </div>
            )}

            {/* Status Tabs */}
            <div className="flex items-center gap-1 bg-stone-100 p-1 rounded-lg w-fit">
                {STATUS_TABS.map((tab) => (
                    <button
                        key={tab}
                        onClick={() => setStatusFilter(tab)}
                        className={`px-3 py-1.5 text-sm rounded-md capitalize transition-colors ${
                            statusFilter === tab
                                ? "bg-white text-stone-800 shadow-sm font-medium"
                                : "text-stone-500 hover:text-stone-700"
                        }`}
                    >
                        {tab}
                    </button>
                ))}
            </div>

            {/* Alert List */}
            <div className="space-y-3">
                {loading && <p className="text-stone-400 text-sm">Loading alerts...</p>}
                {!loading && alerts.length === 0 && (
                    <div className="text-center py-12 text-stone-400">
                        <Shield className="w-12 h-12 mx-auto mb-3 opacity-40" />
                        <p className="text-lg font-medium">No {statusFilter === "all" ? "" : statusFilter} alerts</p>
                        <p className="text-sm mt-1">The system is healthy.</p>
                    </div>
                )}
                {alerts.map((alert) => {
                    const config = SEVERITY_CONFIG[alert.severity as keyof typeof SEVERITY_CONFIG] || SEVERITY_CONFIG.info;
                    const SeverityIcon = config.icon;
                    const isExpanded = expandedId === alert.id;

                    return (
                        <div
                            key={alert.id}
                            className={`border rounded-lg p-4 ${config.bg} transition-all`}
                        >
                            <div className="flex items-start gap-3">
                                <SeverityIcon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${config.color}`} />
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <h3 className="font-semibold text-stone-800 text-sm">{alert.title}</h3>
                                        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${config.badge}`}>
                                            {alert.severity}
                                        </span>
                                        <span className="text-xs text-stone-400 capitalize">
                                            {alert.status}
                                        </span>
                                    </div>
                                    <p className="text-sm text-stone-600 mt-1">{alert.message}</p>
                                    <div className="flex items-center gap-3 mt-2 text-xs text-stone-400">
                                        <span className="flex items-center gap-1">
                                            <Clock className="w-3 h-3" />
                                            {alert.fired_at ? new Date(alert.fired_at).toLocaleString() : "—"}
                                        </span>
                                        {alert.agent_id && (
                                            <span>Agent: {alert.agent_id.slice(0, 8)}...</span>
                                        )}
                                        <button
                                            onClick={() => setExpandedId(isExpanded ? null : alert.id)}
                                            className="flex items-center gap-0.5 hover:text-stone-600"
                                        >
                                            {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                                            Details
                                        </button>
                                    </div>
                                    {isExpanded && alert.context && (
                                        <pre className="mt-3 text-xs bg-white/60 p-3 rounded border border-stone-200 overflow-x-auto">
                                            {JSON.stringify(alert.context, null, 2)}
                                        </pre>
                                    )}
                                </div>
                                <div className="flex items-center gap-1.5 flex-shrink-0">
                                    {alert.status === "firing" && (
                                        <>
                                            <button
                                                onClick={() => handleAcknowledge(alert.id)}
                                                className="p-1.5 rounded-md bg-white border border-stone-200 text-stone-600 hover:bg-stone-50 text-xs"
                                                title="Acknowledge"
                                            >
                                                <Check className="w-3.5 h-3.5" />
                                            </button>
                                            <button
                                                onClick={() => handleResolve(alert.id)}
                                                className="p-1.5 rounded-md bg-white border border-stone-200 text-green-600 hover:bg-green-50 text-xs"
                                                title="Resolve"
                                            >
                                                <CheckCheck className="w-3.5 h-3.5" />
                                            </button>
                                        </>
                                    )}
                                    {alert.status === "acknowledged" && (
                                        <button
                                            onClick={() => handleResolve(alert.id)}
                                            className="p-1.5 rounded-md bg-white border border-stone-200 text-green-600 hover:bg-green-50 text-xs"
                                            title="Resolve"
                                        >
                                            <CheckCheck className="w-3.5 h-3.5" />
                                        </button>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Alert Rules Section */}
            <div className="border border-stone-200 rounded-lg bg-white">
                <button
                    onClick={() => setShowRules(!showRules)}
                    className="w-full flex items-center justify-between p-4 text-left hover:bg-stone-50 transition-colors"
                >
                    <div className="flex items-center gap-2">
                        <Settings2 className="w-5 h-5 text-stone-500" />
                        <h2 className="font-semibold text-stone-700">Alert Rules</h2>
                        <span className="text-xs text-stone-400">{rules.length} rules</span>
                    </div>
                    {showRules ? <ChevronDown className="w-4 h-4 text-stone-400" /> : <ChevronRight className="w-4 h-4 text-stone-400" />}
                </button>

                {showRules && (
                    <div className="border-t border-stone-200">
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-left text-xs text-stone-400 uppercase tracking-wider">
                                        <th className="px-4 py-3">Active</th>
                                        <th className="px-4 py-3">Name</th>
                                        <th className="px-4 py-3">Type</th>
                                        <th className="px-4 py-3">Severity</th>
                                        <th className="px-4 py-3">Threshold</th>
                                        <th className="px-4 py-3">Window</th>
                                        <th className="px-4 py-3">Cooldown</th>
                                        <th className="px-4 py-3">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-stone-100">
                                    {rules.map((rule) => (
                                        <tr key={rule.id} className="hover:bg-stone-50">
                                            <td className="px-4 py-3">
                                                <button onClick={() => handleToggleRule(rule)}>
                                                    {rule.is_active
                                                        ? <ToggleRight className="w-5 h-5 text-green-500" />
                                                        : <ToggleLeft className="w-5 h-5 text-stone-300" />
                                                    }
                                                </button>
                                            </td>
                                            <td className="px-4 py-3 font-medium text-stone-700">{rule.name}</td>
                                            <td className="px-4 py-3 text-stone-500">
                                                <span className="bg-stone-100 px-1.5 py-0.5 rounded text-xs">
                                                    {rule.rule_type}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3">
                                                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                                                    SEVERITY_CONFIG[rule.severity as keyof typeof SEVERITY_CONFIG]?.badge || "bg-stone-100 text-stone-600"
                                                }`}>
                                                    {rule.severity}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-stone-600">
                                                {rule.rule_type.includes("rate") || rule.rule_type.includes("quota")
                                                    ? `${(rule.threshold * 100).toFixed(0)}%`
                                                    : rule.rule_type.includes("latency")
                                                        ? `${rule.threshold.toLocaleString()}ms`
                                                        : rule.threshold
                                                }
                                            </td>
                                            <td className="px-4 py-3 text-stone-500">{rule.window_minutes}m</td>
                                            <td className="px-4 py-3 text-stone-500">{rule.cooldown_minutes}m</td>
                                            <td className="px-4 py-3">
                                                <button
                                                    onClick={() => handleDeleteRule(rule.id)}
                                                    className="p-1 rounded hover:bg-red-50 text-stone-400 hover:text-red-500"
                                                >
                                                    <Trash2 className="w-3.5 h-3.5" />
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

function SummaryCard({ label, count, color, bg }: { label: string; count: number; color: string; bg: string }) {
    return (
        <div className={`${bg} rounded-lg p-4 border border-stone-200/60`}>
            <p className="text-xs text-stone-500 uppercase tracking-wider">{label}</p>
            <p className={`text-2xl font-bold mt-1 ${count > 0 ? color : "text-stone-300"}`}>{count}</p>
        </div>
    );
}
