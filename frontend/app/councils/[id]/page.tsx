"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
    ArrowLeft, Play, RotateCcw, Loader2, CheckCircle, AlertCircle,
    Users, Trash2, Gavel, Scale, FileText, Copy, Check,
} from "lucide-react";
import { councilsApi, agentsApi, Council, Agent, CouncilMessage } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface StreamEvent {
    type: string;
    [key: string]: any;
}

const PHASE_LABELS: Record<string, string> = {
    propose: "Independent Proposal",
    critique: "Critique & Revision",
    synthesis: "Synthesis & Dissent",
};

const PHASE_COLORS: Record<string, string> = {
    propose: "bg-blue-100 text-blue-700",
    critique: "bg-amber-100 text-amber-700",
    synthesis: "bg-emerald-100 text-emerald-700",
};

function AdvisorAvatar({ name, role }: { name: string; role?: string }) {
    const isModelNative = !role || role === "model-native";
    return (
        <div
            title={role && !isModelNative ? `Role: ${role}` : "Model-native"}
            className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm
                ${isModelNative ? "bg-stone-200 text-stone-700" : "bg-indigo-100 text-indigo-700 ring-2 ring-indigo-300"}`}
        >
            {name[0]?.toUpperCase()}
        </div>
    );
}

function ArbitratorAvatar({ name }: { name: string }) {
    return (
        <div
            title="Arbitrator"
            className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 font-bold text-sm bg-amber-100 text-amber-700 ring-2 ring-amber-300"
        >
            <Scale className="w-4 h-4" />
        </div>
    );
}

function MessageBubble({ msg, isThinking }: { msg: CouncilMessage; isThinking?: boolean }) {
    const role = msg.role && msg.role !== "model-native" ? msg.role : null;
    return (
        <div className="flex gap-3 group">
            <AdvisorAvatar name={msg.agent_name} role={msg.role} />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-sm font-semibold text-stone-800">{msg.agent_name}</span>
                    {role && (
                        <span className="text-xs bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded-full">
                            {role}
                        </span>
                    )}
                    <span className="text-xs text-stone-400">Round {msg.round}</span>
                    {msg.phase && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${PHASE_COLORS[msg.phase] || "bg-stone-100 text-stone-700"}`}>
                            {PHASE_LABELS[msg.phase] || msg.phase}
                        </span>
                    )}
                </div>
                <div className="bg-white border border-stone-200 rounded-xl rounded-tl-sm px-4 py-3 shadow-sm">
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

function FinalReportPanel({ content, arbitratorName }: { content: string; arbitratorName: string }) {
    const [copied, setCopied] = useState(false);

    async function handleCopy() {
        await navigator.clipboard.writeText(content);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
    }

    return (
        <div className="bg-white border-2 border-amber-200 rounded-xl shadow-sm overflow-hidden">
            <div className="bg-amber-50 px-5 py-3 border-b border-amber-200 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Scale className="w-5 h-5 text-amber-700" />
                    <div>
                        <h3 className="text-sm font-semibold text-amber-900">Consolidated Council Report</h3>
                        <p className="text-xs text-amber-700">Arbitrator: {arbitratorName}</p>
                    </div>
                </div>
                <button
                    onClick={handleCopy}
                    className="px-3 py-1.5 text-xs rounded-lg border border-amber-300 bg-white text-amber-800 hover:bg-amber-100 flex items-center gap-1.5"
                >
                    {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    {copied ? "Copied" : "Copy"}
                </button>
            </div>
            <div className="px-5 py-4">
                <pre className="text-sm text-stone-700 whitespace-pre-wrap font-sans leading-relaxed">
                    {content}
                </pre>
            </div>
        </div>
    );
}

export default function CouncilDetailPage() {
    const { id } = useParams<{ id: string }>();
    const router = useRouter();
    const [council, setCouncil] = useState<Council | null>(null);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [messages, setMessages] = useState<CouncilMessage[]>([]);
    const [thinking, setThinking] = useState<{ agent_id: string; agent_name: string; role: string; phase: string } | null>(null);
    const [arbitratorThinking, setArbitratorThinking] = useState(false);
    const [finalReport, setFinalReport] = useState<string | null>(null);
    const [currentRound, setCurrentRound] = useState(0);
    const [currentPhase, setCurrentPhase] = useState("");
    const [running, setRunning] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        Promise.all([councilsApi.get(id), agentsApi.list()])
            .then(([c, a]) => {
                setCouncil(c);
                setAgents(a);
                setMessages(c.messages || []);
                setFinalReport(c.final_report ?? null);
            })
            .finally(() => setLoading(false));
    }, [id]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, thinking, finalReport]);

    function agentName(aid: string) {
        return agents.find(a => a.id === aid)?.name ?? aid.slice(0, 8);
    }

    async function handleRun() {
        if (!council) return;
        setRunning(true);
        setError(null);
        setFinalReport(null);
        setMessages([]);
        setCurrentRound(0);
        setCurrentPhase("");

        const token = typeof window !== "undefined" ? localStorage.getItem("sutra_access_token") : null;
        const url = `${API_BASE}/api/councils/${id}/run`;

        try {
            const res = await fetch(url, {
                method: "POST",
                headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
            });
            if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
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
            setThinking(null);
            setArbitratorThinking(false);
            councilsApi.get(id).then(setCouncil).catch(() => {});
        }
    }

    function handleStreamEvent(event: StreamEvent) {
        switch (event.type) {
            case "round_start":
                setCurrentRound(event.round);
                setCurrentPhase(event.phase);
                break;
            case "advisor_thinking":
                setThinking({
                    agent_id: event.agent_id,
                    agent_name: event.agent_name,
                    role: event.role,
                    phase: event.phase,
                });
                break;
            case "advisor_message":
                setThinking(null);
                setMessages(prev => [...prev, {
                    agent_id: event.agent_id,
                    agent_name: event.agent_name,
                    role: event.role,
                    content: event.content,
                    round: event.round,
                    phase: event.phase,
                    timestamp: event.timestamp || new Date().toISOString(),
                }]);
                break;
            case "arbitrator_thinking":
                setThinking(null);
                setArbitratorThinking(true);
                break;
            case "final_report":
                setArbitratorThinking(false);
                setFinalReport(event.content);
                break;
            case "error":
                setError(event.message);
                setThinking(null);
                setArbitratorThinking(false);
                break;
            case "done":
                setThinking(null);
                setArbitratorThinking(false);
                break;
        }
    }

    async function handleReset() {
        if (!confirm("Reset this council? All transcript and the final report will be cleared.")) return;
        const c = await councilsApi.reset(id);
        setCouncil(c);
        setMessages([]);
        setFinalReport(null);
        setCurrentRound(0);
        setCurrentPhase("");
        setError(null);
    }

    async function handleDelete() {
        if (!confirm("Delete this council permanently?")) return;
        try {
            await councilsApi.delete(id);
            router.push("/councils");
        } catch (err: any) {
            setError(err.message || "Failed to delete");
        }
    }

    if (loading) {
        return <div className="flex items-center justify-center h-full"><Loader2 className="w-6 h-6 animate-spin text-stone-600" /></div>;
    }
    if (!council) {
        return <div className="p-6 text-red-500">Council not found</div>;
    }

    const canRun = (council.status === "pending" || council.status === "concluded" || council.status === "failed") && !running;
    const isDone = council.status === "concluded";
    const isFailed = council.status === "failed";

    const arbitratorName = agentName(council.arbitrator_agent_id);
    const rounds = Array.from(new Set(messages.map(m => m.round))).sort((a, b) => a - b);

    return (
        <div className="flex flex-col h-full">
            <div className="px-6 py-4 border-b border-stone-200 bg-white flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                    <button onClick={() => router.push("/councils")} className="p-1.5 rounded-lg hover:bg-stone-100 text-stone-500 flex-shrink-0">
                        <ArrowLeft className="w-5 h-5" />
                    </button>
                    <Gavel className="w-5 h-5 text-stone-500 flex-shrink-0" />
                    <div className="min-w-0">
                        <h1 className="text-lg font-semibold text-stone-900 truncate">{council.title}</h1>
                        <p className="text-xs text-stone-500 truncate">{council.question}</p>
                    </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                    {running && (
                        <div className="flex items-center gap-1.5 text-xs text-amber-600 bg-amber-50 px-3 py-1.5 rounded-full">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            Round {currentRound} / {council.num_rounds}
                            {currentPhase && <span>· {PHASE_LABELS[currentPhase] || currentPhase}</span>}
                        </div>
                    )}
                    {!running && isDone && (
                        <div className="flex items-center gap-1.5 text-xs text-green-600 bg-green-50 px-3 py-1.5 rounded-full">
                            <CheckCircle className="w-3.5 h-3.5" /> Concluded
                        </div>
                    )}
                    {!running && isFailed && (
                        <div className="flex items-center gap-1.5 text-xs text-red-600 bg-red-50 px-3 py-1.5 rounded-full">
                            <AlertCircle className="w-3.5 h-3.5" /> Failed
                        </div>
                    )}
                    {(isDone || isFailed) && !running && (
                        <button onClick={handleReset} className="px-3 py-2 text-sm rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50 flex items-center gap-1.5">
                            <RotateCcw className="w-4 h-4" /> Reset
                        </button>
                    )}
                    {canRun && (
                        <button onClick={handleRun} className="px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-800 flex items-center gap-2">
                            <Play className="w-4 h-4" /> {messages.length > 0 ? "Re-run" : "Convene Council"}
                        </button>
                    )}
                    <button onClick={handleDelete} className="px-3 py-2 text-sm rounded-lg border border-stone-200 text-stone-400 hover:text-rose-600 hover:border-rose-200 hover:bg-rose-50 flex items-center gap-1.5 transition-colors">
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            </div>

            <div className="flex flex-1 overflow-hidden">
                <div className="flex-1 flex flex-col overflow-hidden">
                    <div className="flex-1 overflow-y-auto p-6 space-y-4">
                        {error && (
                            <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 flex items-center gap-2">
                                <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
                            </div>
                        )}

                        {messages.length === 0 && !running && !error && !finalReport && (
                            <div className="flex flex-col items-center justify-center h-64 text-stone-400">
                                <Gavel className="w-12 h-12 mb-3 opacity-30" />
                                <p className="text-sm">Council hasn&apos;t convened yet</p>
                                {canRun && (
                                    <button onClick={handleRun} className="mt-3 px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-800 flex items-center gap-2">
                                        <Play className="w-4 h-4" /> Convene Council
                                    </button>
                                )}
                            </div>
                        )}

                        {/* Group messages by round */}
                        {rounds.map(round => {
                            const roundMsgs = messages.filter(m => m.round === round);
                            const phase = roundMsgs[0]?.phase;
                            return (
                                <div key={round}>
                                    <div className="flex items-center gap-3 my-4">
                                        <div className="flex-1 h-px bg-stone-200" />
                                        <span className="text-xs font-medium text-stone-400 bg-stone-100 px-2 py-1 rounded-full">
                                            Round {round}{phase ? ` · ${PHASE_LABELS[phase] || phase}` : ""}
                                        </span>
                                        <div className="flex-1 h-px bg-stone-200" />
                                    </div>
                                    <div className="space-y-4">
                                        {roundMsgs.map((msg, i) => (
                                            <MessageBubble key={i} msg={msg} />
                                        ))}
                                    </div>
                                </div>
                            );
                        })}

                        {/* Live thinking indicator */}
                        {thinking && (
                            <MessageBubble
                                msg={{
                                    agent_id: thinking.agent_id,
                                    agent_name: thinking.agent_name,
                                    role: thinking.role,
                                    content: "",
                                    round: currentRound,
                                    phase: thinking.phase,
                                    timestamp: new Date().toISOString(),
                                }}
                                isThinking
                            />
                        )}

                        {/* Arbitrator thinking */}
                        {arbitratorThinking && (
                            <div className="flex gap-3">
                                <ArbitratorAvatar name={arbitratorName} />
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="text-sm font-semibold text-stone-800">{arbitratorName}</span>
                                        <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">Arbitrator</span>
                                    </div>
                                    <div className="bg-white border border-amber-200 rounded-xl rounded-tl-sm px-4 py-3 shadow-sm">
                                        <div className="flex items-center gap-2 text-amber-700">
                                            <Loader2 className="w-4 h-4 animate-spin" />
                                            <span className="text-sm italic">Reviewing the full debate and producing the report...</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Final report */}
                        {finalReport && (
                            <div className="my-6">
                                <FinalReportPanel content={finalReport} arbitratorName={arbitratorName} />
                            </div>
                        )}

                        <div ref={bottomRef} />
                    </div>
                </div>

                {/* Right sidebar */}
                <div className="w-72 border-l border-stone-200 bg-stone-50 flex flex-col overflow-y-auto p-4 space-y-4 flex-shrink-0">
                    <div>
                        <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                            <Users className="w-3.5 h-3.5" /> Advisors ({council.advisor_agent_ids.length})
                        </h3>
                        <div className="space-y-2">
                            {council.advisor_agent_ids.map(aid => {
                                const agent = agents.find(a => a.id === aid);
                                const role = council.role_assignments?.[aid];
                                return (
                                    <div key={aid} className="flex items-center gap-2">
                                        <AdvisorAvatar name={agent?.name ?? aid} role={role} />
                                        <div className="min-w-0">
                                            <p className="text-sm text-stone-800 truncate">{agent?.name ?? aid.slice(0, 8)}</p>
                                            {role && council.debate_mode === "role_based" ? (
                                                <p className="text-xs text-indigo-600 truncate">{role}</p>
                                            ) : (
                                                <p className="text-[10px] text-stone-400 truncate">
                                                    {agent?.llm_provider}/{agent?.llm_model}
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    <div>
                        <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                            <Scale className="w-3.5 h-3.5" /> Arbitrator
                        </h3>
                        <div className="flex items-center gap-2">
                            <ArbitratorAvatar name={arbitratorName} />
                            <div className="min-w-0">
                                <p className="text-sm text-stone-800 truncate">{arbitratorName}</p>
                                <p className="text-[10px] text-stone-400 truncate">
                                    {agents.find(a => a.id === council.arbitrator_agent_id)?.llm_provider}
                                    /
                                    {agents.find(a => a.id === council.arbitrator_agent_id)?.llm_model}
                                </p>
                            </div>
                        </div>
                    </div>

                    <div>
                        <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                            <FileText className="w-3.5 h-3.5" /> Setup
                        </h3>
                        <div className="text-xs text-stone-600 bg-white rounded-lg border border-stone-200 p-3 space-y-1">
                            <p><span className="text-stone-400">Mode:</span> {council.debate_mode === "role_based" ? "Role-based" : "Model-native"}</p>
                            <p><span className="text-stone-400">Rounds:</span> {council.num_rounds}</p>
                            {council.context?.background && (
                                <p className="pt-1 border-t border-stone-100"><span className="text-stone-400">Background:</span> {council.context.background}</p>
                            )}
                            {council.context?.constraints && (
                                <p><span className="text-stone-400">Constraints:</span> {council.context.constraints}</p>
                            )}
                            {council.context?.non_negotiables && (
                                <p><span className="text-stone-400">Non-negotiables:</span> {council.context.non_negotiables}</p>
                            )}
                            {council.context?.success_criteria && (
                                <p><span className="text-stone-400">Success:</span> {council.context.success_criteria}</p>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
