"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
    Plus, X, Loader2, Gavel, Users, Play,
    CheckCircle, AlertCircle, Clock, Trash2, Scale,
} from "lucide-react";
import {
    councilsApi, agentsApi,
    Council, Agent, CouncilDebateMode, CouncilCreatePayload,
} from "@/lib/api";

const PRESET_ROLES = [
    "Technical Architect",
    "Ethical Skeptic",
    "Pragmatic CFO",
    "Domain Expert",
    "Contrarian",
];

const STATUS_ICONS: Record<string, React.ReactNode> = {
    pending:   <Clock className="w-4 h-4 text-stone-400" />,
    active:    <Play className="w-4 h-4 text-amber-500 animate-pulse" />,
    concluded: <CheckCircle className="w-4 h-4 text-green-500" />,
    failed:    <AlertCircle className="w-4 h-4 text-red-500" />,
};

interface NewCouncilModalProps {
    agents: Agent[];
    onClose: () => void;
    onCreate: (c: Council) => void;
}

function NewCouncilModal({ agents, onClose, onCreate }: NewCouncilModalProps) {
    const [title, setTitle] = useState("");
    const [question, setQuestion] = useState("");
    const [background, setBackground] = useState("");
    const [constraints, setConstraints] = useState("");
    const [nonNegotiables, setNonNegotiables] = useState("");
    const [success, setSuccess] = useState("");
    const [advisors, setAdvisors] = useState<string[]>([]);
    const [arbitrator, setArbitrator] = useState("");
    const [mode, setMode] = useState<CouncilDebateMode>("model_native");
    const [roles, setRoles] = useState<Record<string, string>>({});
    const [numRounds, setNumRounds] = useState(3);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    function toggleAdvisor(id: string) {
        setAdvisors(prev => {
            const next = prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id];
            // Clear arbitrator if user just selected them as an advisor
            if (id === arbitrator && next.includes(id)) {
                setArbitrator("");
            }
            return next;
        });
    }

    function setRole(agentId: string, role: string) {
        setRoles(prev => ({ ...prev, [agentId]: role }));
    }

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (advisors.length < 2) { setError("Pick at least 2 advisors"); return; }
        if (!arbitrator) { setError("Pick an arbitrator"); return; }
        if (advisors.includes(arbitrator)) { setError("Arbitrator must differ from advisors"); return; }
        if (mode === "role_based") {
            const missing = advisors.filter(a => !(roles[a] || "").trim());
            if (missing.length > 0) { setError("Assign a role to every advisor"); return; }
        }

        setSaving(true);
        setError("");
        try {
            const payload: CouncilCreatePayload = {
                title,
                question,
                context: {
                    background: background || null,
                    constraints: constraints || null,
                    non_negotiables: nonNegotiables || null,
                    success_criteria: success || null,
                },
                advisor_agent_ids: advisors,
                arbitrator_agent_id: arbitrator,
                debate_mode: mode,
                role_assignments: mode === "role_based" ? roles : undefined,
                num_rounds: numRounds,
            };
            const c = await councilsApi.create(payload);
            onCreate(c);
            onClose();
        } catch (err: any) {
            setError(err.message || "Failed to create council");
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl mx-4 p-6 max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-stone-900 flex items-center gap-2">
                        <Gavel className="w-5 h-5" /> New Council
                    </h2>
                    <button onClick={onClose} className="p-1 rounded hover:bg-stone-100 text-stone-400">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Title *</label>
                        <input
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={title} onChange={e => setTitle(e.target.value)} required
                            placeholder="e.g. Should we migrate from Postgres to CockroachDB?"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Question *</label>
                        <textarea
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 h-20 resize-none"
                            value={question} onChange={e => setQuestion(e.target.value)} required
                            placeholder="State the problem the council should solve."
                        />
                    </div>

                    {/* Context */}
                    <details className="border border-stone-200 rounded-lg p-3" open>
                        <summary className="text-xs font-medium text-stone-600 cursor-pointer">
                            Context & Constraints (optional)
                        </summary>
                        <div className="grid grid-cols-2 gap-3 mt-3">
                            <textarea
                                className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 h-16 resize-none"
                                value={background} onChange={e => setBackground(e.target.value)}
                                placeholder="Background"
                            />
                            <textarea
                                className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 h-16 resize-none"
                                value={constraints} onChange={e => setConstraints(e.target.value)}
                                placeholder="Budget / time / resource limits"
                            />
                            <textarea
                                className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 h-16 resize-none"
                                value={nonNegotiables} onChange={e => setNonNegotiables(e.target.value)}
                                placeholder="Non-negotiables"
                            />
                            <textarea
                                className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 h-16 resize-none"
                                value={success} onChange={e => setSuccess(e.target.value)}
                                placeholder='What "good" looks like'
                            />
                        </div>
                    </details>

                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1">Debate Mode</label>
                            <select
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={mode} onChange={e => setMode(e.target.value as CouncilDebateMode)}
                            >
                                <option value="model_native">Model-native (no roles)</option>
                                <option value="role_based">Role-based (assign per advisor)</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1">Rounds (1-5)</label>
                            <input
                                type="number" min={1} max={5}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={numRounds} onChange={e => setNumRounds(Number(e.target.value))}
                            />
                            <p className="text-[10px] text-stone-400 mt-1">
                                3 = full protocol (propose → critique → synthesize). 1–2 skip critique.
                            </p>
                        </div>
                    </div>

                    {/* Advisors */}
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-2">
                            Advisors * <span className="text-stone-400 font-normal">({advisors.length} selected, min 2)</span>
                        </label>
                        <div className="border border-stone-200 rounded-lg p-2 max-h-56 overflow-y-auto space-y-1">
                            {agents.length === 0 ? (
                                <p className="text-xs text-stone-400 p-2">No agents available</p>
                            ) : agents.map(a => (
                                <div key={a.id} className="flex items-center gap-2 p-1.5 rounded hover:bg-stone-50">
                                    <input
                                        type="checkbox"
                                        checked={advisors.includes(a.id)}
                                        onChange={() => toggleAdvisor(a.id)}
                                        className="rounded"
                                    />
                                    <div className="w-6 h-6 rounded-full bg-stone-200 flex items-center justify-center flex-shrink-0">
                                        <span className="text-xs font-bold text-stone-700">{a.name[0]}</span>
                                    </div>
                                    <span className="text-sm text-stone-800 flex-1 truncate">{a.name}</span>
                                    <span className="text-[10px] text-stone-400 flex-shrink-0">
                                        {a.llm_provider}/{a.llm_model}
                                    </span>
                                    {advisors.includes(a.id) && mode === "role_based" && (
                                        <RolePicker
                                            value={roles[a.id] || ""}
                                            onChange={v => setRole(a.id, v)}
                                        />
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Arbitrator */}
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">
                            Arbitrator * <span className="text-stone-400 font-normal">(must NOT be an advisor)</span>
                        </label>
                        <select
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={arbitrator} onChange={e => setArbitrator(e.target.value)}
                            required
                        >
                            <option value="">Select an arbitrator</option>
                            {agents.filter(a => !advisors.includes(a.id)).map(a => (
                                <option key={a.id} value={a.id}>
                                    {a.name} — {a.llm_provider}/{a.llm_model}
                                </option>
                            ))}
                        </select>
                        <p className="text-[10px] text-stone-400 mt-1">
                            Pick a different model than the advisors to reduce self-favoring bias.
                        </p>
                    </div>

                    {error && <p className="text-xs text-red-500">{error}</p>}
                    <div className="flex gap-2 justify-end pt-2">
                        <button type="button" onClick={onClose}
                            className="px-4 py-2 text-sm rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50">
                            Cancel
                        </button>
                        <button type="submit" disabled={saving || !title.trim() || !question.trim()}
                            className="px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-800 disabled:opacity-50 flex items-center gap-2">
                            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                            Create Council
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

function RolePicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
    const isCustom = value && !PRESET_ROLES.includes(value);
    const [custom, setCustom] = useState(isCustom);

    function handleSelect(v: string) {
        if (v === "__custom__") {
            setCustom(true);
            onChange("");
        } else {
            setCustom(false);
            onChange(v);
        }
    }

    if (custom) {
        return (
            <div className="flex items-center gap-1 flex-shrink-0">
                <input
                    type="text"
                    value={value}
                    onChange={e => onChange(e.target.value)}
                    placeholder="Custom role"
                    className="border border-stone-200 rounded px-2 py-1 text-xs w-32 focus:outline-none focus:ring-1 focus:ring-stone-600"
                />
                <button
                    type="button"
                    onClick={() => { setCustom(false); onChange(""); }}
                    className="text-xs text-stone-400 hover:text-stone-600"
                    title="Use preset"
                >
                    <X className="w-3 h-3" />
                </button>
            </div>
        );
    }

    return (
        <select
            value={value}
            onChange={e => handleSelect(e.target.value)}
            className="border border-stone-200 rounded px-2 py-1 text-xs w-32 focus:outline-none focus:ring-1 focus:ring-stone-600 flex-shrink-0"
        >
            <option value="">Pick role…</option>
            {PRESET_ROLES.map(r => <option key={r} value={r}>{r}</option>)}
            <option value="__custom__">Custom…</option>
        </select>
    );
}

export default function CouncilsPage() {
    const router = useRouter();
    const [councils, setCouncils] = useState<Council[]>([]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);

    useEffect(() => {
        Promise.all([councilsApi.list(), agentsApi.list()])
            .then(([c, a]) => { setCouncils(c); setAgents(a); })
            .finally(() => setLoading(false));
    }, []);

    function agentName(id: string) {
        return agents.find(a => a.id === id)?.name ?? id.slice(0, 8);
    }

    async function handleDelete(e: React.MouseEvent, id: string) {
        e.stopPropagation();
        if (!confirm("Delete this council? This cannot be undone.")) return;
        try {
            await councilsApi.delete(id);
            setCouncils(prev => prev.filter(c => c.id !== id));
        } catch (err) {
            console.error(err);
        }
    }

    if (loading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="w-6 h-6 animate-spin text-stone-600" /></div>;
    }

    return (
        <div className="flex flex-col h-full">
            <div className="px-6 py-4 border-b border-stone-200 bg-white flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-semibold text-stone-900 flex items-center gap-2">
                        <Gavel className="w-5 h-5" /> Council of Advisors
                    </h1>
                    <p className="text-sm text-stone-500">
                        Multi-advisor structured debate with an independent arbitrator producing the final report.
                    </p>
                </div>
                <button
                    onClick={() => setShowModal(true)}
                    className="px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-800 flex items-center gap-2"
                >
                    <Plus className="w-4 h-4" /> New Council
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6">
                {councils.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-64 text-stone-400">
                        <Gavel className="w-12 h-12 mb-3 opacity-30" />
                        <p className="text-sm">No councils yet</p>
                        <button onClick={() => setShowModal(true)} className="mt-3 text-sm text-stone-700 hover:underline">
                            Convene your first council
                        </button>
                    </div>
                ) : (
                    <div className="grid gap-4 max-w-4xl">
                        {councils.map(c => (
                            <div
                                key={c.id}
                                className="group bg-white rounded-xl border border-stone-200 p-5 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
                                onClick={() => router.push(`/councils/${c.id}`)}
                            >
                                <div className="flex items-start justify-between gap-4">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                                            {STATUS_ICONS[c.status]}
                                            <h3 className="font-semibold text-stone-900 truncate">{c.title}</h3>
                                            <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-indigo-100 text-indigo-700">
                                                {c.debate_mode === "role_based" ? "Role-based" : "Model-native"}
                                            </span>
                                            <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-stone-100 text-stone-700">
                                                {c.num_rounds} round{c.num_rounds === 1 ? "" : "s"}
                                            </span>
                                        </div>
                                        <p className="text-sm text-stone-600 line-clamp-2">{c.question}</p>
                                    </div>
                                    <div className="flex items-start gap-2 flex-shrink-0">
                                        <div className="text-right">
                                            <p className="text-xs text-stone-400">{c.advisor_agent_ids.length} advisors</p>
                                            <p className="text-xs text-stone-400 mt-1">{c.messages?.length ?? 0} messages</p>
                                        </div>
                                        <button
                                            onClick={(e) => handleDelete(e, c.id)}
                                            className="p-1.5 rounded-lg text-stone-300 hover:text-rose-500 hover:bg-rose-50 transition-colors opacity-0 group-hover:opacity-100"
                                            title="Delete council"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                                <div className="flex items-center gap-3 mt-3 flex-wrap">
                                    <div className="flex items-center gap-1 text-xs text-stone-500">
                                        <Users className="w-3.5 h-3.5" />
                                        <span>{c.advisor_agent_ids.map(id => agentName(id)).join(", ")}</span>
                                    </div>
                                    <div className="flex items-center gap-1 text-xs text-stone-500">
                                        <Scale className="w-3.5 h-3.5" />
                                        <span>Arbitrator: {agentName(c.arbitrator_agent_id)}</span>
                                    </div>
                                    {c.concluded_at && (
                                        <span className="text-xs text-stone-400">
                                            · Concluded {new Date(c.concluded_at).toLocaleDateString()}
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {showModal && (
                <NewCouncilModal
                    agents={agents}
                    onClose={() => setShowModal(false)}
                    onCreate={c => setCouncils(prev => [c, ...prev])}
                />
            )}
        </div>
    );
}
