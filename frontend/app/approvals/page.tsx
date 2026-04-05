"use client";

import { useEffect, useState } from "react";
import {
    ShieldCheck, Clock, CheckCircle, XCircle, AlertCircle,
    Loader2, ChevronDown, ChevronUp, RefreshCw, AlertTriangle,
    DollarSign, Globe, Trash2, Lightbulb, Info,
} from "lucide-react";
import { approvalsApi, agentsApi, type ApprovalRequest, type Agent } from "@/lib/api";
import { wsClient } from "@/lib/ws";

// ─── Config ──────────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
    pending:  { icon: <Clock className="w-4 h-4 text-amber-500" />,        label: "Pending",  cls: "bg-amber-50 text-amber-700 border-amber-200" },
    approved: { icon: <CheckCircle className="w-4 h-4 text-green-500" />,  label: "Approved", cls: "bg-green-50 text-green-700 border-green-200" },
    rejected: { icon: <XCircle className="w-4 h-4 text-red-500" />,        label: "Rejected", cls: "bg-red-50 text-red-700 border-red-200" },
    expired:  { icon: <AlertCircle className="w-4 h-4 text-stone-400" />,  label: "Expired",  cls: "bg-stone-50 text-stone-500 border-stone-200" },
};

const CATEGORY_CONFIG: Record<string, { label: string; cls: string; icon: React.ReactNode }> = {
    financial:   { label: "Financial",   cls: "bg-red-50 text-red-700 border-red-200",       icon: <DollarSign className="w-3 h-3" /> },
    external:    { label: "External",    cls: "bg-purple-50 text-purple-700 border-purple-200", icon: <Globe className="w-3 h-3" /> },
    destructive: { label: "Destructive", cls: "bg-orange-50 text-orange-700 border-orange-200", icon: <Trash2 className="w-3 h-3" /> },
    strategic:   { label: "Strategic",   cls: "bg-blue-50 text-blue-700 border-blue-200",     icon: <Lightbulb className="w-3 h-3" /> },
    general:     { label: "General",     cls: "bg-stone-50 text-stone-600 border-stone-200",  icon: <Info className="w-3 h-3" /> },
};

const RISK_CONFIG: Record<string, { label: string; cls: string }> = {
    critical: { label: "Critical", cls: "bg-red-100 text-red-800 border-red-300" },
    high:     { label: "High",     cls: "bg-orange-100 text-orange-800 border-orange-300" },
    medium:   { label: "Medium",   cls: "bg-amber-100 text-amber-800 border-amber-300" },
    low:      { label: "Low",      cls: "bg-green-100 text-green-800 border-green-300" },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function ExpiryCountdown({ expiresAt }: { expiresAt: string }) {
    const [remaining, setRemaining] = useState("");

    useEffect(() => {
        function calc() {
            const diff = new Date(expiresAt).getTime() - Date.now();
            if (diff <= 0) { setRemaining("Expired"); return; }
            const m = Math.floor(diff / 60000);
            const s = Math.floor((diff % 60000) / 1000);
            setRemaining(m > 0 ? `${m}m ${s}s` : `${s}s`);
        }
        calc();
        const id = setInterval(calc, 1000);
        return () => clearInterval(id);
    }, [expiresAt]);

    return (
        <span className={`text-xs font-medium ${remaining === "Expired" ? "text-red-500" : "text-amber-600"}`}>
            ⏱ {remaining}
        </span>
    );
}

// ─── Approval Card ────────────────────────────────────────────────────────────

function ApprovalCard({
    req,
    agentMap,
    onDecision,
}: {
    req: ApprovalRequest;
    agentMap: Record<string, string>;
    onDecision: (id: string, decision: "approve" | "reject", note: string) => Promise<void>;
}) {
    const [expanded, setExpanded] = useState(req.status === "pending");
    const [note, setNote] = useState("");
    const [deciding, setDeciding] = useState<"approve" | "reject" | null>(null);

    const statusCfg = STATUS_CONFIG[req.status];
    const catCfg = req.category ? CATEGORY_CONFIG[req.category] ?? CATEGORY_CONFIG.general : null;
    const riskCfg = req.risk_level ? RISK_CONFIG[req.risk_level] : null;
    const agentName = req.requester_agent_id ? (agentMap[req.requester_agent_id] ?? req.requester_agent_id.slice(0, 8)) : null;

    async function handleDecision(action: "approve" | "reject") {
        setDeciding(action);
        try { await onDecision(req.id, action, note); }
        finally { setDeciding(null); }
    }

    return (
        <div className={`bg-white rounded-xl border shadow-sm overflow-hidden ${req.status === "pending" ? "border-amber-200" : "border-stone-200"}`}>
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 cursor-pointer" onClick={() => setExpanded(!expanded)}>
                <div className="flex items-center gap-3 min-w-0">
                    {statusCfg.icon}
                    <div className="min-w-0">
                        <h3 className="font-semibold text-stone-900 truncate">{req.title}</h3>
                        <p className="text-xs text-stone-500 flex items-center gap-2 flex-wrap">
                            <span>{new Date(req.created_at).toLocaleString()}</span>
                            {agentName && <span>· by <span className="font-medium text-stone-700">{agentName}</span></span>}
                            {req.workflow_id && <span>· workflow {req.workflow_id.slice(0, 8)}</span>}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                    {catCfg && (
                        <span className={`hidden sm:flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${catCfg.cls}`}>
                            {catCfg.icon} {catCfg.label}
                        </span>
                    )}
                    {riskCfg && (
                        <span className={`hidden sm:inline text-xs font-medium px-2 py-0.5 rounded-full border ${riskCfg.cls}`}>
                            {riskCfg.label} risk
                        </span>
                    )}
                    <span className={`text-xs font-medium px-2.5 py-1 rounded-full border ${statusCfg.cls}`}>{statusCfg.label}</span>
                    {expanded ? <ChevronUp className="w-4 h-4 text-stone-400" /> : <ChevronDown className="w-4 h-4 text-stone-400" />}
                </div>
            </div>

            {/* Body */}
            {expanded && (
                <div className="border-t border-stone-100 px-5 py-4 space-y-4">
                    {/* Mobile badges */}
                    <div className="flex gap-2 sm:hidden">
                        {catCfg && (
                            <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${catCfg.cls}`}>
                                {catCfg.icon} {catCfg.label}
                            </span>
                        )}
                        {riskCfg && (
                            <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${riskCfg.cls}`}>
                                {riskCfg.label} risk
                            </span>
                        )}
                    </div>

                    {req.status === "pending" && req.expires_at && (
                        <div className="flex items-center gap-2">
                            <ExpiryCountdown expiresAt={req.expires_at} />
                        </div>
                    )}

                    {req.description && (
                        <div>
                            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Description</p>
                            <p className="text-sm text-stone-700">{req.description}</p>
                        </div>
                    )}

                    {req.context && (
                        <div className="space-y-3">
                            {req.context.reasoning && (
                                <div>
                                    <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Reasoning</p>
                                    <p className="text-sm text-stone-700 bg-stone-50 rounded-lg px-3 py-2">{req.context.reasoning}</p>
                                </div>
                            )}
                            {req.context.alternatives && (
                                <div>
                                    <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Alternatives Considered</p>
                                    <p className="text-sm text-stone-700 bg-stone-50 rounded-lg px-3 py-2">{req.context.alternatives}</p>
                                </div>
                            )}
                            {req.context.risk_assessment && (
                                <div>
                                    <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Risk Assessment</p>
                                    <p className="text-sm text-stone-700 bg-amber-50 rounded-lg px-3 py-2">{req.context.risk_assessment}</p>
                                </div>
                            )}
                            {req.context.recommended_action && (
                                <div>
                                    <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Recommended Action</p>
                                    <p className="text-sm text-stone-700 bg-green-50 rounded-lg px-3 py-2">{req.context.recommended_action}</p>
                                </div>
                            )}
                            {/* Legacy: workflow input context */}
                            {req.context.input && !req.context.reasoning && (
                                <div>
                                    <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Workflow Input</p>
                                    <pre className="text-xs bg-stone-900 text-stone-200 rounded-lg p-3 overflow-auto max-h-48 whitespace-pre-wrap">{req.context.input}</pre>
                                </div>
                            )}
                        </div>
                    )}

                    {req.action_payload && (
                        <div>
                            <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Action if Approved</p>
                            <pre className="text-xs bg-stone-900 text-stone-200 rounded-lg p-3 overflow-auto max-h-32 whitespace-pre-wrap">
                                {JSON.stringify(req.action_payload, null, 2)}
                            </pre>
                        </div>
                    )}

                    {req.status === "pending" && (
                        <div className="space-y-3 pt-2 border-t border-stone-100">
                            <div>
                                <label className="block text-xs font-semibold text-stone-500 uppercase tracking-wide mb-1">Note (optional)</label>
                                <textarea
                                    className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 resize-none h-16"
                                    placeholder="Add a note for the audit log..."
                                    value={note}
                                    onChange={e => setNote(e.target.value)}
                                />
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => handleDecision("approve")}
                                    disabled={!!deciding}
                                    className="flex-1 py-2 text-sm font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
                                >
                                    {deciding === "approve" ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                                    Approve & Execute
                                </button>
                                <button
                                    onClick={() => handleDecision("reject")}
                                    disabled={!!deciding}
                                    className="flex-1 py-2 text-sm font-medium rounded-lg bg-red-100 text-red-700 hover:bg-red-200 disabled:opacity-50 flex items-center justify-center gap-2"
                                >
                                    {deciding === "reject" ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />}
                                    Reject
                                </button>
                            </div>
                        </div>
                    )}

                    {req.status !== "pending" && (
                        <div className="pt-2 border-t border-stone-100 text-xs text-stone-500">
                            Decided {req.decided_at ? new Date(req.decided_at).toLocaleString() : "—"}
                            {req.reviewer_note && <span> · &ldquo;{req.reviewer_note}&rdquo;</span>}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const RISK_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

export default function ApprovalsPage() {
    const [requests, setRequests] = useState<ApprovalRequest[]>([]);
    const [agentMap, setAgentMap] = useState<Record<string, string>>({});
    const [loading, setLoading] = useState(true);
    const [tab, setTab] = useState<"pending" | "history">("pending");
    const [historyFilter, setHistoryFilter] = useState<string>("approved");
    const [refreshing, setRefreshing] = useState(false);

    async function load(showRefreshing = false) {
        if (showRefreshing) setRefreshing(true);
        try {
            const status = tab === "pending" ? "pending" : historyFilter;
            const [data, agentsData] = await Promise.all([
                approvalsApi.list({ status }),
                agentsApi.list(),
            ]);
            setRequests(data);
            const map: Record<string, string> = {};
            for (const a of agentsData) map[a.id] = a.name;
            setAgentMap(map);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }

    useEffect(() => { load(); }, [tab, historyFilter]);

    // Real-time WebSocket updates
    useEffect(() => {
        const unsub = wsClient.on("approval_requested", () => {
            if (tab === "pending") load();
        });
        const unsub2 = wsClient.on("approval_decided", () => {
            load();
        });
        return () => { unsub(); unsub2(); };
    }, [tab, historyFilter]);

    async function handleDecision(id: string, action: "approve" | "reject", note: string) {
        const updated = action === "approve"
            ? await approvalsApi.approve(id, note)
            : await approvalsApi.reject(id, note);
        setRequests(prev => prev.map(r => r.id === id ? updated : r).filter(r =>
            tab === "pending" ? r.status === "pending" : r.status !== "pending"
        ));
    }

    const sorted = [...requests].sort((a, b) =>
        (RISK_ORDER[a.risk_level ?? "medium"] ?? 2) - (RISK_ORDER[b.risk_level ?? "medium"] ?? 2)
    );
    const pendingCount = tab === "pending" ? sorted.length : 0;

    if (loading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="w-6 h-6 animate-spin text-stone-600" /></div>;
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-6 py-4 border-b border-stone-200 bg-white flex items-center justify-between gap-4">
                <div>
                    <h1 className="text-xl font-semibold text-stone-900 flex items-center gap-2">
                        <ShieldCheck className="w-5 h-5 text-red-500" />
                        Approval Queue
                        {pendingCount > 0 && (
                            <span className="bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-full">{pendingCount}</span>
                        )}
                    </h1>
                    <p className="text-sm text-stone-500">Review and approve agent actions requiring human sign-off</p>
                </div>
                <button
                    onClick={() => load(true)}
                    disabled={refreshing}
                    className="p-2 rounded-lg border border-stone-200 hover:bg-stone-50 text-stone-500"
                >
                    <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
                </button>
            </div>

            {/* Tabs */}
            <div className="px-6 pt-4 pb-0 bg-white border-b border-stone-200 flex items-center gap-1">
                <button
                    onClick={() => setTab("pending")}
                    className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${tab === "pending" ? "border-stone-600 text-stone-700" : "border-transparent text-stone-500 hover:text-stone-700"}`}
                >
                    Pending
                    {tab === "pending" && pendingCount > 0 && (
                        <span className="ml-2 bg-amber-100 text-amber-700 text-xs font-bold px-1.5 py-0.5 rounded-full">{pendingCount}</span>
                    )}
                </button>
                <button
                    onClick={() => setTab("history")}
                    className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${tab === "history" ? "border-stone-600 text-stone-700" : "border-transparent text-stone-500 hover:text-stone-700"}`}
                >
                    History
                </button>
                {tab === "history" && (
                    <div className="ml-auto mb-1">
                        <select
                            className="border border-stone-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={historyFilter}
                            onChange={e => setHistoryFilter(e.target.value)}
                        >
                            <option value="approved">Approved</option>
                            <option value="rejected">Rejected</option>
                            <option value="expired">Expired</option>
                        </select>
                    </div>
                )}
            </div>

            {/* Risk legend for pending tab */}
            {tab === "pending" && sorted.length > 0 && (
                <div className="px-6 py-2 bg-stone-50 border-b border-stone-100 flex items-center gap-3 flex-wrap text-xs text-stone-500">
                    <AlertTriangle className="w-3.5 h-3.5" /> Sorted by risk:
                    {Object.entries(RISK_CONFIG).map(([k, v]) => (
                        <span key={k} className={`px-1.5 py-0.5 rounded border font-medium ${v.cls}`}>{v.label}</span>
                    ))}
                </div>
            )}

            {/* List */}
            <div className="flex-1 overflow-y-auto p-6">
                {sorted.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-64 text-stone-400">
                        <ShieldCheck className="w-12 h-12 mb-3 opacity-30" />
                        <p className="text-sm">
                            {tab === "pending" ? "No pending approvals — all clear!" : "No requests found"}
                        </p>
                    </div>
                ) : (
                    <div className="space-y-3 max-w-3xl">
                        {sorted.map(req => (
                            <ApprovalCard key={req.id} req={req} agentMap={agentMap} onDecision={handleDecision} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
