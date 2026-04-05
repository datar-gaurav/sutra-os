"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
    ArrowLeft, Play, RotateCcw, Loader2, CheckCircle,
    AlertCircle, Users, MessageSquareText, ListChecks, Send, Trash2, User,
} from "lucide-react";
import { discussionsApi, agentsApi, Discussion, Agent } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DiscussionMessage {
    agent_id: string;
    agent_name: string;
    content: string;
    round: number;
    is_moderator: boolean;
    timestamp: string;
}

interface StreamEvent {
    type: string;
    [key: string]: any;
}

function AgentAvatar({ name, isModerator, isHuman }: { name: string; isModerator?: boolean; isHuman?: boolean }) {
    return (
        <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm
            ${isHuman ? "bg-emerald-100 text-emerald-700 ring-2 ring-emerald-300" : isModerator ? "bg-amber-100 text-amber-700 ring-2 ring-amber-300" : "bg-stone-200 text-stone-700"}`}>
            {isHuman ? <User size={14} /> : name[0]?.toUpperCase()}
        </div>
    );
}

function MessageBubble({ msg, isThinking }: { msg: DiscussionMessage; isThinking?: boolean }) {
    const isHuman = !!(msg as any).is_human || msg.agent_id?.startsWith("user:");
    return (
        <div className="flex gap-3 group">
            <AgentAvatar name={msg.agent_name} isModerator={msg.is_moderator} isHuman={isHuman} />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-semibold text-stone-800">{msg.agent_name}</span>
                    {isHuman && (
                        <span className="text-xs bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full">Human</span>
                    )}
                    {msg.is_moderator && !isHuman && (
                        <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">Moderator</span>
                    )}
                    <span className="text-xs text-stone-400">Round {msg.round}</span>
                </div>
                <div className={`bg-white border border-stone-200 rounded-xl rounded-tl-sm px-4 py-3 shadow-sm
                    ${isHuman ? "border-emerald-200 bg-emerald-50/30" : msg.is_moderator ? "border-amber-200 bg-amber-50/30" : ""}`}>
                    {isThinking ? (
                        <div className="flex items-center gap-2 text-stone-400">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span className="text-sm italic">Thinking...</span>
                        </div>
                    ) : (
                        <p className="text-sm text-stone-700 whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                    )}
                </div>
            </div>
        </div>
    );
}

export default function DiscussionDetailPage() {
    const { id } = useParams<{ id: string }>();
    const router = useRouter();
    const [discussion, setDiscussion] = useState<Discussion | null>(null);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [messages, setMessages] = useState<DiscussionMessage[]>([]);
    const [thinkingAgent, setThinkingAgent] = useState<{ agent_id: string; agent_name: string } | null>(null);
    const [summary, setSummary] = useState<string | null>(null);
    const [actionItems, setActionItems] = useState<string[]>([]);
    const [currentRound, setCurrentRound] = useState(0);
    const [running, setRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [humanInput, setHumanInput] = useState("");
    const [sendingMessage, setSendingMessage] = useState(false);
    const bottomRef = useRef<HTMLDivElement>(null);
    const esRef = useRef<EventSource | null>(null);

    useEffect(() => {
        Promise.all([discussionsApi.get(id), agentsApi.list()])
            .then(([d, a]) => {
                setDiscussion(d);
                setAgents(a);
                setMessages(d.messages || []);
                setSummary(d.summary ?? null);
                setActionItems(d.action_items ?? []);
            })
            .finally(() => setLoading(false));
    }, [id]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, thinkingAgent]);

    function agentName(aid: string) {
        return agents.find(a => a.id === aid)?.name ?? aid.slice(0, 8);
    }

    async function handleRun() {
        if (!discussion) return;
        setRunning(true);
        setError(null);
        setSummary(null);
        setActionItems([]);
        setCurrentRound(0);
        // Keep existing human messages — agents will see them as context

        const token = typeof window !== "undefined" ? localStorage.getItem("sutra_access_token") : null;
        const url = `${API_BASE}/api/discussions/${id}/run`;

        // Use fetch with ReadableStream for SSE with auth header
        try {
            const res = await fetch(url, {
                method: "POST",
                headers: {
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
            });
            if (!res.ok || !res.body) {
                throw new Error(`HTTP ${res.status}`);
            }
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() ?? "";

                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    try {
                        const event: StreamEvent = JSON.parse(line.slice(6));
                        handleStreamEvent(event);
                    } catch { /* skip malformed */ }
                }
            }
        } catch (e: any) {
            setError(e.message || "Connection failed");
        } finally {
            setRunning(false);
            setThinkingAgent(null);
            // Refresh discussion state
            discussionsApi.get(id).then(setDiscussion).catch(() => {});
        }
    }

    function handleStreamEvent(event: StreamEvent) {
        switch (event.type) {
            case "round_start":
                setCurrentRound(event.round);
                break;
            case "agent_thinking":
                setThinkingAgent({ agent_id: event.agent_id, agent_name: event.agent_name });
                break;
            case "agent_message":
            case "moderator_message":
                setThinkingAgent(null);
                setMessages(prev => [...prev, {
                    agent_id: event.agent_id,
                    agent_name: event.agent_name,
                    content: event.content,
                    round: event.round,
                    is_moderator: event.type === "moderator_message",
                    timestamp: event.timestamp || new Date().toISOString(),
                }]);
                break;
            case "summary":
                setThinkingAgent(null);
                setSummary(event.summary);
                setActionItems(event.action_items || []);
                break;
            case "error":
                setError(event.message);
                setThinkingAgent(null);
                break;
            case "done":
                setThinkingAgent(null);
                break;
        }
    }

    async function handleReset() {
        if (!confirm("Reset this discussion? All messages and summary will be cleared.")) return;
        const d = await discussionsApi.reset(id);
        setDiscussion(d);
        setMessages([]);
        setSummary(null);
        setActionItems([]);
        setCurrentRound(0);
        setError(null);
    }

    async function handleSendMessage() {
        if (!humanInput.trim() || sendingMessage || running) return;
        setSendingMessage(true);
        try {
            const updated = await discussionsApi.addMessage(id, humanInput.trim());
            setDiscussion(updated);
            setMessages(updated.messages || []);
            setHumanInput("");
        } catch (err: any) {
            setError(err.message || "Failed to send message");
        } finally {
            setSendingMessage(false);
        }
    }

    async function handleDelete() {
        if (!confirm("Delete this discussion permanently?")) return;
        try {
            await discussionsApi.delete(id);
            router.push("/discussions");
        } catch (err: any) {
            setError(err.message || "Failed to delete");
        }
    }

    if (loading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="w-6 h-6 animate-spin text-stone-600" /></div>;
    }
    if (!discussion) {
        return <div className="p-6 text-red-500">Discussion not found</div>;
    }

    const canRun = discussion.status === "pending" && !running;
    const isDone = discussion.status === "concluded";
    const isFailed = discussion.status === "failed";

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-6 py-4 border-b border-stone-200 bg-white flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                    <button onClick={() => router.push("/discussions")} className="p-1.5 rounded-lg hover:bg-stone-100 text-stone-500 flex-shrink-0">
                        <ArrowLeft className="w-5 h-5" />
                    </button>
                    <div className="min-w-0">
                        <h1 className="text-lg font-semibold text-stone-900 truncate">{discussion.title}</h1>
                        <p className="text-xs text-stone-500 truncate">{discussion.topic}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                    {running && (
                        <div className="flex items-center gap-1.5 text-xs text-amber-600 bg-amber-50 px-3 py-1.5 rounded-full">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            Round {currentRound} / {discussion.max_rounds}
                        </div>
                    )}
                    {isDone && <div className="flex items-center gap-1.5 text-xs text-green-600 bg-green-50 px-3 py-1.5 rounded-full"><CheckCircle className="w-3.5 h-3.5" /> Concluded</div>}
                    {isFailed && <div className="flex items-center gap-1.5 text-xs text-red-600 bg-red-50 px-3 py-1.5 rounded-full"><AlertCircle className="w-3.5 h-3.5" /> Failed</div>}
                    {(isDone || isFailed) && (
                        <button onClick={handleReset} className="px-3 py-2 text-sm rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50 flex items-center gap-1.5">
                            <RotateCcw className="w-4 h-4" /> Reset
                        </button>
                    )}
                    {canRun && (
                        <button onClick={handleRun} className="px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-700 flex items-center gap-2">
                            <Play className="w-4 h-4" /> Run Discussion
                        </button>
                    )}
                    <button onClick={handleDelete} className="px-3 py-2 text-sm rounded-lg border border-stone-200 text-stone-400 hover:text-rose-600 hover:border-rose-200 hover:bg-rose-50 flex items-center gap-1.5 transition-colors">
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            </div>

            <div className="flex flex-1 overflow-hidden">
                {/* Main chat area */}
                <div className="flex-1 flex flex-col overflow-hidden">
                <div className="flex-1 overflow-y-auto p-6 space-y-4">
                    {error && (
                        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex items-center gap-2">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
                        </div>
                    )}

                    {messages.length === 0 && !running && !error && (
                        <div className="flex flex-col items-center justify-center h-64 text-stone-400">
                            <MessageSquareText className="w-12 h-12 mb-3 opacity-30" />
                            <p className="text-sm">Discussion hasn't started yet</p>
                            {canRun && (
                                <button onClick={handleRun} className="mt-3 px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-700 flex items-center gap-2">
                                    <Play className="w-4 h-4" /> Run Discussion
                                </button>
                            )}
                        </div>
                    )}

                    {/* Group messages by round */}
                    {Array.from(new Set(messages.map(m => m.round))).map(round => (
                        <div key={round}>
                            <div className="flex items-center gap-3 my-4">
                                <div className="flex-1 h-px bg-stone-200" />
                                <span className="text-xs font-medium text-stone-400 bg-stone-100 px-2 py-1 rounded-full">Round {round}</span>
                                <div className="flex-1 h-px bg-stone-200" />
                            </div>
                            <div className="space-y-4">
                                {messages.filter(m => m.round === round).map((msg, i) => (
                                    <MessageBubble key={i} msg={msg} />
                                ))}
                            </div>
                        </div>
                    ))}

                    {/* Thinking indicator */}
                    {thinkingAgent && (
                        <MessageBubble
                            msg={{
                                agent_id: thinkingAgent.agent_id,
                                agent_name: thinkingAgent.agent_name,
                                content: "",
                                round: currentRound,
                                is_moderator: false,
                                timestamp: new Date().toISOString(),
                            }}
                            isThinking
                        />
                    )}

                    <div ref={bottomRef} />
                </div>

                {/* Human message input */}
                {!running && discussion.status !== "active" && (
                    <div className="px-6 py-3 border-t border-stone-200 bg-white">
                        <form
                            onSubmit={(e) => { e.preventDefault(); handleSendMessage(); }}
                            className="flex items-center gap-2"
                        >
                            <div className="w-7 h-7 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
                                <User size={12} className="text-emerald-700" />
                            </div>
                            <input
                                type="text"
                                value={humanInput}
                                onChange={(e) => setHumanInput(e.target.value)}
                                placeholder="Add your thoughts to the discussion..."
                                className="flex-1 border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 focus:border-stone-600"
                                disabled={sendingMessage}
                            />
                            <button
                                type="submit"
                                disabled={!humanInput.trim() || sendingMessage}
                                className="p-2 rounded-lg bg-stone-700 text-white hover:bg-stone-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                            >
                                {sendingMessage ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                            </button>
                        </form>
                    </div>
                )}
                </div>

                {/* Right sidebar — info + summary */}
                <div className="w-72 border-l border-stone-200 bg-stone-50 flex flex-col overflow-y-auto p-4 space-y-4 flex-shrink-0">
                    {/* Participants */}
                    <div>
                        <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                            <Users className="w-3.5 h-3.5" /> Participants
                        </h3>
                        <div className="space-y-2">
                            {/* Human participant */}
                            <div className="flex items-center gap-2">
                                <AgentAvatar name="You" isHuman />
                                <div>
                                    <p className="text-sm text-stone-800">You</p>
                                    <p className="text-xs text-emerald-600">Human</p>
                                </div>
                            </div>
                            {discussion.participant_agent_ids.map(aid => {
                                const agent = agents.find(a => a.id === aid);
                                const isMod = aid === discussion.moderator_agent_id;
                                return (
                                    <div key={aid} className="flex items-center gap-2">
                                        <AgentAvatar name={agent?.name ?? aid} isModerator={isMod} />
                                        <div>
                                            <p className="text-sm text-stone-800">{agent?.name ?? aid.slice(0, 8)}</p>
                                            {isMod && <p className="text-xs text-amber-600">Moderator</p>}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Summary */}
                    {summary && (
                        <div>
                            <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                                <MessageSquareText className="w-3.5 h-3.5" /> Summary
                            </h3>
                            <p className="text-xs text-stone-600 leading-relaxed whitespace-pre-wrap bg-white rounded-lg border border-stone-200 p-3">
                                {summary}
                            </p>
                        </div>
                    )}

                    {/* Action Items */}
                    {actionItems.length > 0 && (
                        <div>
                            <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                                <ListChecks className="w-3.5 h-3.5" /> Action Items
                            </h3>
                            <ul className="space-y-1.5">
                                {actionItems.map((item, i) => (
                                    <li key={i} className="flex items-start gap-2 text-xs text-stone-700 bg-white rounded-lg border border-stone-200 p-2">
                                        <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0 mt-0.5" />
                                        {item}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
