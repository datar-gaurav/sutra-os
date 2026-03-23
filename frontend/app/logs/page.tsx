"use client";

import { useEffect, useState, useCallback } from "react";
import {
    AlertTriangle, ChevronDown, ChevronRight, Clock, Filter,
    RefreshCw, ScrollText, Search, ShieldCheck, Terminal,
    CheckCircle, XCircle, Wrench,
} from "lucide-react";
import {
    agentsApi, tracesApi, auditApi,
    type Agent, type ExecutionTrace, type AuditEntry,
} from "@/lib/api";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function ts(iso: string) {
    return new Date(iso).toLocaleString(undefined, {
        month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
}

function truncate(s: string, n = 120) {
    return s.length > n ? s.slice(0, n) + "…" : s;
}

// ─── Trace row ───────────────────────────────────────────────────────────────

function TraceRow({ trace, agentName }: { trace: ExecutionTrace; agentName: string }) {
    const [expanded, setExpanded] = useState(false);

    return (
        <>
            <tr
                className="hover:bg-stone-50/60 dark:hover:bg-stone-800/20 cursor-pointer transition-colors"
                onClick={() => setExpanded(e => !e)}
            >
                <td className="px-4 py-3 font-mono text-[11px] text-stone-400 whitespace-nowrap">
                    {ts(trace.created_at)}
                </td>
                <td className="px-4 py-3">
                    <span className="text-sm font-medium text-gray-900 dark:text-white">{agentName}</span>
                    <span className="block text-[10px] font-mono text-stone-400 mt-0.5">{trace.agent_id.slice(0, 8)}…</span>
                </td>
                <td className="px-4 py-3 text-[12px] text-stone-600 dark:text-stone-400 max-w-xs">
                    {truncate(trace.input_message)}
                </td>
                <td className="px-4 py-3">
                    {trace.had_error ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                            <XCircle className="w-3 h-3" /> Error
                        </span>
                    ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
                            <CheckCircle className="w-3 h-3" /> OK
                        </span>
                    )}
                </td>
                <td className="px-4 py-3 text-[12px] font-mono text-stone-500">
                    {trace.latency_ms != null ? `${trace.latency_ms}ms` : "—"}
                </td>
                <td className="px-4 py-3 text-[12px] text-stone-500">
                    {trace.tool_calls.length > 0
                        ? <span className="flex items-center gap-1"><Wrench className="w-3 h-3" />{trace.tool_calls.length}</span>
                        : "—"}
                </td>
                <td className="px-4 py-2 text-stone-400">
                    {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </td>
            </tr>

            {expanded && (
                <tr className="bg-stone-50 dark:bg-stone-900/40">
                    <td colSpan={7} className="px-6 py-4">
                        <div className="space-y-3 text-[12px]">
                            {/* Input */}
                            <div>
                                <p className="font-semibold text-stone-500 uppercase tracking-wider text-[10px] mb-1">Input</p>
                                <p className="text-stone-800 dark:text-stone-200 leading-relaxed whitespace-pre-wrap">{trace.input_message}</p>
                            </div>

                            {/* Output or error */}
                            {trace.had_error ? (
                                <div>
                                    <p className="font-semibold text-red-500 uppercase tracking-wider text-[10px] mb-1">Error</p>
                                    <p className="text-red-600 dark:text-red-400 font-mono leading-relaxed">{trace.error_message}</p>
                                </div>
                            ) : trace.output_message && (
                                <div>
                                    <p className="font-semibold text-stone-500 uppercase tracking-wider text-[10px] mb-1">Output</p>
                                    <p className="text-stone-800 dark:text-stone-200 leading-relaxed whitespace-pre-wrap">{trace.output_message}</p>
                                </div>
                            )}

                            {/* Tool calls */}
                            {trace.tool_calls.length > 0 && (
                                <div>
                                    <p className="font-semibold text-stone-500 uppercase tracking-wider text-[10px] mb-2">Tool Calls</p>
                                    <div className="space-y-2">
                                        {trace.tool_calls.map((tc, i) => (
                                            <div key={i} className="rounded-lg border border-stone-200 dark:border-stone-700 overflow-hidden">
                                                <div className="flex items-center gap-2 px-3 py-1.5 bg-stone-100 dark:bg-stone-800 border-b border-stone-200 dark:border-stone-700">
                                                    <Wrench className="w-3 h-3 text-stone-600" />
                                                    <span className="font-mono font-semibold text-stone-700 dark:text-stone-500">{tc.name}</span>
                                                </div>
                                                <div className="grid grid-cols-2 divide-x divide-stone-200 dark:divide-stone-700">
                                                    <div className="p-3">
                                                        <p className="text-[10px] text-stone-400 uppercase mb-1">Input</p>
                                                        <pre className="text-[11px] font-mono text-stone-600 dark:text-stone-300 whitespace-pre-wrap break-all">{tc.input}</pre>
                                                    </div>
                                                    <div className="p-3">
                                                        <p className="text-[10px] text-stone-400 uppercase mb-1">Output</p>
                                                        <pre className="text-[11px] font-mono text-stone-600 dark:text-stone-300 whitespace-pre-wrap break-all">{tc.output ?? "—"}</pre>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Meta */}
                            <div className="flex items-center gap-4 text-[10px] text-stone-400 font-mono pt-1 border-t border-stone-200 dark:border-stone-700">
                                <span>trace: {trace.id}</span>
                                {trace.request_id && <span>rid: {trace.request_id}</span>}
                                {trace.conversation_id && <span>conv: {trace.conversation_id.slice(0, 8)}…</span>}
                            </div>
                        </div>
                    </td>
                </tr>
            )}
        </>
    );
}

// ─── Audit row ───────────────────────────────────────────────────────────────

const ACTION_COLORS: Record<string, string> = {
    "agent.create": "bg-stone-200 text-stone-700 dark:bg-stone-800/30 dark:text-stone-500",
    "agent.update": "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-400",
    "agent.delete": "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    "agent.start":  "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
    "agent.stop":   "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

function AuditRow({ entry }: { entry: AuditEntry }) {
    const [expanded, setExpanded] = useState(false);
    const colorClass = ACTION_COLORS[entry.action] ?? "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300";

    return (
        <>
            <tr
                className="hover:bg-stone-50/60 dark:hover:bg-stone-800/20 cursor-pointer transition-colors"
                onClick={() => setExpanded(e => !e)}
            >
                <td className="px-4 py-3 font-mono text-[11px] text-stone-400 whitespace-nowrap">
                    {ts(entry.created_at)}
                </td>
                <td className="px-4 py-3">
                    <span className="text-sm font-medium text-gray-900 dark:text-white capitalize">{entry.actor_type}</span>
                    {entry.actor_id && (
                        <span className="block text-[10px] font-mono text-stone-400 mt-0.5">{entry.actor_id.slice(0, 8)}…</span>
                    )}
                </td>
                <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-medium ${colorClass}`}>
                        {entry.action}
                    </span>
                </td>
                <td className="px-4 py-3 text-[12px] text-stone-600 dark:text-stone-400">
                    {entry.resource_type && <span className="capitalize">{entry.resource_type}</span>}
                    {entry.resource_id && (
                        <span className="block font-mono text-[10px] text-stone-400 mt-0.5">{entry.resource_id.slice(0, 8)}…</span>
                    )}
                </td>
                <td className="px-4 py-3 text-[11px] font-mono text-stone-400">{entry.ip_address ?? "—"}</td>
                <td className="px-4 py-2 text-stone-400">
                    {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </td>
            </tr>

            {expanded && (
                <tr className="bg-stone-50 dark:bg-stone-900/40">
                    <td colSpan={6} className="px-6 py-4">
                        <div className="space-y-2 text-[12px]">
                            {entry.details && (
                                <div>
                                    <p className="font-semibold text-stone-500 uppercase tracking-wider text-[10px] mb-1">Details</p>
                                    <pre className="font-mono text-stone-700 dark:text-stone-300 bg-stone-100 dark:bg-stone-800 rounded p-3 overflow-x-auto text-[11px]">
                                        {JSON.stringify(entry.details, null, 2)}
                                    </pre>
                                </div>
                            )}
                            <div className="flex items-center gap-4 text-[10px] text-stone-400 font-mono pt-1 border-t border-stone-200 dark:border-stone-700">
                                <span>id: {entry.id}</span>
                                {entry.request_id && <span>rid: {entry.request_id}</span>}
                            </div>
                        </div>
                    </td>
                </tr>
            )}
        </>
    );
}

// ─── Main page ───────────────────────────────────────────────────────────────

type Tab = "traces" | "audit";

export default function LogsPage() {
    const [tab, setTab] = useState<Tab>("traces");
    const [agents, setAgents] = useState<Agent[]>([]);

    // Traces state
    const [traces, setTraces] = useState<ExecutionTrace[]>([]);
    const [tracesLoading, setTracesLoading] = useState(false);
    const [selectedAgent, setSelectedAgent] = useState<string>("");
    const [errorsOnly, setErrorsOnly] = useState(false);
    const [traceSearch, setTraceSearch] = useState("");

    // Audit state
    const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
    const [auditLoading, setAuditLoading] = useState(false);
    const [auditAction, setAuditAction] = useState("");
    const [auditResource, setAuditResource] = useState("");
    const [auditSearch, setAuditSearch] = useState("");

    const [lastRefreshed, setLastRefreshed] = useState(new Date());

    // Load agents once
    useEffect(() => { agentsApi.list().then(setAgents); }, []);

    // Load traces when agent selected or tab active
    const loadTraces = useCallback(async () => {
        if (!selectedAgent) return;
        setTracesLoading(true);
        try {
            const data = await tracesApi.byAgent(selectedAgent, 200);
            setTraces(data);
            setLastRefreshed(new Date());
        } finally {
            setTracesLoading(false);
        }
    }, [selectedAgent]);

    useEffect(() => { if (tab === "traces") loadTraces(); }, [tab, loadTraces]);

    // Load audit log
    const loadAudit = useCallback(async () => {
        setAuditLoading(true);
        try {
            const data = await auditApi.list({
                action: auditAction || undefined,
                resource_type: auditResource || undefined,
                limit: 200,
            });
            setAuditEntries(data);
            setLastRefreshed(new Date());
        } finally {
            setAuditLoading(false);
        }
    }, [auditAction, auditResource]);

    useEffect(() => { if (tab === "audit") loadAudit(); }, [tab, loadAudit]);

    // Derived filtered lists
    const filteredTraces = traces.filter(t => {
        if (errorsOnly && !t.had_error) return false;
        if (traceSearch) {
            const q = traceSearch.toLowerCase();
            return t.input_message.toLowerCase().includes(q) ||
                (t.output_message ?? "").toLowerCase().includes(q) ||
                (t.error_message ?? "").toLowerCase().includes(q);
        }
        return true;
    });

    const filteredAudit = auditEntries.filter(e => {
        if (!auditSearch) return true;
        const q = auditSearch.toLowerCase();
        return e.action.toLowerCase().includes(q) ||
            (e.actor_id ?? "").toLowerCase().includes(q) ||
            (e.resource_id ?? "").toLowerCase().includes(q);
    });

    const agentName = (id: string) => agents.find(a => a.id === id)?.name ?? id.slice(0, 8) + "…";

    // Unique action types for filter dropdown
    const actionTypes = [...new Set(auditEntries.map(e => e.action))].sort();

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Logs</h1>
                    <p className="text-gray-500 dark:text-gray-400 mt-1">
                        Execution traces and audit history
                    </p>
                </div>
                <button
                    onClick={tab === "traces" ? loadTraces : loadAudit}
                    className="flex items-center gap-1.5 text-xs text-stone-500 hover:text-stone-700 dark:hover:text-stone-300 transition-colors"
                >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>Refreshed {lastRefreshed.toLocaleTimeString()}</span>
                </button>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 p-1 rounded-xl bg-stone-100 dark:bg-stone-800/50 w-fit">
                {([
                    { id: "traces", label: "Execution Traces", icon: Terminal },
                    { id: "audit",  label: "Audit Log",        icon: ShieldCheck },
                ] as { id: Tab; label: string; icon: React.ComponentType<{ className?: string }> }[]).map(t => (
                    <button
                        key={t.id}
                        onClick={() => setTab(t.id)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                            tab === t.id
                                ? "bg-white dark:bg-stone-700 text-stone-900 dark:text-white shadow-sm"
                                : "text-stone-500 hover:text-stone-700 dark:hover:text-stone-300"
                        }`}
                    >
                        <t.icon className="w-4 h-4" />
                        {t.label}
                    </button>
                ))}
            </div>

            {/* ── Execution Traces tab ──────────────────────────────────── */}
            {tab === "traces" && (
                <div className="space-y-4">
                    {/* Filters */}
                    <div className="glass-card p-4 flex flex-wrap items-center gap-3">
                        <Filter className="w-4 h-4 text-stone-400 flex-shrink-0" />

                        {/* Agent picker */}
                        <select
                            className="px-3 py-1.5 text-sm border rounded-lg bg-white dark:bg-stone-900 border-stone-300 dark:border-stone-600 outline-none focus:ring-1 focus:ring-stone-600"
                            value={selectedAgent}
                            onChange={e => setSelectedAgent(e.target.value)}
                        >
                            <option value="">— Select an agent —</option>
                            {agents.map(a => (
                                <option key={a.id} value={a.id}>{a.name}</option>
                            ))}
                        </select>

                        {/* Errors only toggle */}
                        <label className="flex items-center gap-2 text-sm text-stone-600 dark:text-stone-400 cursor-pointer select-none">
                            <input
                                type="checkbox"
                                className="w-4 h-4 rounded accent-red-500"
                                checked={errorsOnly}
                                onChange={e => setErrorsOnly(e.target.checked)}
                            />
                            Errors only
                        </label>

                        {/* Search */}
                        <div className="relative ml-auto">
                            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-stone-400" />
                            <input
                                type="text"
                                placeholder="Search messages…"
                                className="pl-8 pr-3 py-1.5 text-sm border rounded-lg bg-white dark:bg-stone-900 border-stone-300 dark:border-stone-600 outline-none focus:ring-1 focus:ring-stone-600 w-56"
                                value={traceSearch}
                                onChange={e => setTraceSearch(e.target.value)}
                            />
                        </div>
                    </div>

                    {!selectedAgent ? (
                        <div className="glass-card p-12 text-center text-stone-400">
                            <Terminal className="w-10 h-10 mx-auto mb-3 opacity-40" />
                            <p>Select an agent above to view its execution traces.</p>
                        </div>
                    ) : tracesLoading ? (
                        <div className="glass-card p-12 text-center text-stone-400 text-sm">Loading traces…</div>
                    ) : (
                        <div className="glass-card overflow-hidden">
                            <div className="px-5 py-3 border-b border-stone-200 dark:border-stone-700 flex items-center justify-between">
                                <h2 className="text-sm font-semibold text-stone-700 dark:text-stone-300 flex items-center gap-2">
                                    <Terminal className="w-4 h-4 text-stone-600" />
                                    {agentName(selectedAgent)}
                                </h2>
                                <span className="text-xs text-stone-400">{filteredTraces.length} traces</span>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left">
                                    <thead className="bg-stone-50 dark:bg-stone-800/50 text-xs uppercase font-medium text-stone-500 dark:text-stone-400">
                                        <tr>
                                            <th className="px-4 py-3 whitespace-nowrap">Time</th>
                                            <th className="px-4 py-3">Agent</th>
                                            <th className="px-4 py-3">Input</th>
                                            <th className="px-4 py-3">Status</th>
                                            <th className="px-4 py-3">Latency</th>
                                            <th className="px-4 py-3">Tools</th>
                                            <th className="px-4 py-3 w-8"></th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-stone-200 dark:divide-stone-700/50 bg-white dark:bg-surface-dark3">
                                        {filteredTraces.length === 0 ? (
                                            <tr>
                                                <td colSpan={7} className="text-center py-10 text-stone-400 text-sm">
                                                    No traces found.
                                                </td>
                                            </tr>
                                        ) : (
                                            filteredTraces.map(t => (
                                                <TraceRow key={t.id} trace={t} agentName={agentName(t.agent_id)} />
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* ── Audit Log tab ─────────────────────────────────────────── */}
            {tab === "audit" && (
                <div className="space-y-4">
                    {/* Filters */}
                    <div className="glass-card p-4 flex flex-wrap items-center gap-3">
                        <Filter className="w-4 h-4 text-stone-400 flex-shrink-0" />

                        {/* Action filter */}
                        <select
                            className="px-3 py-1.5 text-sm border rounded-lg bg-white dark:bg-stone-900 border-stone-300 dark:border-stone-600 outline-none focus:ring-1 focus:ring-stone-600"
                            value={auditAction}
                            onChange={e => setAuditAction(e.target.value)}
                        >
                            <option value="">All actions</option>
                            {actionTypes.map(a => <option key={a} value={a}>{a}</option>)}
                        </select>

                        {/* Resource type filter */}
                        <select
                            className="px-3 py-1.5 text-sm border rounded-lg bg-white dark:bg-stone-900 border-stone-300 dark:border-stone-600 outline-none focus:ring-1 focus:ring-stone-600"
                            value={auditResource}
                            onChange={e => setAuditResource(e.target.value)}
                        >
                            <option value="">All resources</option>
                            <option value="agent">Agent</option>
                            <option value="memory">Memory</option>
                        </select>

                        {/* Search */}
                        <div className="relative ml-auto">
                            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-stone-400" />
                            <input
                                type="text"
                                placeholder="Search audit log…"
                                className="pl-8 pr-3 py-1.5 text-sm border rounded-lg bg-white dark:bg-stone-900 border-stone-300 dark:border-stone-600 outline-none focus:ring-1 focus:ring-stone-600 w-56"
                                value={auditSearch}
                                onChange={e => setAuditSearch(e.target.value)}
                            />
                        </div>
                    </div>

                    <div className="glass-card overflow-hidden">
                        <div className="px-5 py-3 border-b border-stone-200 dark:border-stone-700 flex items-center justify-between">
                            <h2 className="text-sm font-semibold text-stone-700 dark:text-stone-300 flex items-center gap-2">
                                <ShieldCheck className="w-4 h-4 text-stone-600" />
                                Audit Log
                            </h2>
                            <span className="text-xs text-stone-400">{filteredAudit.length} entries</span>
                        </div>

                        {auditLoading ? (
                            <div className="p-10 text-center text-stone-400 text-sm">Loading audit log…</div>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm text-left">
                                    <thead className="bg-stone-50 dark:bg-stone-800/50 text-xs uppercase font-medium text-stone-500 dark:text-stone-400">
                                        <tr>
                                            <th className="px-4 py-3 whitespace-nowrap">Time</th>
                                            <th className="px-4 py-3">Actor</th>
                                            <th className="px-4 py-3">Action</th>
                                            <th className="px-4 py-3">Resource</th>
                                            <th className="px-4 py-3">IP</th>
                                            <th className="px-4 py-3 w-8"></th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-stone-200 dark:divide-stone-700/50 bg-white dark:bg-surface-dark3">
                                        {filteredAudit.length === 0 ? (
                                            <tr>
                                                <td colSpan={6} className="text-center py-10 text-stone-400 text-sm">
                                                    No audit entries found.
                                                </td>
                                            </tr>
                                        ) : (
                                            filteredAudit.map(e => <AuditRow key={e.id} entry={e} />)
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
