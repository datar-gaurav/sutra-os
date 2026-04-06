"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
    Bot,
    Send,
    Loader2,
    MessageSquare,
    User,
    ChevronDown,
    ChevronRight,
    Plus,
    Hash,
    Search,
    Trash2,
    Settings,
    MoreVertical,
    Clock,
    Zap,
    Cpu,
    CheckCircle2,
    AlertCircle,
    Terminal,
    PanelLeftClose,
    PanelLeftOpen,
    Shield,
    XCircle,
    Check,
    ChevronUp,
    Wrench,
} from "lucide-react";
import { agentsApi, chatApi, approvalsApi, projectsApi, type Agent, type ChatMessage, type Conversation, type Project } from "@/lib/api";
import { wsClient } from "@/lib/ws";
import AgentAvatar from "@/components/AgentAvatar";

// ── Tool Call Step (shown during streaming and in final messages) ─────────────
interface ToolStep {
    name: string;
    input: string;
    output?: string;
    status: "running" | "done" | "error";
}

function ToolCallCard({ step, defaultExpanded = false }: { step: ToolStep; defaultExpanded?: boolean }) {
    const [expanded, setExpanded] = useState(defaultExpanded);
    const isRunning = step.status === "running";

    return (
        <div className={`border rounded-xl overflow-hidden transition-all ${
            isRunning ? "border-amber-200 bg-amber-50/50" : "border-stone-200 bg-stone-50"
        }`}>
            <button
                onClick={() => setExpanded(!expanded)}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-stone-100/50 transition-colors"
            >
                <Wrench className={`w-3.5 h-3.5 flex-shrink-0 ${isRunning ? "text-amber-500" : "text-stone-400"}`} />
                <span className="text-[11px] font-mono text-stone-500 flex-1 truncate">
                    {isRunning ? "Running" : "Called"}: <span className="font-semibold text-stone-700">{step.name}</span>
                </span>
                {isRunning ? (
                    <div className="flex gap-1">
                        <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce" />
                        <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce [animation-delay:0.2s]" />
                        <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce [animation-delay:0.4s]" />
                    </div>
                ) : (
                    <>
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                        {expanded ? <ChevronUp className="w-3 h-3 text-stone-400" /> : <ChevronDown className="w-3 h-3 text-stone-400" />}
                    </>
                )}
            </button>
            {expanded && (
                <div className="px-3 pb-2.5 space-y-2 border-t border-stone-200/60">
                    {step.input && (
                        <div className="mt-2">
                            <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-1">Input</p>
                            <pre className="text-[11px] text-stone-600 bg-white rounded-lg p-2 border border-stone-100 overflow-x-auto max-h-32 custom-scrollbar whitespace-pre-wrap break-words font-mono">{step.input.length > 500 ? step.input.slice(0, 500) + "…" : step.input}</pre>
                        </div>
                    )}
                    {step.output && (
                        <div>
                            <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider mb-1">Output</p>
                            <pre className="text-[11px] text-stone-600 bg-white rounded-lg p-2 border border-stone-100 overflow-x-auto max-h-40 custom-scrollbar whitespace-pre-wrap break-words font-mono">{step.output.length > 800 ? step.output.slice(0, 800) + "…" : step.output}</pre>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ── Inline Approval Card ─────────────────────────────────────────────────────
interface InlineApproval {
    id: string;
    title: string;
    description: string;
    risk_level: string;
    category: string;
    context: any;
    status: "pending" | "approved" | "rejected";
}

function InlineApprovalCard({ approval, onDecide }: { approval: InlineApproval; onDecide: (id: string, action: "approve" | "reject") => void }) {
    const [note, setNote] = useState("");
    const [deciding, setDeciding] = useState(false);
    const isPending = approval.status === "pending";

    const riskColors: Record<string, string> = {
        low: "bg-emerald-100 text-emerald-700",
        medium: "bg-amber-100 text-amber-700",
        high: "bg-red-100 text-red-700",
        critical: "bg-red-200 text-red-800",
    };

    async function handleDecision(action: "approve" | "reject") {
        setDeciding(true);
        await onDecide(approval.id, action);
        setDeciding(false);
    }

    return (
        <div className={`border rounded-xl p-4 space-y-3 ${
            approval.status === "approved" ? "border-emerald-200 bg-emerald-50/30" :
            approval.status === "rejected" ? "border-red-200 bg-red-50/30" :
            "border-amber-200 bg-amber-50/30"
        }`}>
            <div className="flex items-start gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                    isPending ? "bg-amber-100" : approval.status === "approved" ? "bg-emerald-100" : "bg-red-100"
                }`}>
                    <Shield className={`w-4 h-4 ${
                        isPending ? "text-amber-600" : approval.status === "approved" ? "text-emerald-600" : "text-red-600"
                    }`} />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="text-sm font-semibold text-stone-800">{approval.title}</h4>
                        {approval.risk_level && (
                            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${riskColors[approval.risk_level] || "bg-stone-100 text-stone-600"}`}>
                                {approval.risk_level}
                            </span>
                        )}
                        {!isPending && (
                            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                                approval.status === "approved" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
                            }`}>
                                {approval.status}
                            </span>
                        )}
                    </div>
                    {approval.description && (
                        <p className="text-xs text-stone-500 mt-1">{approval.description}</p>
                    )}
                    {approval.context?.reasoning && (
                        <p className="text-xs text-stone-500 mt-1 italic">Reasoning: {approval.context.reasoning}</p>
                    )}
                </div>
            </div>

            {isPending && (
                <div className="flex items-center gap-2 pt-1">
                    <input
                        type="text"
                        placeholder="Optional note..."
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        className="flex-1 text-xs px-3 py-1.5 rounded-lg border border-stone-200 bg-white focus:outline-none focus:ring-1 focus:ring-stone-300"
                    />
                    <button
                        onClick={() => handleDecision("approve")}
                        disabled={deciding}
                        className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
                    >
                        <Check className="w-3 h-3" /> Approve
                    </button>
                    <button
                        onClick={() => handleDecision("reject")}
                        disabled={deciding}
                        className="flex items-center gap-1 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50"
                    >
                        <XCircle className="w-3 h-3" /> Reject
                    </button>
                </div>
            )}
        </div>
    );
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ChatPage() {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
    const [agentConversations, setAgentConversations] = useState<Record<string, Conversation[]>>({});
    const [expandedAgents, setExpandedAgents] = useState<Set<string>>(new Set());

    const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState("");
    const [streaming, setStreaming] = useState(false);
    const [streamContent, setStreamContent] = useState("");
    const [streamToolSteps, setStreamToolSteps] = useState<ToolStep[]>([]);
    const [inlineApprovals, setInlineApprovals] = useState<InlineApproval[]>([]);
    const [showAgentPicker, setShowAgentPicker] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [user, setUser] = useState<{ username: string; role: string } | null>(null);
    const [sidebarOpen, setSidebarOpen] = useState(true);

    // Active project
    const [activeProject, setActiveProject] = useState<Project | null>(null);
    const [projects, setProjects] = useState<Project[]>([]);

    // @Mention State
    const [mentionQuery, setMentionQuery] = useState("");
    const [showMentionList, setShowMentionList] = useState(false);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    // ── Data Fetching ────────────────────────────────────────────────────────────

    useEffect(() => {
        const storedUser = localStorage.getItem("sutra_user");
        if (storedUser) {
            try {
                setUser(JSON.parse(storedUser));
            } catch (e) {
                console.error("Failed to parse user", e);
            }
        }

        // Load projects for active project display
        projectsApi.list({ status: "active" }).then(setProjects).catch(() => {});

        agentsApi.list().then((list) => {
            const running = list.filter((a) => a.status === "running");
            setAgents(running);

            if (running.length > 0 && !selectedAgent) {
                setSelectedAgent(running[0]);
                setExpandedAgents(new Set([running[0].id]));
            }

            running.forEach(agent => {
                chatApi.conversations(agent.id).then(convs => {
                    setAgentConversations(prev => ({
                        ...prev,
                        [agent.id]: convs
                    }));
                });
            });
        });
    }, []);

    useEffect(() => {
        if (selectedAgent && activeConversationId) {
            chatApi.messages(selectedAgent.id, activeConversationId).then(setMessages);
        } else {
            setMessages([]);
        }
    }, [selectedAgent, activeConversationId]);

    // WebSocket: listen for approval requests targeting the current agent
    useEffect(() => {
        wsClient.connect();
        const unsub = wsClient.on("approval_requested", (data: any) => {
            // Only show if it's from the current agent
            if (selectedAgent && data.agent_id === selectedAgent.id) {
                const approval: InlineApproval = {
                    id: data.approval_id || data.id,
                    title: data.title || "Approval Required",
                    description: data.description || "",
                    risk_level: data.risk_level || "medium",
                    category: data.category || "",
                    context: data.context || {},
                    status: "pending",
                };
                setInlineApprovals(prev => [...prev, approval]);
            }
        });
        const unsubDecided = wsClient.on("approval_decided", (data: any) => {
            setInlineApprovals(prev =>
                prev.map(a => a.id === (data.approval_id || data.id)
                    ? { ...a, status: data.decision === "approved" ? "approved" : "rejected" }
                    : a
                )
            );
        });
        return () => { unsub(); unsubDecided(); };
    }, [selectedAgent]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, streamContent, streamToolSteps, inlineApprovals]);

    // ── Handlers ─────────────────────────────────────────────────────────────────

    const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        const val = e.target.value;
        setInput(val);

        const cursorPosition = e.target.selectionStart;
        const textBeforeCursor = val.slice(0, cursorPosition);
        const lastAtSymbol = textBeforeCursor.lastIndexOf("@");

        if (lastAtSymbol !== -1 && (lastAtSymbol === 0 || textBeforeCursor[lastAtSymbol - 1] === " " || textBeforeCursor[lastAtSymbol - 1] === "\n")) {
            const query = textBeforeCursor.slice(lastAtSymbol + 1);
            if (!query.includes(" ")) {
                setMentionQuery(query);
                setShowMentionList(true);
            } else {
                setShowMentionList(false);
            }
        } else {
            setShowMentionList(false);
        }
    };

    const handleSelectMention = (agentName: string) => {
        if (!inputRef.current) return;

        const cursorPosition = inputRef.current.selectionStart;
        const textBeforeCursor = input.slice(0, cursorPosition);
        const textAfterCursor = input.slice(cursorPosition);
        const lastAtSymbol = textBeforeCursor.lastIndexOf("@");

        const newInput =
            textBeforeCursor.slice(0, lastAtSymbol) +
            `@${agentName} ` +
            textAfterCursor;

        setInput(newInput);
        setShowMentionList(false);
        setTimeout(() => inputRef.current?.focus(), 0);
    };

    const handleNewChat = useCallback((agentOverride?: Agent) => {
        const agent = agentOverride || selectedAgent;
        if (!agent) return;

        setSelectedAgent(agent);
        setActiveConversationId(null);
        setMessages([]);
        setInput("");
        if (inputRef.current) inputRef.current.focus();
    }, [selectedAgent]);

    const handleSelectConversation = (agentId: string, conversationId: string) => {
        const agent = agents.find(a => a.id === agentId);
        if (agent) {
            setSelectedAgent(agent);
            setActiveConversationId(conversationId);
        }
    };

    const toggleAgentExpand = (agentId: string) => {
        setExpandedAgents(prev => {
            const next = new Set(prev);
            if (next.has(agentId)) next.delete(agentId);
            else next.add(agentId);
            return next;
        });
    };

    async function handleSend() {
        if (!input.trim() || !selectedAgent || streaming) return;

        const userMessage = input.trim();
        setInput("");

        const tempUserMsg: ChatMessage = {
            id: `temp-${Date.now()}`,
            role: "user",
            content: userMessage,
            tool_calls: null,
            created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, tempUserMsg]);

        setStreaming(true);
        setStreamContent("");

        try {
            const token = localStorage.getItem("sutra_access_token");
            const response = await fetch(`${API_BASE}/api/chat/stream`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({
                    agent_id: selectedAgent.id,
                    message: userMessage,
                    conversation_id: activeConversationId,
                }),
            });

            if (!response.ok) throw new Error("Stream failed");

            const reader = response.body?.getReader();
            if (!reader) throw new Error("No reader");

            const decoder = new TextDecoder();
            let fullContent = "";
            let currentConversationId = activeConversationId;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const text = decoder.decode(value, { stream: true });
                const lines = text.split("\n");

                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    try {
                        const data = JSON.parse(line.slice(6));

                        if (data.type === "meta") {
                            if (!currentConversationId) {
                                currentConversationId = data.conversation_id;
                                setActiveConversationId(data.conversation_id);
                                chatApi.conversations(selectedAgent.id).then(convs => {
                                    setAgentConversations(prev => ({
                                        ...prev,
                                        [selectedAgent.id]: convs
                                    }));
                                });
                            }
                        } else if (data.type === "token") {
                            fullContent += data.content;
                            setStreamContent(fullContent);
                        } else if (data.type === "tool_start") {
                            setStreamToolSteps(prev => [...prev, { name: data.content, input: data.input || "", status: "running" }]);
                        } else if (data.type === "tool_end") {
                            setStreamToolSteps(prev => prev.map(s =>
                                s.name === data.content && s.status === "running"
                                    ? { ...s, output: data.output || "", status: "done" }
                                    : s
                            ));
                        } else if (data.type === "project_switch") {
                            const proj = projects.find(p => p.id === data.project_id);
                            if (proj) setActiveProject(proj);
                        } else if (data.type === "error") {
                            fullContent += `\nError: ${data.content}`;
                            setStreamContent(fullContent);
                        }
                    } catch (e) { console.error("Parse error", e); }
                }
            }

            // Capture tool steps before resetting
            let finalToolSteps: ToolStep[] = [];
            setStreamToolSteps(prev => { finalToolSteps = prev; return []; });

            const assistantMsg: ChatMessage = {
                id: `msg-${Date.now()}`,
                role: "assistant",
                content: fullContent,
                tool_calls: finalToolSteps.length > 0 ? finalToolSteps : null,
                created_at: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, assistantMsg]);
            setStreamContent("");
        } catch (err) {
            console.error("Chat error:", err);
            const errorMsg: ChatMessage = {
                id: `err-${Date.now()}`,
                role: "assistant",
                content: "Failed to get response. Make sure the agent is running.",
                tool_calls: null,
                created_at: new Date().toISOString(),
            };
            setMessages((prev) => [...prev, errorMsg]);
            setStreamContent("");
            setStreamToolSteps([]);
        } finally {
            setStreaming(false);
        }
    }

    function handleKeyDown(e: React.KeyboardEvent) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    }

    async function handleApprovalDecision(approvalId: string, action: "approve" | "reject") {
        try {
            if (action === "approve") {
                await approvalsApi.approve(approvalId);
            } else {
                await approvalsApi.reject(approvalId);
            }
            setInlineApprovals(prev =>
                prev.map(a => a.id === approvalId ? { ...a, status: action === "approve" ? "approved" : "rejected" } : a)
            );
        } catch (err) {
            console.error("Approval decision failed:", err);
        }
    }

    // ── Search & Filter ─────────────────────────────────────────────────────────

    const filteredAgentsWithConvs = useMemo(() => {
        return agents.map(agent => {
            const convs = agentConversations[agent.id] || [];
            const filtered = convs.filter(c => c.title.toLowerCase().includes(searchQuery.toLowerCase()));
            return { ...agent, conversations: filtered };
        }).filter(a => a.conversations.length > 0 || searchQuery === "");
    }, [agents, agentConversations, searchQuery]);

    return (
        <div className="flex h-full w-full bg-surface-1 overflow-hidden">
            {/* ── Chat Sidebar (collapsible) ── */}
            <div className={`${sidebarOpen ? "w-72" : "w-0"} flex-shrink-0 border-r border-stone-200 flex flex-col bg-white transition-all duration-300 overflow-hidden`}>
                <div className="w-72 flex flex-col h-full">
                    <div className="p-3 space-y-3">
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => handleNewChat()}
                                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-stone-800 hover:bg-stone-700 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
                            >
                                <Plus className="w-4 h-4" />
                                New Conversation
                            </button>
                            <button
                                onClick={() => setSidebarOpen(false)}
                                className="p-2 text-stone-400 hover:text-stone-600 hover:bg-stone-100 rounded-lg transition-colors"
                                title="Collapse sidebar"
                            >
                                <PanelLeftClose className="w-4 h-4" />
                            </button>
                        </div>

                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
                            <input
                                type="text"
                                placeholder="Search threads..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-10 pr-4 py-2 bg-white border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-300/50 focus:border-stone-300 placeholder:text-stone-400"
                            />
                        </div>
                    </div>

                    <div className="flex-1 overflow-y-auto custom-scrollbar px-2 space-y-1 pb-4">
                        {filteredAgentsWithConvs.map((agent) => (
                            <div key={agent.id} className="space-y-0.5">
                                <div
                                    className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${selectedAgent?.id === agent.id ? "bg-stone-100" : "hover:bg-stone-50"}`}
                                    onClick={() => toggleAgentExpand(agent.id)}
                                >
                                    {expandedAgents.has(agent.id) ? <ChevronDown className="w-3.5 h-3.5 text-stone-400" /> : <ChevronRight className="w-3.5 h-3.5 text-stone-400" />}
                                    <AgentAvatar name={agent.name} avatarUrl={agent.avatar_url} size="sm" className="!w-5 !h-5 !text-[10px]" />
                                    <span className="text-sm font-medium truncate flex-1 text-stone-700">
                                        {agent.name}
                                    </span>
                                    <span className="text-[10px] text-stone-400 font-medium bg-stone-100 px-1.5 rounded-full">
                                        {agent.conversations.length}
                                    </span>
                                </div>

                                {expandedAgents.has(agent.id) && (
                                    <div className="ml-4 pl-2 border-l border-stone-200 space-y-0.5">
                                        {agent.conversations.length === 0 ? (
                                            <p className="text-xs text-stone-400 py-1 pl-4">No threads</p>
                                        ) : (
                                            agent.conversations.map((conv) => (
                                                <button
                                                    key={conv.id}
                                                    onClick={() => handleSelectConversation(agent.id, conv.id)}
                                                    className={`w-full group flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-all ${
                                                        activeConversationId === conv.id
                                                        ? "bg-stone-100 border border-stone-200"
                                                        : "hover:bg-stone-50 border border-transparent"
                                                    }`}
                                                >
                                                    <div className="flex-1 min-w-0">
                                                        <p className={`text-sm truncate ${activeConversationId === conv.id ? "font-medium text-stone-800" : "text-stone-600"}`}>
                                                            {conv.title || "Untitled Chat"}
                                                        </p>
                                                    </div>
                                                    <button className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-stone-200 rounded transition-opacity">
                                                        <MoreVertical className="w-3 h-3 text-stone-400" />
                                                    </button>
                                                </button>
                                            ))
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    <div className="p-3 border-t border-stone-200">
                        <div className="flex items-center gap-3 p-2 rounded-lg bg-stone-50 border border-stone-100">
                            <div className="w-7 h-7 rounded-full bg-stone-200 flex items-center justify-center">
                                <User className="w-3.5 h-3.5 text-stone-600" />
                            </div>
                            <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium text-stone-800 truncate">{user?.username || "Guest"}</p>
                                <p className="text-[10px] text-stone-400 truncate capitalize">{user?.role || "Viewer"}</p>
                            </div>
                            <Settings className="w-3.5 h-3.5 text-stone-400" />
                        </div>
                    </div>
                </div>
            </div>

            {/* ── Main Chat Area ── */}
            <div className="flex-1 flex flex-col min-w-0 relative">
                {/* ── Chat Header ── */}
                <header className="h-14 border-b border-stone-200 flex items-center justify-between px-6 bg-white/90 backdrop-blur-md sticky top-0 z-30">
                    <div className="flex items-center gap-3">
                        {!sidebarOpen && (
                            <button
                                onClick={() => setSidebarOpen(true)}
                                className="p-2 text-stone-400 hover:text-stone-600 hover:bg-stone-100 rounded-lg transition-colors"
                                title="Expand sidebar"
                            >
                                <PanelLeftOpen className="w-4 h-4" />
                            </button>
                        )}
                        <div className="relative">
                            <button
                                onClick={() => setShowAgentPicker(!showAgentPicker)}
                                className="flex items-center gap-3 hover:bg-stone-50 p-1.5 pr-3 rounded-lg transition-colors"
                            >
                                {selectedAgent ? (
                                    <>
                                        <AgentAvatar name={selectedAgent.name} avatarUrl={selectedAgent.avatar_url} size="sm" />
                                        <div className="text-left">
                                            <div className="flex items-center gap-2">
                                                <h2 className="text-sm font-semibold text-stone-800">{selectedAgent.name}</h2>
                                                <ChevronDown className="w-3.5 h-3.5 text-stone-400" />
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <p className="text-[10px] text-emerald-600 font-medium flex items-center gap-1">
                                                    <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
                                                    Agent Online
                                                </p>
                                                {activeProject && (
                                                    <span className="text-[10px] px-1.5 py-0 rounded-full border border-stone-200 text-stone-500 flex items-center gap-1">
                                                        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: activeProject.color || "#6b7280" }} />
                                                        {activeProject.name}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </>
                                ) : (
                                    <div className="flex items-center gap-2 text-stone-400">
                                        <Bot className="w-5 h-5" />
                                        <span className="text-sm font-medium">Select Agent</span>
                                    </div>
                                )}
                            </button>

                            {showAgentPicker && (
                                <div className="absolute left-0 top-full mt-2 w-64 bg-white border border-stone-200 rounded-xl p-1.5 z-50 shadow-lg animate-slide-up">
                                    <div className="px-3 py-2 border-b border-stone-100 mb-1">
                                        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Active Agents</p>
                                    </div>
                                    {agents.length === 0 ? (
                                        <p className="text-sm text-stone-400 p-3">No running agents.</p>
                                    ) : (
                                        agents.map((agent) => (
                                            <button
                                                key={agent.id}
                                                onClick={() => {
                                                    setSelectedAgent(agent);
                                                    setShowAgentPicker(false);
                                                    handleNewChat(agent);
                                                }}
                                                className={`w-full flex items-center gap-3 p-2.5 rounded-lg transition-colors text-left ${selectedAgent?.id === agent.id ? "bg-stone-100" : "hover:bg-stone-50"}`}
                                            >
                                                <AgentAvatar name={agent.name} avatarUrl={agent.avatar_url} size="sm" />
                                                <div className="flex-1">
                                                    <p className={`text-sm font-medium ${selectedAgent?.id === agent.id ? "text-stone-800" : "text-stone-700"}`}>
                                                        {agent.name}
                                                    </p>
                                                    <p className="text-[10px] text-stone-400 flex items-center gap-1">
                                                        <Cpu className="w-2.5 h-2.5" /> {agent.llm_model}
                                                    </p>
                                                </div>
                                                {selectedAgent?.id === agent.id && <CheckCircle2 className="w-4 h-4 text-stone-500" />}
                                            </button>
                                        ))
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="flex items-center gap-2">
                        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-stone-100 rounded-lg">
                            <Zap className="w-3 h-3 text-amber-500" />
                            <span className="text-[11px] font-medium text-stone-500">0.002</span>
                        </div>
                        <button className="p-2 text-stone-400 hover:text-stone-600 transition-colors">
                            <MoreVertical className="w-4 h-4" />
                        </button>
                    </div>
                </header>

                {/* ── Messages List ── */}
                <div className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-6 bg-surface-1">
                    {messages.length === 0 && !streaming ? (
                        <div className="h-full flex flex-col items-center justify-center text-center max-w-2xl mx-auto space-y-5">
                            <div className="w-16 h-16 rounded-2xl bg-stone-200 flex items-center justify-center">
                                <MessageSquare className="w-8 h-8 text-stone-500" />
                            </div>
                            <div className="space-y-2">
                                <h3 className="text-2xl font-bold text-stone-800 tracking-tight">
                                    Ready to automate?
                                </h3>
                                <p className="text-sm text-stone-500 max-w-md mx-auto leading-relaxed">
                                    {selectedAgent
                                        ? `You're chatting with ${selectedAgent.name}. Ask me to manage files, research trends, or coordinate other agents.`
                                        : "Select a running agent to begin your mission."}
                                </p>
                            </div>

                            {selectedAgent && (
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-xl pt-2">
                                    {[
                                        { icon: Zap, label: "Capabilities", text: "What are your core skills?" },
                                        { icon: Search, label: "Tasks", text: "Analyze my current task list" },
                                        { icon: Terminal, label: "Control", text: "Run a system health check" },
                                        { icon: Bot, label: "Delegate", text: "Coordinate with other agents" }
                                    ].map((s, i) => (
                                        <button
                                            key={i}
                                            onClick={() => setInput(s.text)}
                                            className="text-left p-4 rounded-xl bg-white border border-stone-200 hover:border-stone-300 hover:shadow-sm transition-all group"
                                        >
                                            <div className="flex items-center gap-2 mb-1">
                                                <s.icon className="w-3.5 h-3.5 text-stone-400" />
                                                <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">{s.label}</span>
                                            </div>
                                            <p className="text-sm text-stone-600 group-hover:text-stone-800">{s.text}</p>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="max-w-4xl mx-auto w-full space-y-6">
                            {messages.map((msg) => (
                                <div
                                    key={msg.id}
                                    className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
                                >
                                    <div className="flex-shrink-0 mt-1">
                                        {msg.role === "user" ? (
                                            <div className="w-8 h-8 rounded-lg bg-stone-200 flex items-center justify-center">
                                                <User className="w-4 h-4 text-stone-500" />
                                            </div>
                                        ) : (
                                            <AgentAvatar name={selectedAgent?.name || "A"} avatarUrl={selectedAgent?.avatar_url} size="md" className="rounded-lg !w-8 !h-8" />
                                        )}
                                    </div>

                                    <div className={`flex flex-col gap-1.5 min-w-0 max-w-[85%] ${msg.role === "user" ? "items-end" : ""}`}>
                                        <div className="flex items-center gap-2 px-1">
                                            <span className="text-xs font-medium text-stone-700">
                                                {msg.role === "user" ? "You" : selectedAgent?.name}
                                            </span>
                                            <span className="text-[10px] text-stone-400">{new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                                        </div>

                                        <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                                            msg.role === "user"
                                            ? "bg-stone-800 text-white rounded-tr-sm"
                                            : "bg-white text-stone-800 border border-stone-200 rounded-tl-sm shadow-sm"
                                        }`}>
                                            <div className="whitespace-pre-wrap">{msg.content}</div>
                                        </div>

                                        {msg.tool_calls && Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0 && (
                                            <div className="flex flex-col gap-1.5 w-full">
                                                {msg.tool_calls.map((tc: any, i: number) => (
                                                    tc.name ? (
                                                        <ToolCallCard key={i} step={{ name: tc.name, input: tc.input || "", output: tc.output || "", status: tc.status || "done" }} />
                                                    ) : tc.function ? (
                                                        <ToolCallCard key={i} step={{ name: tc.function.name, input: JSON.stringify(tc.function.arguments || {}), status: "done" }} />
                                                    ) : null
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}

                            {/* Streaming content */}
                            {streaming && (streamContent || streamToolSteps.length > 0) && (
                                <div className="flex gap-3">
                                    <div className="flex-shrink-0 mt-1">
                                        <AgentAvatar name={selectedAgent?.name || "A"} avatarUrl={selectedAgent?.avatar_url} size="md" className="rounded-lg !w-8 !h-8" />
                                    </div>
                                    <div className="flex flex-col gap-1.5 min-w-0 max-w-[85%]">
                                        <div className="flex items-center gap-2 px-1">
                                            <span className="text-xs font-medium text-stone-700">{selectedAgent?.name}</span>
                                            <span className="text-[10px] text-stone-500 font-medium animate-pulse">Thinking...</span>
                                        </div>
                                        {streamToolSteps.length > 0 && (
                                            <div className="flex flex-col gap-1.5 w-full">
                                                {streamToolSteps.map((step, i) => (
                                                    <ToolCallCard key={i} step={step} defaultExpanded={step.status === "running"} />
                                                ))}
                                            </div>
                                        )}
                                        {streamContent && (
                                            <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-white text-stone-800 text-sm leading-relaxed border border-stone-200 shadow-sm">
                                                <div className="whitespace-pre-wrap">{streamContent}</div>
                                                <span className="inline-block w-1.5 h-4 bg-stone-400 animate-pulse ml-0.5" />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {streaming && !streamContent && streamToolSteps.length === 0 && (
                                <div className="flex gap-3">
                                    <div className="flex-shrink-0 mt-1">
                                        <AgentAvatar name={selectedAgent?.name || "A"} avatarUrl={selectedAgent?.avatar_url} size="md" className="rounded-lg !w-8 !h-8" />
                                    </div>
                                    <div className="flex flex-col gap-1.5">
                                        <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-white border border-stone-200 shadow-sm">
                                            <div className="flex gap-1.5">
                                                <div className="w-1.5 h-1.5 rounded-full bg-stone-400 animate-bounce" />
                                                <div className="w-1.5 h-1.5 rounded-full bg-stone-400 animate-bounce [animation-delay:0.2s]" />
                                                <div className="w-1.5 h-1.5 rounded-full bg-stone-400 animate-bounce [animation-delay:0.4s]" />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                            {/* Inline Approval Cards */}
                            {inlineApprovals.length > 0 && (
                                <div className="flex flex-col gap-2 max-w-4xl mx-auto w-full">
                                    {inlineApprovals.map(approval => (
                                        <InlineApprovalCard
                                            key={approval.id}
                                            approval={approval}
                                            onDecide={handleApprovalDecision}
                                        />
                                    ))}
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>
                    )}
                </div>

                {/* ── Message Input ── */}
                <div className="p-4 bg-surface-1 border-t border-stone-200">
                    <div className="max-w-4xl mx-auto w-full relative">
                        {/* Mention List Popover */}
                        {showMentionList && (
                            <div className="absolute bottom-full left-0 mb-2 w-60 bg-white border border-stone-200 rounded-xl shadow-lg p-1.5 z-50 animate-slide-up">
                                <div className="px-3 py-2 border-b border-stone-100 mb-1">
                                    <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wider">Mention Agent</p>
                                </div>
                                <div className="max-h-48 overflow-y-auto custom-scrollbar">
                                    {agents
                                        .filter(a => a.name.toLowerCase().includes(mentionQuery.toLowerCase()))
                                        .map(agent => (
                                            <button
                                                key={agent.id}
                                                onClick={() => handleSelectMention(agent.name)}
                                                className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                            >
                                                <AgentAvatar name={agent.name} avatarUrl={agent.avatar_url} size="sm" className="!w-6 !h-6 !text-[10px]" />
                                                <span className="text-sm text-stone-700">{agent.name}</span>
                                            </button>
                                        ))}
                                    {agents.filter(a => a.name.toLowerCase().includes(mentionQuery.toLowerCase())).length === 0 && (
                                        <p className="text-xs text-stone-400 p-3 text-center">No agents match &quot;@{mentionQuery}&quot;</p>
                                    )}
                                </div>
                            </div>
                        )}

                        <div className="bg-white border border-stone-200 rounded-xl p-3 flex items-end gap-3 shadow-sm">
                            <div className="flex-1 flex flex-col min-w-0">
                                <textarea
                                    ref={inputRef}
                                    value={input}
                                    onChange={handleInputChange}
                                    onKeyDown={handleKeyDown}
                                    placeholder={
                                        selectedAgent
                                            ? `Message ${selectedAgent.name}...`
                                            : "Select an agent to begin"
                                    }
                                    disabled={!selectedAgent || streaming}
                                    className="w-full bg-transparent border-none focus:ring-0 focus:outline-none text-sm py-1.5 resize-none custom-scrollbar min-h-[36px] max-h-48 text-stone-800 placeholder:text-stone-400"
                                    rows={1}
                                />
                            </div>
                            <div className="flex items-center gap-1.5 pb-0.5">
                                <button
                                    onClick={handleSend}
                                    disabled={!input.trim() || !selectedAgent || streaming}
                                    className={`p-2 rounded-lg transition-all ${
                                        !input.trim() || !selectedAgent || streaming
                                        ? "bg-stone-100 text-stone-400"
                                        : "bg-stone-800 hover:bg-stone-700 text-white shadow-sm"
                                    }`}
                                >
                                    {streaming ? (
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                    ) : (
                                        <Send className="w-4 h-4" />
                                    )}
                                </button>
                            </div>
                        </div>
                        <p className="text-[10px] text-center text-stone-400 mt-2">
                            Press <kbd className="px-1.5 py-0.5 rounded bg-stone-100 text-[9px] border border-stone-200">Enter</kbd> to send, <kbd className="px-1.5 py-0.5 rounded bg-stone-100 text-[9px] border border-stone-200">Shift+Enter</kbd> for new line
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
