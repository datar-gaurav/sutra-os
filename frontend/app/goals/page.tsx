"use client";

import { useEffect, useState } from "react";
import {
    Target, Plus, X, Check, Loader2, ChevronDown, ChevronRight,
    RefreshCw, Lightbulb, Zap, AlertTriangle, Bot,
    Clock, CheckCircle2, PauseCircle, XCircle,
    Calendar, Flag, Edit3, Trash2, MessageSquare,
} from "lucide-react";
import {
    agentsApi, goalsApi, checkinsApi, initiativesApi,
    type Agent, type AgentGoal, type AgentCheckIn, type AgentInitiative,
    type GoalStatus, type GoalPriority,
} from "@/lib/api";

// ─── Helpers ─────────────────────────────────────────────────────────────────

const GOAL_STATUS_CONFIG: Record<GoalStatus, { label: string; color: string; icon: React.ReactNode }> = {
    active:    { label: "Active",    color: "text-green-600 bg-green-50 border-green-200",  icon: <CheckCircle2 className="w-3.5 h-3.5" /> },
    paused:    { label: "Paused",    color: "text-amber-600 bg-amber-50 border-amber-200",  icon: <PauseCircle className="w-3.5 h-3.5" /> },
    completed: { label: "Completed", color: "text-blue-600 bg-blue-50 border-blue-200",    icon: <Check className="w-3.5 h-3.5" /> },
    abandoned: { label: "Abandoned", color: "text-stone-400 bg-stone-50 border-stone-200", icon: <XCircle className="w-3.5 h-3.5" /> },
};

const PRIORITY_CONFIG: Record<GoalPriority, { label: string; dot: string }> = {
    critical: { label: "Critical", dot: "bg-red-500" },
    high:     { label: "High",     dot: "bg-orange-400" },
    medium:   { label: "Medium",   dot: "bg-amber-400" },
    low:      { label: "Low",      dot: "bg-stone-300" },
};

const INIT_STATUS_CONFIG = {
    pending:     { label: "Pending",     cls: "bg-amber-50 text-amber-700 border-amber-200" },
    approved:    { label: "Approved",    cls: "bg-green-50 text-green-700 border-green-200" },
    rejected:    { label: "Rejected",    cls: "bg-red-50 text-red-700 border-red-200" },
    implemented: { label: "Implemented", cls: "bg-blue-50 text-blue-700 border-blue-200" },
};

function fmt(iso: string) {
    return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// ─── Goal Modal ───────────────────────────────────────────────────────────────
function GoalModal({
    goal,
    agents,
    defaultAgentId,
    onClose,
    onSave,
}: {
    goal?: AgentGoal | null;
    agents: Agent[];
    defaultAgentId?: string;
    onClose: () => void;
    onSave: (data: Partial<AgentGoal>) => Promise<void>;
}) {
    const [agentId, setAgentId] = useState(goal?.agent_id || defaultAgentId || "");
    const [title, setTitle] = useState(goal?.title || "");
    const [description, setDescription] = useState(goal?.description || "");
    const [priority, setPriority] = useState<GoalPriority>(goal?.priority || "medium");
    const [deadline, setDeadline] = useState(goal?.deadline || "");
    const [successCriteria, setSuccessCriteria] = useState(goal?.success_criteria || "");
    const [saving, setSaving] = useState(false);

    async function handleSave() {
        if (!title || !agentId) return;
        setSaving(true);
        try {
            await onSave({ agent_id: agentId, title, description: description || undefined, priority, deadline: deadline || undefined, success_criteria: successCriteria || undefined });
            onClose();
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between mb-5">
                    <h2 className="text-lg font-semibold text-stone-900">{goal ? "Edit Goal" : "New Goal"}</h2>
                    <button onClick={onClose} className="p-1.5 hover:bg-stone-100 rounded-lg"><X className="w-4 h-4" /></button>
                </div>
                <div className="space-y-4">
                    {!goal && (
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Agent *</label>
                            <select className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" value={agentId} onChange={e => setAgentId(e.target.value)}>
                                <option value="">Select agent...</option>
                                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                            </select>
                        </div>
                    )}
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Title *</label>
                        <input className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" value={title} onChange={e => setTitle(e.target.value)} placeholder="Ship v2.0 of the product by Q2" />
                    </div>
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Description</label>
                        <textarea className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 resize-none h-20" value={description} onChange={e => setDescription(e.target.value)} placeholder="Context and details..." />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Priority</label>
                            <select className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" value={priority} onChange={e => setPriority(e.target.value as GoalPriority)}>
                                {Object.entries(PRIORITY_CONFIG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Deadline</label>
                            <input type="date" className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" value={deadline} onChange={e => setDeadline(e.target.value)} />
                        </div>
                    </div>
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Success Criteria</label>
                        <textarea className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 resize-none h-16" value={successCriteria} onChange={e => setSuccessCriteria(e.target.value)} placeholder="How will you know this goal is achieved?" />
                    </div>
                </div>
                <div className="flex gap-3 mt-6">
                    <button onClick={onClose} className="flex-1 py-2 border border-stone-200 rounded-lg text-sm text-stone-600 hover:bg-stone-50">Cancel</button>
                    <button onClick={handleSave} disabled={!title || !agentId || saving} className="flex-1 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50 flex items-center justify-center gap-2">
                        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                        {goal ? "Save" : "Create Goal"}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Check-in Card ────────────────────────────────────────────────────────────
function CheckInCard({ checkin, onDelete }: { checkin: AgentCheckIn; onDelete: () => Promise<void> }) {
    const [expanded, setExpanded] = useState(false);
    const [deleting, setDeleting] = useState(false);

    async function handleDelete(e: React.MouseEvent) {
        e.stopPropagation();
        if (!confirm("Delete this check-in?")) return;
        setDeleting(true);
        try {
            await onDelete();
        } catch {
            setDeleting(false);
        }
    }

    return (
        <div className="bg-stone-50 border border-stone-100 rounded-xl overflow-hidden group">
            <button
                className="w-full flex items-center justify-between px-4 py-3 text-left"
                onClick={() => setExpanded(!expanded)}
            >
                <div className="flex items-center gap-3 min-w-0">
                    {checkin.had_error
                        ? <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
                        : <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
                    }
                    <div className="min-w-0">
                        <p className="text-xs text-stone-500">{fmt(checkin.created_at)}</p>
                        <p className="text-sm text-stone-700 truncate mt-0.5">{checkin.summary || "Check-in completed"}</p>
                    </div>
                </div>
                <div className="flex items-center gap-3 shrink-0 ml-3">
                    {checkin.stuck_items.length > 0 && (
                        <span className="bg-amber-100 text-amber-700 text-[10px] font-bold px-2 py-0.5 rounded-full">
                            {checkin.stuck_items.length} stuck
                        </span>
                    )}
                    {checkin.blockers.length > 0 && (
                        <span className="bg-red-100 text-red-600 text-[10px] font-bold px-2 py-0.5 rounded-full">
                            {checkin.blockers.length} blockers
                        </span>
                    )}
                    <button
                        onClick={handleDelete}
                        disabled={deleting}
                        className="p-1 rounded-md text-stone-300 hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
                        title="Delete check-in"
                    >
                        {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    </button>
                    {expanded ? <ChevronDown className="w-4 h-4 text-stone-400" /> : <ChevronRight className="w-4 h-4 text-stone-400" />}
                </div>
            </button>

            {expanded && (
                <div className="px-4 pb-4 space-y-3 border-t border-stone-100 pt-3">
                    {checkin.goals_reviewed.length > 0 && (
                        <div>
                            <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-2">Goals</p>
                            {checkin.goals_reviewed.map((g, i) => (
                                <div key={i} className="flex items-start gap-2 text-xs mb-1.5">
                                    <span className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold ${g.status_update === "on_track" ? "bg-green-100 text-green-700" : g.status_update === "blocked" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>
                                        {g.status_update}
                                    </span>
                                    <span className="text-stone-600">{g.title}: <span className="text-stone-500">{g.progress}</span></span>
                                </div>
                            ))}
                        </div>
                    )}
                    {checkin.blockers.length > 0 && (
                        <div>
                            <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wide mb-1">Blockers</p>
                            {checkin.blockers.map((b, i) => <p key={i} className="text-xs text-stone-600 flex gap-1.5"><span>•</span>{b}</p>)}
                        </div>
                    )}
                    {checkin.proposed_actions.length > 0 && (
                        <div>
                            <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-1">Next Actions</p>
                            {checkin.proposed_actions.map((a, i) => <p key={i} className="text-xs text-stone-600 flex gap-1.5"><span>→</span>{a}</p>)}
                        </div>
                    )}
                    {checkin.stuck_items.length > 0 && (
                        <div>
                            <p className="text-[10px] font-semibold text-amber-500 uppercase tracking-wide mb-1">Stuck Items</p>
                            {checkin.stuck_items.map((s, i) => (
                                <p key={i} className="text-xs text-stone-600">{s.title} — {s.days_stale}d without update</p>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ─── Goal Card ────────────────────────────────────────────────────────────────
function GoalCard({
    goal,
    agentName,
    onEdit,
    onDelete,
    onStatusChange,
    onAddNote,
}: {
    goal: AgentGoal;
    agentName: string;
    onEdit: () => void;
    onDelete: () => void;
    onStatusChange: (status: GoalStatus) => void;
    onAddNote: (note: string) => Promise<void>;
}) {
    const [expanded, setExpanded] = useState(false);
    const [noteInput, setNoteInput] = useState("");
    const [savingNote, setSavingNote] = useState(false);
    const cfg = GOAL_STATUS_CONFIG[goal.status];
    const pri = PRIORITY_CONFIG[goal.priority];

    async function handleNote() {
        if (!noteInput.trim()) return;
        setSavingNote(true);
        await onAddNote(noteInput.trim());
        setNoteInput("");
        setSavingNote(false);
    }

    return (
        <div className="bg-white border border-stone-200 rounded-xl shadow-sm overflow-hidden">
            <div className="flex items-start gap-3 px-4 py-3">
                <div className={`shrink-0 mt-0.5 w-2 h-2 rounded-full ${pri.dot}`} title={pri.label} />
                <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                        <button onClick={() => setExpanded(!expanded)} className="text-sm font-semibold text-stone-800 text-left hover:text-stone-700 flex-1">
                            {goal.title}
                        </button>
                        <div className="flex items-center gap-1.5 shrink-0">
                            <span className={`flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border ${cfg.color}`}>
                                {cfg.icon}{cfg.label}
                            </span>
                            <button onClick={onEdit} className="p-1 text-stone-300 hover:text-stone-600 rounded"><Edit3 className="w-3.5 h-3.5" /></button>
                            <button onClick={onDelete} className="p-1 text-stone-300 hover:text-red-400 rounded"><Trash2 className="w-3.5 h-3.5" /></button>
                        </div>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[10px] text-stone-400">
                        <span>{agentName}</span>
                        {goal.deadline && <span className="flex items-center gap-1"><Calendar className="w-2.5 h-2.5" />{goal.deadline}</span>}
                    </div>
                </div>
            </div>

            {expanded && (
                <div className="border-t border-stone-100 px-4 py-3 space-y-3">
                    {goal.description && <p className="text-xs text-stone-600">{goal.description}</p>}
                    {goal.success_criteria && (
                        <div>
                            <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-1">Success Criteria</p>
                            <p className="text-xs text-stone-600">{goal.success_criteria}</p>
                        </div>
                    )}

                    {/* Status quick-change */}
                    <div>
                        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-1.5">Change Status</p>
                        <div className="flex flex-wrap gap-1.5">
                            {(Object.keys(GOAL_STATUS_CONFIG) as GoalStatus[]).map(s => (
                                <button
                                    key={s}
                                    onClick={() => onStatusChange(s)}
                                    className={`text-[10px] px-2.5 py-1 rounded-full border font-medium transition-all ${goal.status === s ? GOAL_STATUS_CONFIG[s].color + " ring-1 ring-offset-1" : "border-stone-200 text-stone-500 hover:bg-stone-50"}`}
                                >
                                    {GOAL_STATUS_CONFIG[s].label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Progress notes */}
                    {goal.progress_notes.length > 0 && (
                        <div>
                            <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-1.5">Progress Log</p>
                            <div className="space-y-1.5 max-h-32 overflow-y-auto">
                                {[...goal.progress_notes].reverse().map((n, i) => (
                                    <div key={i} className="flex gap-2 text-xs">
                                        <span className="text-stone-300 shrink-0">{new Date(n.timestamp).toLocaleDateString()}</span>
                                        <span className="text-stone-600">{n.note}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Add note */}
                    <div className="flex gap-2">
                        <input
                            className="flex-1 border border-stone-200 rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-stone-500"
                            placeholder="Add progress note..."
                            value={noteInput}
                            onChange={e => setNoteInput(e.target.value)}
                            onKeyDown={e => { if (e.key === "Enter") handleNote(); }}
                        />
                        <button onClick={handleNote} disabled={!noteInput.trim() || savingNote} className="px-3 py-1.5 bg-stone-700 text-white rounded-lg text-xs font-medium disabled:opacity-50">
                            {savingNote ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Add"}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}

// ─── Initiative Card ──────────────────────────────────────────────────────────
function InitiativeCard({
    initiative,
    agentName,
    onApprove,
    onReject,
    onDelete,
}: {
    initiative: AgentInitiative;
    agentName: string;
    onApprove: (note?: string) => Promise<void>;
    onReject: (note?: string) => Promise<void>;
    onDelete: () => Promise<void>;
}) {
    const [expanded, setExpanded] = useState(initiative.status === "pending");
    const [note, setNote] = useState("");
    const [acting, setActing] = useState<"approve" | "reject" | "delete" | null>(null);
    const [error, setError] = useState<string | null>(null);
    const cfg = INIT_STATUS_CONFIG[initiative.status];

    async function handle(e: React.MouseEvent, action: "approve" | "reject") {
        e.stopPropagation();
        setActing(action);
        setError(null);
        try {
            await (action === "approve" ? onApprove(note) : onReject(note));
        } catch (err: any) {
            setError(err.message || "Action failed. Please try again.");
        } finally {
            setActing(null);
        }
    }

    async function handleDelete(e: React.MouseEvent) {
        e.stopPropagation();
        if (!confirm(`Delete initiative "${initiative.title}"?`)) return;
        setActing("delete");
        try {
            await onDelete();
        } catch (err: any) {
            setError(err.message || "Delete failed.");
            setActing(null);
        }
    }

    return (
        <div className={`bg-white border rounded-xl shadow-sm overflow-hidden group ${initiative.status === "pending" ? "border-amber-200" : "border-stone-200"}`}>
            <div className="flex items-center justify-between px-4 py-3 cursor-pointer" onClick={() => setExpanded(!expanded)}>
                <div className="flex items-center gap-3 min-w-0">
                    <Lightbulb className={`w-4 h-4 shrink-0 ${initiative.status === "pending" ? "text-amber-500" : "text-stone-400"}`} />
                    <div className="min-w-0">
                        <h3 className="font-medium text-stone-900 text-sm truncate">{initiative.title}</h3>
                        <p className="text-[10px] text-stone-400">{agentName} · {new Date(initiative.created_at).toLocaleDateString()}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${cfg.cls}`}>{cfg.label}</span>
                    <button
                        onClick={handleDelete}
                        disabled={acting === "delete"}
                        className="p-1 rounded-md text-stone-300 hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
                        title="Delete initiative"
                    >
                        {acting === "delete" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    </button>
                    {expanded ? <ChevronDown className="w-4 h-4 text-stone-400" /> : <ChevronRight className="w-4 h-4 text-stone-400" />}
                </div>
            </div>

            {expanded && (
                <div className="border-t border-stone-100 px-4 py-3 space-y-3">
                    {initiative.description && <p className="text-sm text-stone-700">{initiative.description}</p>}
                    {initiative.rationale && (
                        <div>
                            <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-1">Rationale</p>
                            <p className="text-xs text-stone-600">{initiative.rationale}</p>
                        </div>
                    )}
                    {initiative.proposed_actions.length > 0 && (
                        <div>
                            <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-1">Proposed Actions</p>
                            {initiative.proposed_actions.map((a, i) => <p key={i} className="text-xs text-stone-600">→ {a}</p>)}
                        </div>
                    )}
                    {initiative.estimated_impact && (
                        <p className="text-xs text-stone-500 italic">Impact: {initiative.estimated_impact}</p>
                    )}

                    {initiative.status === "pending" && (
                        <div className="space-y-2 pt-2 border-t border-stone-100">
                            <textarea
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-stone-500 resize-none h-14"
                                placeholder="Reviewer note (optional)..."
                                value={note}
                                onChange={e => setNote(e.target.value)}
                            />
                            {error && (
                                <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
                            )}
                            <div className="flex gap-2">
                                <button onClick={e => handle(e, "approve")} disabled={!!acting} className="flex-1 py-2 text-sm font-medium rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-1.5">
                                    {acting === "approve" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />} Approve
                                </button>
                                <button onClick={e => handle(e, "reject")} disabled={!!acting} className="flex-1 py-2 text-sm font-medium rounded-lg bg-red-100 text-red-700 hover:bg-red-200 disabled:opacity-50 flex items-center justify-center gap-1.5">
                                    {acting === "reject" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />} Reject
                                </button>
                            </div>
                        </div>
                    )}

                    {initiative.status !== "pending" && initiative.reviewer_note && (
                        <p className="text-xs text-stone-400 italic pt-2 border-t border-stone-100">
                            Note: "{initiative.reviewer_note}"
                        </p>
                    )}
                </div>
            )}
        </div>
    );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

type Tab = "goals" | "checkins" | "initiatives";

export default function GoalsPage() {
    const [tab, setTab] = useState<Tab>("goals");
    const [agents, setAgents] = useState<Agent[]>([]);
    const [goals, setGoals] = useState<AgentGoal[]>([]);
    const [checkins, setCheckins] = useState<AgentCheckIn[]>([]);
    const [initiatives, setInitiatives] = useState<AgentInitiative[]>([]);
    const [selectedAgent, setSelectedAgent] = useState<string>("");
    const [loading, setLoading] = useState(true);
    const [goalModal, setGoalModal] = useState<{ open: boolean; goal?: AgentGoal | null }>({ open: false });
    const [runningCheckin, setRunningCheckin] = useState<string | null>(null);
    const [statusFilter, setStatusFilter] = useState<string>("");

    async function loadAll() {
        setLoading(true);
        try {
            const [a, g, c, i] = await Promise.all([
                agentsApi.list(),
                goalsApi.list(selectedAgent ? { agent_id: selectedAgent } : undefined),
                checkinsApi.list(selectedAgent ? { agent_id: selectedAgent } : undefined),
                initiativesApi.list(),
            ]);
            setAgents(a);
            setGoals(g);
            setCheckins(c);
            setInitiatives(i);
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => { loadAll(); }, [selectedAgent]);

    const agentMap = Object.fromEntries(agents.map(a => [a.id, a.name]));

    async function handleSaveGoal(data: Partial<AgentGoal>) {
        if (goalModal.goal) {
            const updated = await goalsApi.update(goalModal.goal.id, data);
            setGoals(prev => prev.map(g => g.id === updated.id ? updated : g));
        } else {
            const created = await goalsApi.create(data);
            setGoals(prev => [created, ...prev]);
        }
    }

    async function handleDeleteGoal(id: string) {
        if (!confirm("Delete this goal?")) return;
        await goalsApi.delete(id);
        setGoals(prev => prev.filter(g => g.id !== id));
    }

    async function handleStatusChange(goal: AgentGoal, status: GoalStatus) {
        const updated = await goalsApi.update(goal.id, { status });
        setGoals(prev => prev.map(g => g.id === updated.id ? updated : g));
    }

    async function handleAddNote(goal: AgentGoal, note: string) {
        const updated = await goalsApi.addProgress(goal.id, note);
        setGoals(prev => prev.map(g => g.id === updated.id ? updated : g));
    }

    async function handleRunCheckin(agentId: string) {
        setRunningCheckin(agentId);
        try {
            await checkinsApi.run(agentId);
            // Poll for new check-in
            setTimeout(async () => {
                const c = await checkinsApi.list(agentId ? { agent_id: agentId } : undefined);
                setCheckins(c);
                const i = await initiativesApi.list();
                setInitiatives(i);
                setRunningCheckin(null);
            }, 8000);
        } catch {
            setRunningCheckin(null);
        }
    }

    async function handleApproveInitiative(id: string, note?: string) {
        const updated = await initiativesApi.approve(id, note);
        setInitiatives(prev => prev.map(i => i.id === updated.id ? updated : i));
    }

    async function handleRejectInitiative(id: string, note?: string) {
        const updated = await initiativesApi.reject(id, note);
        setInitiatives(prev => prev.map(i => i.id === updated.id ? updated : i));
    }

    async function handleDeleteInitiative(id: string) {
        await initiativesApi.delete(id);
        setInitiatives(prev => prev.filter(i => i.id !== id));
    }

    async function handleDeleteCheckin(id: string) {
        await checkinsApi.delete(id);
        setCheckins(prev => prev.filter(c => c.id !== id));
    }

    const filteredGoals = goals.filter(g => !statusFilter || g.status === statusFilter);
    const pendingInitiatives = initiatives.filter(i => i.status === "pending").length;

    if (loading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="w-6 h-6 animate-spin text-stone-600" /></div>;
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-6 py-4 border-b border-stone-200 bg-white flex items-center justify-between gap-4">
                <div>
                    <h1 className="text-xl font-semibold text-stone-900 flex items-center gap-2">
                        <Target className="w-5 h-5 text-stone-600" />
                        Goals & Proactive Behavior
                    </h1>
                    <p className="text-sm text-stone-500">Agent goals, periodic check-ins, and initiative proposals</p>
                </div>
                <div className="flex items-center gap-2">
                    {/* Agent filter */}
                    <select
                        className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                        value={selectedAgent}
                        onChange={e => setSelectedAgent(e.target.value)}
                    >
                        <option value="">All agents</option>
                        {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </select>

                    {tab === "goals" && (
                        <button
                            onClick={() => setGoalModal({ open: true, goal: null })}
                            className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700"
                        >
                            <Plus className="w-4 h-4" /> New Goal
                        </button>
                    )}

                    {selectedAgent && (
                        <button
                            onClick={() => handleRunCheckin(selectedAgent)}
                            disabled={runningCheckin === selectedAgent}
                            className="flex items-center gap-2 px-4 py-2 bg-stone-800 text-white rounded-lg text-sm font-medium hover:bg-stone-900 disabled:opacity-60"
                        >
                            {runningCheckin === selectedAgent
                                ? <Loader2 className="w-4 h-4 animate-spin" />
                                : <RefreshCw className="w-4 h-4" />
                            }
                            Run Check-in
                        </button>
                    )}
                </div>
            </div>

            {/* Tabs */}
            <div className="border-b border-stone-200 bg-white px-6">
                <div className="flex gap-6">
                    {[
                        { key: "goals" as Tab, label: "Goals", count: filteredGoals.length },
                        { key: "checkins" as Tab, label: "Check-ins", count: checkins.length },
                        { key: "initiatives" as Tab, label: "Initiatives", count: pendingInitiatives, badge: true },
                    ].map(({ key, label, count, badge }) => (
                        <button
                            key={key}
                            onClick={() => setTab(key)}
                            className={`py-3 text-sm font-medium border-b-2 transition-colors flex items-center gap-2 ${tab === key ? "border-stone-600 text-stone-700" : "border-transparent text-stone-500 hover:text-stone-700"}`}
                        >
                            {label}
                            {count > 0 && (
                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${badge && pendingInitiatives > 0 ? "bg-amber-500 text-white" : "bg-stone-100 text-stone-500"}`}>
                                    {count}
                                </span>
                            )}
                        </button>
                    ))}
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">

                {/* ── Goals tab ─────────────────────────────────── */}
                {tab === "goals" && (
                    <div className="max-w-3xl space-y-3">
                        {/* Status filter */}
                        <div className="flex gap-2 mb-4 flex-wrap">
                            {["", "active", "paused", "completed", "abandoned"].map(s => (
                                <button
                                    key={s}
                                    onClick={() => setStatusFilter(s)}
                                    className={`text-xs px-3 py-1.5 rounded-full border font-medium transition-all ${statusFilter === s ? "border-stone-600 bg-stone-100 text-stone-700" : "border-stone-200 text-stone-500 hover:bg-stone-50"}`}
                                >
                                    {s === "" ? "All" : GOAL_STATUS_CONFIG[s as GoalStatus].label}
                                </button>
                            ))}
                        </div>

                        {filteredGoals.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-20 text-stone-400">
                                <Target className="w-14 h-14 mb-3 opacity-20" />
                                <p className="text-sm font-medium">No goals yet</p>
                                <p className="text-xs mt-1">Set persistent goals for your agents to work toward</p>
                                <button onClick={() => setGoalModal({ open: true })} className="mt-4 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700">
                                    Create First Goal
                                </button>
                            </div>
                        ) : (
                            filteredGoals.map(goal => (
                                <GoalCard
                                    key={goal.id}
                                    goal={goal}
                                    agentName={agentMap[goal.agent_id] || goal.agent_id}
                                    onEdit={() => setGoalModal({ open: true, goal })}
                                    onDelete={() => handleDeleteGoal(goal.id)}
                                    onStatusChange={status => handleStatusChange(goal, status)}
                                    onAddNote={note => handleAddNote(goal, note)}
                                />
                            ))
                        )}
                    </div>
                )}

                {/* ── Check-ins tab ──────────────────────────────── */}
                {tab === "checkins" && (
                    <div className="max-w-3xl space-y-3">
                        {!selectedAgent && (
                            <div className="bg-stone-100 border border-stone-200 rounded-xl px-4 py-3 text-sm text-stone-700 flex items-center gap-2">
                                <Bot className="w-4 h-4" />
                                Select an agent above to run a check-in or see agent-specific history
                            </div>
                        )}
                        {checkins.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-20 text-stone-400">
                                <RefreshCw className="w-14 h-14 mb-3 opacity-20" />
                                <p className="text-sm font-medium">No check-ins yet</p>
                                <p className="text-xs mt-1">Run a check-in to get a structured status report from your agent</p>
                            </div>
                        ) : (
                            checkins.map(c => <CheckInCard key={c.id} checkin={c} onDelete={() => handleDeleteCheckin(c.id)} />)
                        )}
                    </div>
                )}

                {/* ── Initiatives tab ────────────────────────────── */}
                {tab === "initiatives" && (
                    <div className="max-w-3xl space-y-3">
                        {/* Filter bar */}
                        <div className="flex gap-2 mb-4">
                            {["", "pending", "approved", "rejected", "implemented"].map(s => (
                                <button
                                    key={s}
                                    onClick={() => setStatusFilter(s)}
                                    className={`text-xs px-3 py-1.5 rounded-full border font-medium transition-all ${statusFilter === s ? "border-stone-600 bg-stone-100 text-stone-700" : "border-stone-200 text-stone-500 hover:bg-stone-50"}`}
                                >
                                    {s === "" ? "All" : INIT_STATUS_CONFIG[s as keyof typeof INIT_STATUS_CONFIG].label}
                                </button>
                            ))}
                        </div>
                        {initiatives.filter(i => !statusFilter || i.status === statusFilter).length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-20 text-stone-400">
                                <Lightbulb className="w-14 h-14 mb-3 opacity-20" />
                                <p className="text-sm font-medium">No initiatives yet</p>
                                <p className="text-xs mt-1">Agents will propose initiatives during check-ins</p>
                            </div>
                        ) : (
                            initiatives
                                .filter(i => !statusFilter || i.status === statusFilter)
                                .map(initiative => (
                                    <InitiativeCard
                                        key={initiative.id}
                                        initiative={initiative}
                                        agentName={agentMap[initiative.agent_id] || initiative.agent_id}
                                        onApprove={note => handleApproveInitiative(initiative.id, note)}
                                        onReject={note => handleRejectInitiative(initiative.id, note)}
                                        onDelete={() => handleDeleteInitiative(initiative.id)}
                                    />
                                ))
                        )}
                    </div>
                )}
            </div>

            {/* Modals */}
            {goalModal.open && (
                <GoalModal
                    goal={goalModal.goal}
                    agents={agents}
                    defaultAgentId={selectedAgent}
                    onClose={() => setGoalModal({ open: false })}
                    onSave={handleSaveGoal}
                />
            )}
        </div>
    );
}
