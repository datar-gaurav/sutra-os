"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
    Plus, X, Loader2, MessageSquareText, Users, Play,
    CheckCircle, AlertCircle, Clock, RotateCcw, Trash2,
} from "lucide-react";
import { discussionsApi, agentsApi, Discussion, Agent, DiscussionType } from "@/lib/api";

const TYPE_LABELS: Record<DiscussionType, string> = {
    brainstorm: "Brainstorm",
    debate: "Debate",
    review: "Review",
    standup: "Standup",
    retrospective: "Retrospective",
};

const TYPE_COLORS: Record<DiscussionType, string> = {
    brainstorm: "bg-purple-100 text-purple-700",
    debate:     "bg-red-100 text-red-700",
    review:     "bg-blue-100 text-blue-700",
    standup:    "bg-green-100 text-green-700",
    retrospective: "bg-amber-100 text-amber-700",
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
    pending:   <Clock className="w-4 h-4 text-stone-400" />,
    active:    <Play className="w-4 h-4 text-amber-500 animate-pulse" />,
    concluded: <CheckCircle className="w-4 h-4 text-green-500" />,
    failed:    <AlertCircle className="w-4 h-4 text-red-500" />,
};

interface NewDiscussionModalProps {
    agents: Agent[];
    onClose: () => void;
    onCreate: (d: Discussion) => void;
}

function NewDiscussionModal({ agents, onClose, onCreate }: NewDiscussionModalProps) {
    const [title, setTitle] = useState("");
    const [topic, setTopic] = useState("");
    const [type, setType] = useState<DiscussionType>("brainstorm");
    const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
    const [moderatorId, setModeratorId] = useState("");
    const [maxRounds, setMaxRounds] = useState(2);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    function toggleAgent(id: string) {
        setSelectedAgents(prev =>
            prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]
        );
    }

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (selectedAgents.length === 0) { setError("Select at least one participant"); return; }
        setSaving(true);
        setError("");
        try {
            const d = await discussionsApi.create({
                title,
                topic,
                type,
                participant_agent_ids: selectedAgents,
                moderator_agent_id: moderatorId || undefined,
                max_rounds: maxRounds,
            });
            onCreate(d);
            onClose();
        } catch (err: any) {
            setError(err.message || "Failed to create discussion");
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6 max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-stone-900">New Discussion</h2>
                    <button onClick={onClose} className="p-1 rounded hover:bg-stone-100 text-stone-400"><X className="w-5 h-5" /></button>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Title *</label>
                        <input
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={title} onChange={e => setTitle(e.target.value)} required placeholder="e.g. Q3 Marketing Strategy Brainstorm"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Topic / Question *</label>
                        <textarea
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 h-20 resize-none"
                            value={topic} onChange={e => setTopic(e.target.value)} required
                            placeholder="What should the agents discuss?"
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1">Discussion Type</label>
                            <select
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={type} onChange={e => setType(e.target.value as DiscussionType)}
                            >
                                {(Object.keys(TYPE_LABELS) as DiscussionType[]).map(t =>
                                    <option key={t} value={t}>{TYPE_LABELS[t]}</option>
                                )}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1">Rounds (1-5)</label>
                            <input
                                type="number" min={1} max={5}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={maxRounds} onChange={e => setMaxRounds(Number(e.target.value))}
                            />
                        </div>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-2">
                            Participants * <span className="text-stone-400 font-normal">({selectedAgents.length} selected)</span>
                        </label>
                        <div className="border border-stone-200 rounded-lg p-2 max-h-40 overflow-y-auto space-y-1">
                            {agents.length === 0 ? (
                                <p className="text-xs text-stone-400 p-2">No agents available</p>
                            ) : agents.map(a => (
                                <label key={a.id} className="flex items-center gap-2 p-1.5 rounded hover:bg-stone-50 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={selectedAgents.includes(a.id)}
                                        onChange={() => toggleAgent(a.id)}
                                        className="rounded"
                                    />
                                    <div className="w-6 h-6 rounded-full bg-stone-200 flex items-center justify-center flex-shrink-0">
                                        <span className="text-xs font-bold text-stone-700">{a.name[0]}</span>
                                    </div>
                                    <div>
                                        <span className="text-sm text-stone-800">{a.name}</span>
                                        <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${a.status === "running" ? "bg-green-100 text-green-600" : "bg-stone-100 text-stone-500"}`}>
                                            {a.status}
                                        </span>
                                    </div>
                                </label>
                            ))}
                        </div>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Moderator (optional)</label>
                        <select
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={moderatorId} onChange={e => setModeratorId(e.target.value)}
                        >
                            <option value="">No moderator</option>
                            {agents.filter(a => selectedAgents.includes(a.id)).map(a =>
                                <option key={a.id} value={a.id}>{a.name}</option>
                            )}
                        </select>
                    </div>
                    {error && <p className="text-xs text-red-500">{error}</p>}
                    <div className="flex gap-2 justify-end pt-2">
                        <button type="button" onClick={onClose}
                            className="px-4 py-2 text-sm rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50">
                            Cancel
                        </button>
                        <button type="submit" disabled={saving || !title.trim() || !topic.trim()}
                            className="px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-700 disabled:opacity-50 flex items-center gap-2">
                            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                            Create Discussion
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

export default function DiscussionsPage() {
    const router = useRouter();
    const [discussions, setDiscussions] = useState<Discussion[]>([]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);

    useEffect(() => {
        Promise.all([discussionsApi.list(), agentsApi.list()])
            .then(([d, a]) => { setDiscussions(d); setAgents(a); })
            .finally(() => setLoading(false));
    }, []);

    function agentName(id: string) {
        return agents.find(a => a.id === id)?.name ?? id.slice(0, 8);
    }

    async function handleDelete(e: React.MouseEvent, id: string) {
        e.stopPropagation();
        if (!confirm("Delete this discussion? This cannot be undone.")) return;
        try {
            await discussionsApi.delete(id);
            setDiscussions(prev => prev.filter(d => d.id !== id));
        } catch (err) {
            console.error(err);
        }
    }

    if (loading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="w-6 h-6 animate-spin text-stone-600" /></div>;
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-6 py-4 border-b border-stone-200 bg-white flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-semibold text-stone-900">Discussions</h1>
                    <p className="text-sm text-stone-500">Structured multi-agent group discussions</p>
                </div>
                <button
                    onClick={() => setShowModal(true)}
                    className="px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-700 flex items-center gap-2"
                >
                    <Plus className="w-4 h-4" /> New Discussion
                </button>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto p-6">
                {discussions.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-64 text-stone-400">
                        <MessageSquareText className="w-12 h-12 mb-3 opacity-30" />
                        <p className="text-sm">No discussions yet</p>
                        <button onClick={() => setShowModal(true)} className="mt-3 text-sm text-stone-700 hover:underline">
                            Start your first discussion
                        </button>
                    </div>
                ) : (
                    <div className="grid gap-4 max-w-4xl">
                        {discussions.map(d => (
                            <div
                                key={d.id}
                                className="group bg-white rounded-xl border border-stone-200 p-5 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
                                onClick={() => router.push(`/discussions/${d.id}`)}
                            >
                                <div className="flex items-start justify-between gap-4">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1">
                                            {STATUS_ICONS[d.status]}
                                            <h3 className="font-semibold text-stone-900 truncate">{d.title}</h3>
                                            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLORS[d.type as DiscussionType]}`}>
                                                {TYPE_LABELS[d.type as DiscussionType]}
                                            </span>
                                        </div>
                                        <p className="text-sm text-stone-600 line-clamp-2">{d.topic}</p>
                                    </div>
                                    <div className="flex items-start gap-2 flex-shrink-0">
                                        <div className="text-right">
                                            <p className="text-xs text-stone-400">{d.max_rounds} rounds</p>
                                            <p className="text-xs text-stone-400 mt-1">{d.messages?.length ?? 0} messages</p>
                                        </div>
                                        <button
                                            onClick={(e) => handleDelete(e, d.id)}
                                            className="p-1.5 rounded-lg text-stone-300 hover:text-rose-500 hover:bg-rose-50 transition-colors opacity-0 group-hover:opacity-100"
                                            title="Delete discussion"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                                <div className="flex items-center gap-3 mt-3">
                                    <div className="flex items-center gap-1 text-xs text-stone-500">
                                        <Users className="w-3.5 h-3.5" />
                                        <span>
                                            {d.participant_agent_ids.map(id => agentName(id)).join(", ")}
                                        </span>
                                    </div>
                                    {d.concluded_at && (
                                        <span className="text-xs text-stone-400">
                                            · Concluded {new Date(d.concluded_at).toLocaleDateString()}
                                        </span>
                                    )}
                                </div>
                                {d.summary && (
                                    <p className="mt-2 text-xs text-stone-500 italic line-clamp-1 border-t border-stone-100 pt-2">
                                        {d.summary}
                                    </p>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {showModal && (
                <NewDiscussionModal
                    agents={agents}
                    onClose={() => setShowModal(false)}
                    onCreate={d => setDiscussions(prev => [d, ...prev])}
                />
            )}
        </div>
    );
}
