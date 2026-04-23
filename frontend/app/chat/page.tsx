"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import {
    Bot,
    Send,
    Loader2,
    MessageSquare,
    User,
    ChevronDown,
    ChevronRight,
    Plus,
    Search,
    Trash2,
    Settings,
    MoreVertical,
    Zap,
    Cpu,
    CheckCircle2,
    Terminal,
    PanelLeftClose,
    PanelLeftOpen,
    Shield,
    XCircle,
    Check,
    ChevronUp,
    Wrench,
    Paperclip,
    Puzzle,
    Target,
    HardDrive,
    X,
    Clock,
    GitBranch,
} from "lucide-react";
import {
    agentsApi,
    chatApi,
    approvalsApi,
    projectsApi,
    skillsApi,
    purposesApi,
    googleDriveApi,
    jobsApi,
    workflowsApi,
    type Agent,
    type ChatMessage,
    type Conversation,
    type Project,
    type Skill,
    type LLMPurpose,
} from "@/lib/api";
import { wsClient } from "@/lib/ws";
import AgentAvatar from "@/components/AgentAvatar";

// ── Tool Call Step ─────────────────────────────────────────────────────────────

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
                            <pre className="text-[11px] text-stone-600 bg-white rounded-lg p-2 border border-stone-100 overflow-x-auto max-h-32 custom-scrollbar whitespace-pre-wrap break-words font-mono">{step.output.length > 500 ? step.output.slice(0, 500) + "…" : step.output}</pre>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ── Inline Approval Card ───────────────────────────────────────────────────────

interface InlineApproval {
    id: string;
    title: string;
    description: string;
    risk_level: string | null;
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
    // ── Core State ───────────────────────────────────────────────────────────────
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
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [convMenuOpen, setConvMenuOpen] = useState<string | null>(null);

    // ── + Menu / Attach State ────────────────────────────────────────────────────
    const [showAttachMenu, setShowAttachMenu] = useState(false);
    const [fileUploading, setFileUploading] = useState(false);

    // Conversation-scoped skills
    const [conversationSkillIds, setConversationSkillIds] = useState<string[]>([]);
    const [showSkillPanel, setShowSkillPanel] = useState(false);
    const [availableSkills, setAvailableSkills] = useState<Skill[]>([]);

    // Purpose override
    const [purposeOverrideId, setPurposeOverrideId] = useState<string | null>(null);
    const [showPurposeMenu, setShowPurposeMenu] = useState(false);
    const [availablePurposes, setAvailablePurposes] = useState<LLMPurpose[]>([]);

    // Google Drive
    const [driveConnected, setDriveConnected] = useState(false);
    const [showDriveDialog, setShowDriveDialog] = useState(false);
    const [driveSearchQuery, setDriveSearchQuery] = useState("");
    const [driveFiles, setDriveFiles] = useState<{ id: string; name: string; mimeType: string; modifiedTime: string }[]>([]);
    const [driveSearching, setDriveSearching] = useState(false);

    // Schedule modal
    const [showScheduleModal, setShowScheduleModal] = useState(false);
    const [scheduleLabel, setScheduleLabel] = useState("");
    const [schedulePreset, setSchedulePreset] = useState("daily_9am");
    const [scheduleCron, setScheduleCron] = useState("0 9 * * *");
    const [scheduleCreating, setScheduleCreating] = useState(false);
    const [scheduleSuccess, setScheduleSuccess] = useState(false);

    // Workflow generator modal
    const [showWorkflowModal, setShowWorkflowModal] = useState(false);
    const [workflowDescription, setWorkflowDescription] = useState("");
    const [generatingWorkflow, setGeneratingWorkflow] = useState(false);
    const [generatedWorkflowId, setGeneratedWorkflowId] = useState<string | null>(null);

    // Projects
    const [activeProject, setActiveProject] = useState<Project | null>(null);
    const [projects, setProjects] = useState<Project[]>([]);

    // @Mention
    const [mentionQuery, setMentionQuery] = useState("");
    const [showMentionList, setShowMentionList] = useState(false);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const attachMenuRef = useRef<HTMLDivElement>(null);

    // ── Click-outside for menus ──────────────────────────────────────────────────

    useEffect(() => {
        if (!convMenuOpen) return;
        const handler = () => setConvMenuOpen(null);
        document.addEventListener("click", handler);
        return () => document.removeEventListener("click", handler);
    }, [convMenuOpen]);

    useEffect(() => {
        if (!showAttachMenu) return;
        const handler = (e: MouseEvent) => {
            if (attachMenuRef.current && !attachMenuRef.current.contains(e.target as Node)) {
                setShowAttachMenu(false);
            }
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, [showAttachMenu]);

    useEffect(() => {
        if (!showAgentPicker) return;
        const handler = () => setShowAgentPicker(false);
        document.addEventListener("click", handler);
        return () => document.removeEventListener("click", handler);
    }, [showAgentPicker]);

    // ── Data Fetching ────────────────────────────────────────────────────────────

    useEffect(() => {
        const storedUser = localStorage.getItem("sutra_user");
        if (storedUser) {
            try { setUser(JSON.parse(storedUser)); } catch { /* ignore */ }
        }

        projectsApi.list({ status: "active" }).then(setProjects).catch(() => {});

        agentsApi.list().then((list) => {
            const running = list.filter((a) => a.status === "running");
            setAgents(running);

            const dash = running.find(a => a.name === "Dash");
            const first = dash || (running.length > 0 ? running[0] : null);
            if (first && !selectedAgent) {
                setSelectedAgent(first);
                setExpandedAgents(new Set([first.id]));
            }

            running.forEach(agent => {
                chatApi.conversations(agent.id).then(convs => {
                    setAgentConversations(prev => ({ ...prev, [agent.id]: convs }));
                });
            });
        });

        // Load skills + purposes for + menu
        skillsApi.list().then(skills => setAvailableSkills(skills.filter(s => s.is_active))).catch(() => {});
        purposesApi.list().then(setAvailablePurposes).catch(() => {});

        // Check if Drive is connected
        googleDriveApi.list().then(integrations => {
            setDriveConnected(integrations.some(i => i.has_credentials && i.is_active));
        }).catch(() => {});
    }, []);

    useEffect(() => {
        if (selectedAgent && activeConversationId) {
            chatApi.messages(selectedAgent.id, activeConversationId).then(setMessages);
        } else {
            setMessages([]);
        }
    }, [selectedAgent, activeConversationId]);

    // WebSocket approvals
    useEffect(() => {
        wsClient.connect();
        const unsub = wsClient.on("approval_requested", (data: any) => {
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
        setInput(textBeforeCursor.slice(0, lastAtSymbol) + `@${agentName} ` + textAfterCursor);
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
        setConversationSkillIds([]);
        setPurposeOverrideId(null);
        if (inputRef.current) inputRef.current.focus();
    }, [selectedAgent]);

    const handleSelectConversation = (agentId: string, conversationId: string) => {
        setConvMenuOpen(null);
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

    const handleDeleteConversation = async (agentId: string, conversationId: string) => {
        setConvMenuOpen(null);
        await chatApi.deleteConversation(agentId, conversationId);
        if (activeConversationId === conversationId) {
            setActiveConversationId(null);
            setMessages([]);
        }
        setAgentConversations(prev => ({
            ...prev,
            [agentId]: (prev[agentId] || []).filter(c => c.id !== conversationId),
        }));
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
                    extra_skill_ids: conversationSkillIds.length > 0 ? conversationSkillIds : undefined,
                    purpose_override_id: purposeOverrideId || undefined,
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
                                    setAgentConversations(prev => ({ ...prev, [selectedAgent.id]: convs }));
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
                    } catch { /* ignore parse errors */ }
                }
            }

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

    // ── Schedule Task ────────────────────────────────────────────────────────────

    async function handleScheduleTask() {
        if (!scheduleLabel.trim() || !scheduleCron || !selectedAgent) return;
        setScheduleCreating(true);
        try {
            const label = scheduleLabel.slice(0, 120);
            await jobsApi.create({
                name: label,
                execution_type: "prompt",
                target_id: selectedAgent.id,
                prompt_text: scheduleLabel,
                cron_expression: scheduleCron,
                timezone: "America/Los_Angeles",
                is_active: true,
            });
            setScheduleSuccess(true);
        } catch (err) {
            console.error("Schedule failed:", err);
        } finally {
            setScheduleCreating(false);
        }
    }

    function openScheduleModal() {
        setShowAttachMenu(false);
        setScheduleLabel(input.trim());
        setSchedulePreset("daily_9am");
        setScheduleCron("0 9 * * *");
        setScheduleSuccess(false);
        setShowScheduleModal(true);
    }

    // ── Workflow Generator ───────────────────────────────────────────────────────

    async function handleGenerateWorkflow() {
        if (!workflowDescription.trim()) return;
        setGeneratingWorkflow(true);
        try {
            const wf = await workflowsApi.generateFromText(workflowDescription, selectedAgent?.id);
            setGeneratedWorkflowId(wf.id);
        } catch (err) {
            console.error("Workflow generation failed:", err);
        } finally {
            setGeneratingWorkflow(false);
        }
    }

    function openWorkflowModal() {
        setShowAttachMenu(false);
        setWorkflowDescription(input.trim());
        setGeneratedWorkflowId(null);
        setShowWorkflowModal(true);
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

    // ── File Upload Handler ───────────────────────────────────────────────────────

    async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
        const file = e.target.files?.[0];
        if (!file) return;
        setShowAttachMenu(false);
        setFileUploading(true);
        try {
            const result = await chatApi.extractFileContext(file);
            const prefix = `[Context from "${result.filename}"${result.truncated ? " (truncated)" : ""}]\n${result.content}\n\n---\n\n`;
            setInput(prev => prefix + prev);
            setTimeout(() => inputRef.current?.focus(), 0);
        } catch (err) {
            console.error("File extract failed:", err);
        } finally {
            setFileUploading(false);
            // Reset file input so same file can be picked again
            if (fileInputRef.current) fileInputRef.current.value = "";
        }
    }

    // ── Google Drive Search ───────────────────────────────────────────────────────

    async function handleDriveSearch(q: string) {
        setDriveSearchQuery(q);
        if (!q.trim()) { setDriveFiles([]); return; }
        setDriveSearching(true);
        try {
            const files = await googleDriveApi.searchFiles(q);
            setDriveFiles(files);
        } catch { setDriveFiles([]); }
        finally { setDriveSearching(false); }
    }

    function handleDriveFileSelect(file: { id: string; name: string }) {
        const ref = `[Please reference my Google Drive file: "${file.name}" (ID: ${file.id})]`;
        setInput(prev => prev ? `${prev}\n${ref}` : ref);
        setShowDriveDialog(false);
        setDriveSearchQuery("");
        setDriveFiles([]);
        setTimeout(() => inputRef.current?.focus(), 0);
    }

    // ── Skill Toggle ─────────────────────────────────────────────────────────────

    function toggleSkill(skillId: string) {
        setConversationSkillIds(prev =>
            prev.includes(skillId) ? prev.filter(id => id !== skillId) : [...prev, skillId]
        );
    }

    // ── Computed ─────────────────────────────────────────────────────────────────

    const filteredAgentsWithConvs = useMemo(() => {
        return agents.map(agent => {
            const convs = agentConversations[agent.id] || [];
            const filtered = convs.filter(c => c.title.toLowerCase().includes(searchQuery.toLowerCase()));
            return { ...agent, conversations: filtered };
        }).filter(a => a.conversations.length > 0);
    }, [agents, agentConversations, searchQuery]);

    const activePurpose = availablePurposes.find(p => p.id === purposeOverrideId);
    const hasConversation = messages.length > 0 || streaming;

    // ── Render ────────────────────────────────────────────────────────────────────

    return (
        <div className="flex h-full w-full bg-[#fafaf8] overflow-hidden">

            {/* ── Conversation Sidebar ─────────────────────────────────────────────── */}
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
                                    <span className="text-sm font-medium truncate flex-1 text-stone-700">{agent.name}</span>
                                    <span className="text-[10px] text-stone-400 font-medium bg-stone-100 px-1.5 rounded-full">{agent.conversations.length}</span>
                                </div>

                                {expandedAgents.has(agent.id) && (
                                    <div className="ml-4 pl-2 border-l border-stone-200 space-y-0.5">
                                        {agent.conversations.length === 0 ? (
                                            <p className="text-xs text-stone-400 py-1 pl-4">No threads</p>
                                        ) : (
                                            agent.conversations.map((conv) => (
                                                <div key={conv.id} className="relative">
                                                    <button
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
                                                        <div
                                                            className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-stone-200 rounded transition-opacity"
                                                            onClick={(e) => { e.stopPropagation(); setConvMenuOpen(convMenuOpen === conv.id ? null : conv.id); }}
                                                        >
                                                            <MoreVertical className="w-3 h-3 text-stone-400" />
                                                        </div>
                                                    </button>
                                                    {convMenuOpen === conv.id && (
                                                        <div className="absolute right-0 top-full mt-0.5 z-50 bg-white border border-stone-200 rounded-lg shadow-lg py-1 min-w-[120px]">
                                                            <button
                                                                onClick={() => handleDeleteConversation(agent.id, conv.id)}
                                                                className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
                                                            >
                                                                <Trash2 className="w-3.5 h-3.5" />
                                                                Delete
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
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

            {/* ── Main Area ─────────────────────────────────────────────────────────── */}
            <div className="flex-1 flex flex-col min-w-0 relative overflow-hidden">

                {/* ── Thin top bar (sidebar toggle + agent picker when in conversation) ── */}
                <header className="h-12 border-b border-stone-200/70 flex items-center gap-3 px-4 bg-white/90 backdrop-blur-md sticky top-0 z-30 flex-shrink-0">
                    <button
                        onClick={() => setSidebarOpen(v => !v)}
                        className="p-1.5 text-stone-400 hover:text-stone-600 hover:bg-stone-100 rounded-lg transition-colors"
                        title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
                    >
                        {sidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeftOpen className="w-4 h-4" />}
                    </button>

                    {hasConversation && (
                        <div className="relative" onClick={e => e.stopPropagation()}>
                            <button
                                onClick={() => setShowAgentPicker(v => !v)}
                                className="flex items-center gap-2 hover:bg-stone-50 px-2 py-1 rounded-lg transition-colors"
                            >
                                {selectedAgent ? (
                                    <>
                                        <AgentAvatar name={selectedAgent.name} avatarUrl={selectedAgent.avatar_url} size="sm" className="!w-6 !h-6 !text-[10px]" />
                                        <span className="text-sm font-medium text-stone-800">{selectedAgent.name}</span>
                                        <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
                                        <ChevronDown className="w-3.5 h-3.5 text-stone-400" />
                                    </>
                                ) : (
                                    <span className="text-sm text-stone-400">Select agent</span>
                                )}
                            </button>

                            {showAgentPicker && (
                                <div className="absolute left-0 top-full mt-2 w-56 bg-white border border-stone-200 rounded-xl p-1.5 z-50 shadow-lg">
                                    {agents.map((agent) => (
                                        <button
                                            key={agent.id}
                                            onClick={() => { setSelectedAgent(agent); setShowAgentPicker(false); handleNewChat(agent); }}
                                            className={`w-full flex items-center gap-3 p-2.5 rounded-lg transition-colors text-left ${selectedAgent?.id === agent.id ? "bg-stone-100" : "hover:bg-stone-50"}`}
                                        >
                                            <AgentAvatar name={agent.name} avatarUrl={agent.avatar_url} size="sm" />
                                            <div className="flex-1">
                                                <p className="text-sm font-medium text-stone-700">{agent.name}</p>
                                                <p className="text-[10px] text-stone-400 flex items-center gap-1"><Cpu className="w-2.5 h-2.5" />{agent.llm_model}</p>
                                            </div>
                                            {selectedAgent?.id === agent.id && <CheckCircle2 className="w-4 h-4 text-stone-500" />}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {hasConversation && activeProject && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full border border-stone-200 text-stone-500 flex items-center gap-1 ml-1">
                            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: activeProject.color || "#6b7280" }} />
                            {activeProject.name}
                        </span>
                    )}

                    {hasConversation && (
                        <button
                            onClick={() => handleNewChat()}
                            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-stone-600 hover:text-stone-800 hover:bg-stone-100 rounded-lg transition-colors"
                        >
                            <Plus className="w-3.5 h-3.5" />
                            New chat
                        </button>
                    )}
                </header>

                {/* ── Content ─────────────────────────────────────────────────────────── */}
                {!hasConversation ? (
                    /* ── Welcome / Empty State ── */
                    <div className="flex-1 flex flex-col items-center justify-center px-4 pb-8">
                        <div className="w-full max-w-2xl space-y-6">
                            <h1 className="text-4xl font-bold text-stone-800 text-center tracking-tight">
                                What can I do for you?
                            </h1>

                            {/* Input box */}
                            <div className="bg-white border border-stone-200 rounded-2xl shadow-sm p-3 space-y-2">
                                <textarea
                                    ref={inputRef}
                                    value={input}
                                    onChange={handleInputChange}
                                    onKeyDown={handleKeyDown}
                                    placeholder={selectedAgent ? `Message ${selectedAgent.name}...` : "Select an agent below to begin..."}
                                    disabled={!selectedAgent || streaming}
                                    className="w-full bg-transparent border-none focus:ring-0 focus:outline-none text-sm resize-none custom-scrollbar min-h-[60px] max-h-48 text-stone-800 placeholder:text-stone-400 px-1"
                                    rows={2}
                                />

                                {/* Active skill / purpose badges */}
                                {(conversationSkillIds.length > 0 || activePurpose) && (
                                    <div className="flex flex-wrap gap-1.5 px-1">
                                        {conversationSkillIds.length > 0 && (
                                            <span className="flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-violet-50 border border-violet-200 text-violet-700">
                                                <Puzzle className="w-2.5 h-2.5" />
                                                {conversationSkillIds.length} skill{conversationSkillIds.length > 1 ? "s" : ""} active
                                                <button onClick={() => setConversationSkillIds([])} className="hover:text-violet-900"><X className="w-2.5 h-2.5" /></button>
                                            </span>
                                        )}
                                        {activePurpose && (
                                            <span className="flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-50 border border-amber-200 text-amber-700">
                                                <Target className="w-2.5 h-2.5" />
                                                {activePurpose.name}
                                                <button onClick={() => setPurposeOverrideId(null)} className="hover:text-amber-900"><X className="w-2.5 h-2.5" /></button>
                                            </span>
                                        )}
                                    </div>
                                )}

                                {/* Bottom toolbar */}
                                <div className="flex items-center gap-1.5 px-1">
                                    {/* + attach menu */}
                                    <div className="relative" ref={attachMenuRef}>
                                        <button
                                            onClick={() => setShowAttachMenu(v => !v)}
                                            className={`p-2 rounded-lg transition-all ${showAttachMenu ? "bg-stone-200 text-stone-700" : "text-stone-400 hover:text-stone-600 hover:bg-stone-100"}`}
                                            title="Attach"
                                        >
                                            <Plus className="w-4 h-4" />
                                        </button>

                                        {showAttachMenu && (
                                            <div className="absolute bottom-full left-0 mb-2 w-56 bg-white border border-stone-200 rounded-xl shadow-lg p-1 z-50">
                                                {/* Local file */}
                                                <button
                                                    onClick={() => { setShowAttachMenu(false); fileInputRef.current?.click(); }}
                                                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                >
                                                    <Paperclip className="w-4 h-4 text-stone-500" />
                                                    <span className="text-sm text-stone-700">Add from local files</span>
                                                </button>

                                                {/* Skills */}
                                                <button
                                                    onClick={() => { setShowAttachMenu(false); setShowSkillPanel(true); }}
                                                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                >
                                                    <Puzzle className="w-4 h-4 text-stone-500" />
                                                    <span className="text-sm text-stone-700 flex-1">Use Skills</span>
                                                    {conversationSkillIds.length > 0 && (
                                                        <span className="text-[10px] bg-violet-100 text-violet-700 px-1.5 rounded-full font-medium">{conversationSkillIds.length}</span>
                                                    )}
                                                    <ChevronRight className="w-3.5 h-3.5 text-stone-400" />
                                                </button>

                                                {/* Google Drive (only if connected) */}
                                                {driveConnected && (
                                                    <button
                                                        onClick={() => { setShowAttachMenu(false); setShowDriveDialog(true); }}
                                                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                    >
                                                        <HardDrive className="w-4 h-4 text-stone-500" />
                                                        <span className="text-sm text-stone-700">Add from Google Drive</span>
                                                    </button>
                                                )}

                                                {/* Purpose */}
                                                <button
                                                    onClick={() => { setShowAttachMenu(false); setShowPurposeMenu(true); }}
                                                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                >
                                                    <Target className="w-4 h-4 text-stone-500" />
                                                    <span className="text-sm text-stone-700 flex-1">Select Purpose</span>
                                                    <ChevronRight className="w-3.5 h-3.5 text-stone-400" />
                                                </button>

                                                <div className="my-1 border-t border-stone-100" />

                                                {/* Schedule task */}
                                                <button
                                                    onClick={openScheduleModal}
                                                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                >
                                                    <Clock className="w-4 h-4 text-stone-500" />
                                                    <span className="text-sm text-stone-700">Schedule task</span>
                                                </button>

                                                {/* Create workflow */}
                                                <button
                                                    onClick={openWorkflowModal}
                                                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                >
                                                    <GitBranch className="w-4 h-4 text-stone-500" />
                                                    <span className="text-sm text-stone-700">Create workflow</span>
                                                </button>
                                            </div>
                                        )}
                                    </div>

                                    {fileUploading && <Loader2 className="w-4 h-4 text-stone-400 animate-spin ml-1" />}

                                    {/* Spacer */}
                                    <div className="flex-1" />

                                    {/* Agent picker pill */}
                                    <div className="relative" onClick={e => e.stopPropagation()}>
                                        <button
                                            onClick={() => setShowAgentPicker(v => !v)}
                                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-stone-200 hover:border-stone-300 hover:bg-stone-50 transition-colors text-sm text-stone-600"
                                        >
                                            {selectedAgent ? (
                                                <>
                                                    <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
                                                    {selectedAgent.name}
                                                </>
                                            ) : (
                                                <><Bot className="w-3.5 h-3.5" />Select agent</>
                                            )}
                                            <ChevronDown className="w-3 h-3 text-stone-400" />
                                        </button>

                                        {showAgentPicker && (
                                            <div className="absolute bottom-full right-0 mb-2 w-56 bg-white border border-stone-200 rounded-xl p-1.5 z-50 shadow-lg">
                                                {agents.length === 0 ? (
                                                    <p className="text-sm text-stone-400 p-3">No running agents.</p>
                                                ) : (
                                                    agents.map((agent) => (
                                                        <button
                                                            key={agent.id}
                                                            onClick={() => { setSelectedAgent(agent); setShowAgentPicker(false); }}
                                                            className={`w-full flex items-center gap-3 p-2.5 rounded-lg transition-colors text-left ${selectedAgent?.id === agent.id ? "bg-stone-100" : "hover:bg-stone-50"}`}
                                                        >
                                                            <AgentAvatar name={agent.name} avatarUrl={agent.avatar_url} size="sm" />
                                                            <div className="flex-1">
                                                                <p className="text-sm font-medium text-stone-700">{agent.name}</p>
                                                                <p className="text-[10px] text-stone-400">{agent.llm_model}</p>
                                                            </div>
                                                            {selectedAgent?.id === agent.id && <CheckCircle2 className="w-4 h-4 text-stone-500" />}
                                                        </button>
                                                    ))
                                                )}
                                            </div>
                                        )}
                                    </div>

                                    {/* Send button */}
                                    <button
                                        onClick={handleSend}
                                        disabled={!input.trim() || !selectedAgent || streaming}
                                        className={`p-2 rounded-xl transition-all ${
                                            !input.trim() || !selectedAgent || streaming
                                            ? "bg-stone-200 text-stone-400"
                                            : "bg-stone-800 hover:bg-stone-700 text-white shadow-sm"
                                        }`}
                                    >
                                        {streaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                    </button>
                                </div>
                            </div>

                            {/* Suggestion chips */}
                            <div className="grid grid-cols-2 gap-3">
                                {[
                                    { icon: Zap, label: "Orchestrate", text: "What can you help me with today?" },
                                    { icon: Terminal, label: "System", text: "Run a system health check" },
                                    { icon: MessageSquare, label: "Delegate", text: "Coordinate with other agents on a task" },
                                    { icon: Search, label: "Research", text: "Research and summarize a topic for me" },
                                ].map((s, i) => (
                                    <button
                                        key={i}
                                        onClick={() => setInput(s.text)}
                                        className="text-left p-4 rounded-xl bg-white border border-stone-200 hover:border-stone-300 hover:shadow-sm transition-all group"
                                    >
                                        <div className="flex items-center gap-2 mb-1.5">
                                            <s.icon className="w-3.5 h-3.5 text-stone-400" />
                                            <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-400">{s.label}</span>
                                        </div>
                                        <p className="text-sm text-stone-600 group-hover:text-stone-800">{s.text}</p>
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                ) : (
                    /* ── Active Conversation ── */
                    <>
                        <div className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-6 bg-[#fafaf8]">
                            <div className="max-w-3xl mx-auto w-full space-y-6">
                                {messages.map((msg) => (
                                    <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
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
                                                <span className="text-[10px] text-stone-400">{new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
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

                                {/* Streaming */}
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

                                {inlineApprovals.length > 0 && (
                                    <div className="flex flex-col gap-2">
                                        {inlineApprovals.map(approval => (
                                            <InlineApprovalCard key={approval.id} approval={approval} onDecide={handleApprovalDecision} />
                                        ))}
                                    </div>
                                )}

                                <div ref={messagesEndRef} />
                            </div>
                        </div>

                        {/* ── Input Bar (active conversation) ── */}
                        <div className="p-4 bg-[#fafaf8] border-t border-stone-200/70 flex-shrink-0">
                            <div className="max-w-3xl mx-auto w-full relative">
                                {/* Mention List */}
                                {showMentionList && (
                                    <div className="absolute bottom-full left-0 mb-2 w-60 bg-white border border-stone-200 rounded-xl shadow-lg p-1.5 z-50">
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
                                        </div>
                                    </div>
                                )}

                                <div className="bg-white border border-stone-200 rounded-2xl shadow-sm p-3 space-y-2">
                                    {/* Active badges */}
                                    {(conversationSkillIds.length > 0 || activePurpose) && (
                                        <div className="flex flex-wrap gap-1.5 px-1">
                                            {conversationSkillIds.length > 0 && (
                                                <span className="flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-violet-50 border border-violet-200 text-violet-700">
                                                    <Puzzle className="w-2.5 h-2.5" />
                                                    {conversationSkillIds.length} skill{conversationSkillIds.length > 1 ? "s" : ""} active
                                                    <button onClick={() => setConversationSkillIds([])}><X className="w-2.5 h-2.5" /></button>
                                                </span>
                                            )}
                                            {activePurpose && (
                                                <span className="flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-50 border border-amber-200 text-amber-700">
                                                    <Target className="w-2.5 h-2.5" />
                                                    {activePurpose.name}
                                                    <button onClick={() => setPurposeOverrideId(null)}><X className="w-2.5 h-2.5" /></button>
                                                </span>
                                            )}
                                        </div>
                                    )}

                                    <textarea
                                        ref={inputRef}
                                        value={input}
                                        onChange={handleInputChange}
                                        onKeyDown={handleKeyDown}
                                        placeholder={selectedAgent ? `Message ${selectedAgent.name}...` : "Select an agent to begin"}
                                        disabled={!selectedAgent || streaming}
                                        className="w-full bg-transparent border-none focus:ring-0 focus:outline-none text-sm py-1 resize-none custom-scrollbar min-h-[36px] max-h-48 text-stone-800 placeholder:text-stone-400 px-1"
                                        rows={1}
                                    />

                                    <div className="flex items-center gap-1.5 px-1">
                                        {/* + attach menu */}
                                        <div className="relative" ref={attachMenuRef}>
                                            <button
                                                onClick={() => setShowAttachMenu(v => !v)}
                                                className={`p-1.5 rounded-lg transition-all ${showAttachMenu ? "bg-stone-200 text-stone-700" : "text-stone-400 hover:text-stone-600 hover:bg-stone-100"}`}
                                                title="Attach"
                                            >
                                                <Plus className="w-4 h-4" />
                                            </button>

                                            {showAttachMenu && (
                                                <div className="absolute bottom-full left-0 mb-2 w-56 bg-white border border-stone-200 rounded-xl shadow-lg p-1 z-50">
                                                    <button
                                                        onClick={() => { setShowAttachMenu(false); fileInputRef.current?.click(); }}
                                                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                    >
                                                        <Paperclip className="w-4 h-4 text-stone-500" />
                                                        <span className="text-sm text-stone-700">Add from local files</span>
                                                    </button>
                                                    <button
                                                        onClick={() => { setShowAttachMenu(false); setShowSkillPanel(true); }}
                                                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                    >
                                                        <Puzzle className="w-4 h-4 text-stone-500" />
                                                        <span className="text-sm text-stone-700 flex-1">Use Skills</span>
                                                        {conversationSkillIds.length > 0 && (
                                                            <span className="text-[10px] bg-violet-100 text-violet-700 px-1.5 rounded-full font-medium">{conversationSkillIds.length}</span>
                                                        )}
                                                        <ChevronRight className="w-3.5 h-3.5 text-stone-400" />
                                                    </button>
                                                    {driveConnected && (
                                                        <button
                                                            onClick={() => { setShowAttachMenu(false); setShowDriveDialog(true); }}
                                                            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                        >
                                                            <HardDrive className="w-4 h-4 text-stone-500" />
                                                            <span className="text-sm text-stone-700">Add from Google Drive</span>
                                                        </button>
                                                    )}
                                                    <button
                                                        onClick={() => { setShowAttachMenu(false); setShowPurposeMenu(true); }}
                                                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                    >
                                                        <Target className="w-4 h-4 text-stone-500" />
                                                        <span className="text-sm text-stone-700 flex-1">Select Purpose</span>
                                                        <ChevronRight className="w-3.5 h-3.5 text-stone-400" />
                                                    </button>

                                                    <div className="my-1 border-t border-stone-100" />

                                                    <button
                                                        onClick={openScheduleModal}
                                                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                    >
                                                        <Clock className="w-4 h-4 text-stone-500" />
                                                        <span className="text-sm text-stone-700">Schedule task</span>
                                                    </button>
                                                    <button
                                                        onClick={openWorkflowModal}
                                                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                                    >
                                                        <GitBranch className="w-4 h-4 text-stone-500" />
                                                        <span className="text-sm text-stone-700">Create workflow</span>
                                                    </button>
                                                </div>
                                            )}
                                        </div>

                                        {fileUploading && <Loader2 className="w-3.5 h-3.5 text-stone-400 animate-spin" />}

                                        <div className="flex-1" />

                                        <button
                                            onClick={handleSend}
                                            disabled={!input.trim() || !selectedAgent || streaming}
                                            className={`p-2 rounded-xl transition-all ${
                                                !input.trim() || !selectedAgent || streaming
                                                ? "bg-stone-100 text-stone-400"
                                                : "bg-stone-800 hover:bg-stone-700 text-white shadow-sm"
                                            }`}
                                        >
                                            {streaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                        </button>
                                    </div>
                                </div>

                                <p className="text-[10px] text-center text-stone-400 mt-1.5">
                                    <kbd className="px-1.5 py-0.5 rounded bg-stone-100 text-[9px] border border-stone-200">Enter</kbd> to send &nbsp;
                                    <kbd className="px-1.5 py-0.5 rounded bg-stone-100 text-[9px] border border-stone-200">Shift+Enter</kbd> for new line
                                </p>
                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* ── Skills Modal ─────────────────────────────────────────────────────── */}
            {showSkillPanel && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/20" onClick={() => setShowSkillPanel(false)} />
                    <div className="relative bg-white rounded-2xl border border-stone-200 shadow-2xl w-80 max-h-[70vh] flex flex-col">
                        <div className="p-4 border-b border-stone-200 flex items-center justify-between">
                            <h3 className="text-base font-semibold text-stone-800">Use Skills</h3>
                            <button onClick={() => setShowSkillPanel(false)} className="p-1.5 hover:bg-stone-100 rounded-lg transition-colors">
                                <X className="w-4 h-4 text-stone-500" />
                            </button>
                        </div>
                        <div className="overflow-y-auto custom-scrollbar p-2 space-y-0.5">
                            {availableSkills.length === 0 ? (
                                <p className="text-sm text-stone-400 text-center py-8 px-4">No skills available. Add skills in the Skills page.</p>
                            ) : (
                                availableSkills.map(skill => {
                                    const active = conversationSkillIds.includes(skill.id);
                                    return (
                                        <button
                                            key={skill.id}
                                            onClick={() => toggleSkill(skill.id)}
                                            className={`w-full flex items-center gap-3 px-3 py-3 rounded-xl text-left transition-colors ${
                                                active ? "bg-stone-100" : "hover:bg-stone-50"
                                            }`}
                                        >
                                            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                                                active ? "border-stone-800 bg-stone-800" : "border-stone-300"
                                            }`}>
                                                {active && <div className="w-2 h-2 rounded-full bg-white" />}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <p className="text-sm font-medium text-stone-800">{skill.name}</p>
                                                {skill.description && (
                                                    <p className="text-xs text-stone-400 mt-0.5 leading-relaxed">{skill.description}</p>
                                                )}
                                            </div>
                                        </button>
                                    );
                                })
                            )}
                        </div>
                        {conversationSkillIds.length > 0 && (
                            <div className="p-3 border-t border-stone-100">
                                <p className="text-xs text-stone-500 font-medium text-center">
                                    {conversationSkillIds.length} skill{conversationSkillIds.length > 1 ? "s" : ""} active for this conversation
                                </p>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* ── Purpose Menu (modal) ─────────────────────────────────────────────── */}
            {showPurposeMenu && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/20" onClick={() => setShowPurposeMenu(false)} />
                    <div className="relative bg-white rounded-2xl border border-stone-200 shadow-2xl w-80 max-h-[70vh] flex flex-col">
                        <div className="p-4 border-b border-stone-200 flex items-center justify-between">
                            <h3 className="text-sm font-semibold text-stone-800">Select Purpose</h3>
                            <button onClick={() => setShowPurposeMenu(false)} className="p-1.5 hover:bg-stone-100 rounded-lg transition-colors">
                                <X className="w-4 h-4 text-stone-500" />
                            </button>
                        </div>
                        <div className="overflow-y-auto custom-scrollbar p-2 space-y-1">
                            <button
                                onClick={() => { setPurposeOverrideId(null); setShowPurposeMenu(false); }}
                                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-colors ${!purposeOverrideId ? "bg-stone-100" : "hover:bg-stone-50"}`}
                            >
                                <span className="text-sm text-stone-600 flex-1">Use agent default</span>
                                {!purposeOverrideId && <Check className="w-4 h-4 text-stone-500" />}
                            </button>
                            {availablePurposes.map(purpose => (
                                <button
                                    key={purpose.id}
                                    onClick={() => { setPurposeOverrideId(purpose.id); setShowPurposeMenu(false); }}
                                    className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-xl text-left transition-colors ${purposeOverrideId === purpose.id ? "bg-amber-50 border border-amber-200" : "hover:bg-stone-50"}`}
                                >
                                    <Target className="w-4 h-4 text-stone-400 mt-0.5 flex-shrink-0" />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium text-stone-800">{purpose.name}</p>
                                        {purpose.description && <p className="text-xs text-stone-500 mt-0.5">{purpose.description}</p>}
                                    </div>
                                    {purposeOverrideId === purpose.id && <Check className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* ── Google Drive Dialog ──────────────────────────────────────────────── */}
            {showDriveDialog && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/20" onClick={() => setShowDriveDialog(false)} />
                    <div className="relative bg-white rounded-2xl border border-stone-200 shadow-2xl w-96 flex flex-col max-h-[70vh]">
                        <div className="p-4 border-b border-stone-200 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <HardDrive className="w-4 h-4 text-stone-500" />
                                <h3 className="text-sm font-semibold text-stone-800">Add from Google Drive</h3>
                            </div>
                            <button onClick={() => setShowDriveDialog(false)} className="p-1.5 hover:bg-stone-100 rounded-lg transition-colors">
                                <X className="w-4 h-4 text-stone-500" />
                            </button>
                        </div>
                        <div className="p-3 border-b border-stone-100">
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
                                <input
                                    type="text"
                                    placeholder="Search your Drive files..."
                                    value={driveSearchQuery}
                                    onChange={e => handleDriveSearch(e.target.value)}
                                    className="w-full pl-9 pr-4 py-2 border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-300/50 focus:border-stone-300"
                                    autoFocus
                                />
                            </div>
                        </div>
                        <div className="flex-1 overflow-y-auto custom-scrollbar p-2 min-h-[120px]">
                            {driveSearching ? (
                                <div className="flex items-center justify-center py-8">
                                    <Loader2 className="w-5 h-5 text-stone-400 animate-spin" />
                                </div>
                            ) : driveFiles.length === 0 && driveSearchQuery ? (
                                <p className="text-sm text-stone-400 text-center py-6">No files found for &ldquo;{driveSearchQuery}&rdquo;</p>
                            ) : driveFiles.length === 0 ? (
                                <p className="text-sm text-stone-400 text-center py-6">Type to search your Drive files</p>
                            ) : (
                                driveFiles.map(file => (
                                    <button
                                        key={file.id}
                                        onClick={() => handleDriveFileSelect(file)}
                                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-stone-50 transition-colors text-left"
                                    >
                                        <HardDrive className="w-4 h-4 text-stone-400 flex-shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm text-stone-700 truncate">{file.name}</p>
                                            <p className="text-[10px] text-stone-400">{new Date(file.modifiedTime).toLocaleDateString()}</p>
                                        </div>
                                    </button>
                                ))
                            )}
                        </div>
                        <div className="p-3 border-t border-stone-100">
                            <p className="text-xs text-stone-400 text-center">The agent will read the file using its Google Drive tools</p>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Schedule Task Modal ──────────────────────────────────────────────── */}
            {showScheduleModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/20" onClick={() => { setShowScheduleModal(false); setScheduleSuccess(false); }} />
                    <div className="relative bg-white rounded-2xl border border-stone-200 shadow-2xl w-96 flex flex-col">
                        <div className="p-4 border-b border-stone-200 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Clock className="w-4 h-4 text-stone-500" />
                                <h3 className="text-sm font-semibold text-stone-800">Schedule Task</h3>
                            </div>
                            <button onClick={() => { setShowScheduleModal(false); setScheduleSuccess(false); }} className="p-1.5 hover:bg-stone-100 rounded-lg transition-colors">
                                <X className="w-4 h-4 text-stone-500" />
                            </button>
                        </div>
                        <div className="p-4 space-y-4">
                            {scheduleSuccess ? (
                                <div className="text-center py-6 space-y-3">
                                    <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
                                    <p className="text-sm font-medium text-stone-800">Task scheduled!</p>
                                    <Link href="/jobs" className="text-xs text-stone-500 hover:text-stone-700 underline">View in Jobs →</Link>
                                </div>
                            ) : (
                                <>
                                    <div>
                                        <label className="block text-xs font-medium text-stone-600 mb-1.5">Task</label>
                                        <textarea
                                            value={scheduleLabel}
                                            onChange={e => setScheduleLabel(e.target.value)}
                                            className="w-full px-3 py-2 border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-300/50 resize-none"
                                            rows={2}
                                            placeholder="What should the agent do?"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-stone-600 mb-2">Recurrence</label>
                                        <div className="grid grid-cols-2 gap-2">
                                            {[
                                                { id: "hourly", label: "Every hour", cron: "0 * * * *" },
                                                { id: "daily_9am", label: "Daily at 9am", cron: "0 9 * * *" },
                                                { id: "weekdays", label: "Weekdays 9am", cron: "0 9 * * 1-5" },
                                                { id: "weekly", label: "Every Monday", cron: "0 9 * * 1" },
                                                { id: "custom", label: "Custom cron…", cron: "" },
                                            ].map(p => (
                                                <button
                                                    key={p.id}
                                                    onClick={() => { setSchedulePreset(p.id); if (p.cron) setScheduleCron(p.cron); }}
                                                    className={`px-3 py-2 rounded-lg text-sm text-left transition-colors border ${
                                                        schedulePreset === p.id
                                                            ? "bg-stone-800 text-white border-stone-800"
                                                            : "border-stone-200 hover:bg-stone-50 text-stone-700"
                                                    }`}
                                                >
                                                    {p.label}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                    {schedulePreset === "custom" && (
                                        <div>
                                            <label className="block text-xs font-medium text-stone-600 mb-1.5">Cron Expression</label>
                                            <input
                                                type="text"
                                                value={scheduleCron}
                                                onChange={e => setScheduleCron(e.target.value)}
                                                placeholder="0 9 * * 1-5"
                                                className="w-full px-3 py-2 border border-stone-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-stone-300/50"
                                            />
                                            <p className="text-[10px] text-stone-400 mt-1">5-field cron: minute hour day month weekday</p>
                                        </div>
                                    )}
                                    <button
                                        onClick={handleScheduleTask}
                                        disabled={scheduleCreating || !scheduleLabel.trim() || !scheduleCron}
                                        className="w-full py-2 px-4 bg-stone-800 text-white text-sm font-medium rounded-lg hover:bg-stone-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                                    >
                                        {scheduleCreating ? <><Loader2 className="w-4 h-4 animate-spin" />Scheduling...</> : <><Clock className="w-4 h-4" />Schedule Task</>}
                                    </button>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* ── Create Workflow Modal ─────────────────────────────────────────────── */}
            {showWorkflowModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/20" onClick={() => { setShowWorkflowModal(false); setGeneratedWorkflowId(null); }} />
                    <div className="relative bg-white rounded-2xl border border-stone-200 shadow-2xl w-[480px] flex flex-col">
                        <div className="p-4 border-b border-stone-200 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <GitBranch className="w-4 h-4 text-stone-500" />
                                <h3 className="text-sm font-semibold text-stone-800">Create Workflow</h3>
                            </div>
                            <button onClick={() => { setShowWorkflowModal(false); setGeneratedWorkflowId(null); }} className="p-1.5 hover:bg-stone-100 rounded-lg transition-colors">
                                <X className="w-4 h-4 text-stone-500" />
                            </button>
                        </div>
                        <div className="p-4 space-y-4">
                            {generatedWorkflowId ? (
                                <div className="text-center py-6 space-y-3">
                                    <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
                                    <p className="text-sm font-medium text-stone-800">Workflow created!</p>
                                    <p className="text-xs text-stone-400">Saved as draft — configure agents before activating.</p>
                                    <Link
                                        href={`/workflows/${generatedWorkflowId}`}
                                        className="inline-flex items-center gap-1.5 text-sm text-stone-600 hover:text-stone-800 bg-stone-100 hover:bg-stone-200 px-4 py-2 rounded-lg transition-colors"
                                    >
                                        <GitBranch className="w-3.5 h-3.5" />
                                        Open in builder →
                                    </Link>
                                </div>
                            ) : (
                                <>
                                    <div>
                                        <label className="block text-xs font-medium text-stone-600 mb-1.5">Describe your workflow</label>
                                        <textarea
                                            value={workflowDescription}
                                            onChange={e => setWorkflowDescription(e.target.value)}
                                            className="w-full px-3 py-2 border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-300/50 resize-none"
                                            rows={4}
                                            placeholder="e.g. Fetch latest news, summarize it, then post to Slack every morning..."
                                            autoFocus
                                        />
                                    </div>
                                    <p className="text-xs text-stone-400">
                                        The workflow is generated using AI and saved as a draft. You can edit it in the builder before activating.
                                    </p>
                                    <button
                                        onClick={handleGenerateWorkflow}
                                        disabled={generatingWorkflow || !workflowDescription.trim()}
                                        className="w-full py-2 px-4 bg-stone-800 text-white text-sm font-medium rounded-lg hover:bg-stone-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                                    >
                                        {generatingWorkflow
                                            ? <><Loader2 className="w-4 h-4 animate-spin" />Generating...</>
                                            : <><GitBranch className="w-4 h-4" />Generate Workflow</>
                                        }
                                    </button>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* ── Hidden File Input ─────────────────────────────────────────────────── */}
            <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.txt,.md,.csv,.json,.rst"
                className="hidden"
                onChange={handleFileSelected}
            />
        </div>
    );
}
