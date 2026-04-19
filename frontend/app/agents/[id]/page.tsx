"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import {
    ArrowLeft,
    Save,
    Bot,
    Sparkles,
    Cpu,
    Wrench,
    Trash2,
    Play,
    Square,
    MessageSquare,
    AlertTriangle,
    Folder as FolderIcon,
    Send,
    ChevronDown,
    ChevronRight,
    CheckSquare,
    Square as SquareIcon,
} from "lucide-react";
import {
    agentsApi,
    toolsApi,
    llmsApi,
    foldersApi,
    purposesApi,
    type Agent,
    type ToolInfo,
    type OllamaModel,
    type OpenRouterModel,
    type GeminiModel,
    type PerplexityModel,
    type GroqModel,
    type Folder,
    type LLMPurpose,
} from "@/lib/api";
import { ProviderModelSelect } from "@/components/ProviderModelSelect";
import { SkillsSection } from "@/components/SkillsSection";
import AgentAvatar, { AvatarPicker } from "@/components/AgentAvatar";

// ─── Category config ──────────────────────────────────────────────────────────

const CATEGORY_META: Record<string, { label: string; color: string; defaultOpen: boolean }> = {
    agent:          { label: "Agent",          color: "text-violet-600 bg-violet-50 border-violet-200 dark:bg-violet-950/30 dark:border-violet-800",  defaultOpen: true },
    tasks:          { label: "Tasks",          color: "text-blue-600 bg-blue-50 border-blue-200 dark:bg-blue-950/30 dark:border-blue-800",            defaultOpen: true },
    collaboration:  { label: "Collaboration",  color: "text-sky-600 bg-sky-50 border-sky-200 dark:bg-sky-950/30 dark:border-sky-800",                 defaultOpen: true },
    knowledge:      { label: "Knowledge",      color: "text-emerald-600 bg-emerald-50 border-emerald-200 dark:bg-emerald-950/30 dark:border-emerald-800", defaultOpen: true },
    memory:         { label: "Memory",         color: "text-teal-600 bg-teal-50 border-teal-200 dark:bg-teal-950/30 dark:border-teal-800",             defaultOpen: true },
    communication:  { label: "Communication",  color: "text-pink-600 bg-pink-50 border-pink-200 dark:bg-pink-950/30 dark:border-pink-800",             defaultOpen: false },
    integrations:   { label: "Integrations",   color: "text-indigo-600 bg-indigo-50 border-indigo-200 dark:bg-indigo-950/30 dark:border-indigo-800",   defaultOpen: false },
    developer:      { label: "Developer",      color: "text-amber-600 bg-amber-50 border-amber-200 dark:bg-amber-950/30 dark:border-amber-800",        defaultOpen: false },
    os:             { label: "System / OS",    color: "text-stone-600 bg-stone-50 border-stone-200 dark:bg-stone-950/30 dark:border-stone-700",        defaultOpen: false },
    data:           { label: "Data",           color: "text-orange-600 bg-orange-50 border-orange-200 dark:bg-orange-950/30 dark:border-orange-800",   defaultOpen: false },
    factory:        { label: "Agent Factory",  color: "text-rose-600 bg-rose-50 border-rose-200 dark:bg-rose-950/30 dark:border-rose-800",             defaultOpen: false },
    safety:         { label: "Safety",         color: "text-green-600 bg-green-50 border-green-200 dark:bg-green-950/30 dark:border-green-800",        defaultOpen: true },
    goals:          { label: "Goals",          color: "text-yellow-600 bg-yellow-50 border-yellow-200 dark:bg-yellow-950/30 dark:border-yellow-800",    defaultOpen: true },
    autonomy:       { label: "Autonomy",       color: "text-cyan-600 bg-cyan-50 border-cyan-200 dark:bg-cyan-950/30 dark:border-cyan-800",              defaultOpen: true },
    workflows:      { label: "Workflows",      color: "text-indigo-600 bg-indigo-50 border-indigo-200 dark:bg-indigo-950/30 dark:border-indigo-800",    defaultOpen: true },
    forge:          { label: "Forge",          color: "text-slate-600 bg-slate-50 border-slate-200 dark:bg-slate-950/30 dark:border-slate-800",          defaultOpen: false },
};

const CATEGORY_ORDER = [
    "agent", "tasks", "goals", "collaboration", "knowledge", "memory", "safety",
    "autonomy", "workflows", "communication", "integrations", "developer", "os", "data", "factory", "forge",
];

// ─── ToolsSection component ───────────────────────────────────────────────────

function ToolsSection({
    tools,
    enabledTools,
    onToggle,
}: {
    tools: import("@/lib/api").ToolInfo[];
    enabledTools: string[];
    onToggle: (id: string) => void;
}) {
    // Group tools by category
    const grouped: Record<string, import("@/lib/api").ToolInfo[]> = {};
    for (const tool of tools) {
        const cat = tool.category || "other";
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(tool);
    }

    // Build ordered list: known categories first, then any unknown ones
    const orderedCats = [
        ...CATEGORY_ORDER.filter(c => grouped[c]),
        ...Object.keys(grouped).filter(c => !CATEGORY_ORDER.includes(c)),
    ];

    // Track which sections are open
    const [openSections, setOpenSections] = useState<Record<string, boolean>>(() => {
        const init: Record<string, boolean> = {};
        for (const cat of orderedCats) {
            init[cat] = CATEGORY_META[cat]?.defaultOpen ?? false;
        }
        return init;
    });

    function toggleSection(cat: string) {
        setOpenSections(p => ({ ...p, [cat]: !p[cat] }));
    }

    function toggleAll(cat: string, catTools: import("@/lib/api").ToolInfo[]) {
        const allEnabled = catTools.every(t => enabledTools.includes(t.id));
        for (const t of catTools) {
            const currently = enabledTools.includes(t.id);
            if (allEnabled ? currently : !currently) onToggle(t.id);
        }
    }

    const totalEnabled = enabledTools.length;

    return (
        <div className="glass-card p-6 space-y-3">
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                    <Wrench className="w-5 h-5 text-amber-500" /> Tools
                </h2>
                {totalEnabled > 0 && (
                    <span className="text-xs bg-stone-200 dark:bg-stone-800/40 text-stone-700 dark:text-stone-400 px-2.5 py-1 rounded-full font-medium">
                        {totalEnabled} enabled
                    </span>
                )}
            </div>

            <div className="space-y-2">
                {orderedCats.map(cat => {
                    const catTools = grouped[cat];
                    const meta = CATEGORY_META[cat] ?? { label: cat, color: "text-stone-600 bg-stone-50 border-stone-200", defaultOpen: false };
                    const isOpen = openSections[cat] ?? false;
                    const enabledCount = catTools.filter(t => enabledTools.includes(t.id)).length;
                    const allEnabled = enabledCount === catTools.length;

                    return (
                        <div key={cat} className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
                            {/* Section header */}
                            <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-50 dark:bg-gray-800/50">
                                <button
                                    type="button"
                                    onClick={() => toggleSection(cat)}
                                    className="flex items-center gap-2 flex-1 min-w-0 text-left"
                                >
                                    {isOpen
                                        ? <ChevronDown className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                                        : <ChevronRight className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                                    }
                                    <span className={`text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border ${meta.color}`}>
                                        {meta.label}
                                    </span>
                                    <span className="text-xs text-gray-400">
                                        {enabledCount > 0 ? `${enabledCount}/${catTools.length}` : catTools.length} tools
                                    </span>
                                </button>
                                {/* Select/deselect all in category */}
                                <button
                                    type="button"
                                    onClick={() => toggleAll(cat, catTools)}
                                    className="text-xs text-gray-400 hover:text-stone-700 dark:hover:text-stone-500 flex items-center gap-1 flex-shrink-0"
                                    title={allEnabled ? "Disable all" : "Enable all"}
                                >
                                    {allEnabled
                                        ? <CheckSquare className="w-4 h-4" />
                                        : <SquareIcon className="w-4 h-4" />
                                    }
                                </button>
                            </div>

                            {/* Tool grid */}
                            {isOpen && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 p-3">
                                    {catTools.map(tool => (
                                        <label
                                            key={tool.id}
                                            className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all duration-200 ${
                                                enabledTools.includes(tool.id)
                                                    ? "bg-stone-100 dark:bg-stone-900/30 border-stone-400 dark:border-stone-600"
                                                    : "bg-surface-1 dark:bg-surface-dark2 border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                                            }`}
                                        >
                                            <input
                                                type="checkbox"
                                                checked={enabledTools.includes(tool.id)}
                                                onChange={() => onToggle(tool.id)}
                                                className="sr-only"
                                            />
                                            <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${
                                                enabledTools.includes(tool.id)
                                                    ? "bg-stone-700 text-white"
                                                    : "bg-surface-2 dark:bg-surface-dark3 text-gray-400"
                                            }`}>
                                                <Wrench className="w-4 h-4" />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-1.5">
                                                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                                                        {tool.name}
                                                    </span>
                                                    {tool.is_dangerous && (
                                                        <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                                                    )}
                                                </div>
                                                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                                                    {tool.description}
                                                </p>
                                            </div>
                                        </label>
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export default function AgentDetailPage() {
    const router = useRouter();
    const params = useParams();
    const agentId = params.id as string;

    const [agent, setAgent] = useState<Agent | null>(null);
    const [tools, setTools] = useState<ToolInfo[]>([]);
    const [ollamaModels, setOllamaModels] = useState<OllamaModel[]>([]);
    const [openRouterModels, setOpenRouterModels] = useState<OpenRouterModel[]>([]);
    const [loadingOpenRouterModels, setLoadingOpenRouterModels] = useState(false);
    const [geminiModels, setGeminiModels] = useState<GeminiModel[]>([]);
    const [loadingGeminiModels, setLoadingGeminiModels] = useState(false);
    const [perplexityModels, setPerplexityModels] = useState<PerplexityModel[]>([]);
    const [loadingPerplexityModels, setLoadingPerplexityModels] = useState(false);
    const [groqModels, setGroqModels] = useState<GroqModel[]>([]);
    const [loadingGroqModels, setLoadingGroqModels] = useState(false);
    const [modelSearch, setModelSearch] = useState("");
    const [folders, setFolders] = useState<Folder[]>([]);
    const [purposes, setPurposes] = useState<LLMPurpose[]>([]);
    const [saving, setSaving] = useState(false);
    const [loading, setLoading] = useState(true);

    // Form state
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [purposeId, setPurposeId] = useState<string>("");
    const [systemPrompt, setSystemPrompt] = useState("");
    const [temperature, setTemperature] = useState(0.7);
    const [maxTokens, setMaxTokens] = useState(4096);
    const [llmProvider, setLlmProvider] = useState("ollama");
    const [llmModel, setLlmModel] = useState("llama3");
    const [secondaryProvider, setSecondaryProvider] = useState("");
    const [secondaryModel, setSecondaryModel] = useState("");
    const [fallbackProvider, setFallbackProvider] = useState("");
    const [fallbackModel, setFallbackModel] = useState("");
    const [enabledTools, setEnabledTools] = useState<string[]>([]);
    const [folderId, setFolderId] = useState<string>("");
    const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
    const [telegramChatId, setTelegramChatId] = useState("");
    const [telegramEnabled, setTelegramEnabled] = useState(false);
    const [onlineNotificationEnabled, setOnlineNotificationEnabled] = useState(false);
    // Autonomy controls
    const [autoApproveBelow, setAutoApproveBelow] = useState<string>("");
    const [maxToolCallsPerRun, setMaxToolCallsPerRun] = useState(0);
    const [maxTokensPerDay, setMaxTokensPerDay] = useState(0);

    useEffect(() => {
        async function load() {
            try {
                const [agentData, toolList, models, folderList, purposeList] = await Promise.all([
                    agentsApi.get(agentId),
                    toolsApi.list(),
                    llmsApi.ollamaModels().catch(() => []),
                    foldersApi.list().catch(() => []),
                    purposesApi.list().catch(() => []),
                ]);
                setAgent(agentData);
                setTools(toolList);
                setOllamaModels(models);
                setFolders(folderList);
                setPurposes(purposeList);

                // Populate form
                setName(agentData.name);
                setDescription(agentData.description || "");
                setPurposeId(agentData.purpose_id || "");
                setSystemPrompt(agentData.system_prompt);
                setTemperature(agentData.temperature);
                setMaxTokens(agentData.max_tokens);
                setLlmProvider(agentData.llm_provider);
                setLlmModel(agentData.llm_model);
                setSecondaryProvider(agentData.secondary_provider || "");
                setSecondaryModel(agentData.secondary_model || "");
                setFallbackProvider(agentData.fallback_provider || "");
                setFallbackModel(agentData.fallback_model || "");
                setEnabledTools(agentData.enabled_tools || []);
                setFolderId(agentData.folder_id || "");
                setAvatarUrl(agentData.avatar_url || null);
                setTelegramChatId(agentData.telegram_chat_id || "");
                setTelegramEnabled(agentData.telegram_enabled || false);
                setOnlineNotificationEnabled(agentData.online_notification_enabled || false);
                setAutoApproveBelow(agentData.auto_approve_below || "");
                setMaxToolCallsPerRun(agentData.max_tool_calls_per_run || 0);
                setMaxTokensPerDay(agentData.max_tokens_per_day || 0);
            } catch (err) {
                console.error("Failed to load agent:", err);
            } finally {
                setLoading(false);
            }
        }
        load();
    }, [agentId]);

    // Fetch OpenRouter models when any provider is openrouter
    useEffect(() => {
        if (llmProvider !== "openrouter" && secondaryProvider !== "openrouter" && fallbackProvider !== "openrouter") return;
        if (openRouterModels.length > 0) return;
        setLoadingOpenRouterModels(true);
        llmsApi.openRouterModels()
            .then((models) => {
                setOpenRouterModels(models);
            })
            .catch(() => { })
            .finally(() => setLoadingOpenRouterModels(false));
    }, [llmProvider, secondaryProvider, fallbackProvider]);

    // Fetch Gemini models when any provider is google
    useEffect(() => {
        if (llmProvider !== "google" && secondaryProvider !== "google" && fallbackProvider !== "google") return;
        if (geminiModels.length > 0) return;
        setLoadingGeminiModels(true);
        llmsApi.googleModels()
            .then((models) => {
                setGeminiModels(models);
            })
            .catch(() => { })
            .finally(() => setLoadingGeminiModels(false));
    }, [llmProvider, secondaryProvider, fallbackProvider]);

    // Fetch Perplexity models when any provider is perplexity
    useEffect(() => {
        if (llmProvider !== "perplexity" && secondaryProvider !== "perplexity" && fallbackProvider !== "perplexity") return;
        if (perplexityModels.length > 0) return;
        setLoadingPerplexityModels(true);
        llmsApi.perplexityModels()
            .then((models) => {
                setPerplexityModels(models);
            })
            .catch(() => { })
            .finally(() => setLoadingPerplexityModels(false));
    }, [llmProvider, secondaryProvider, fallbackProvider]);

    // Fetch Groq models when any provider is groq
    useEffect(() => {
        if (llmProvider !== "groq" && secondaryProvider !== "groq" && fallbackProvider !== "groq") return;
        if (groqModels.length > 0) return;
        setLoadingGroqModels(true);
        llmsApi.groqModels()
            .then((models) => {
                setGroqModels(models);
            })
            .catch(() => { })
            .finally(() => setLoadingGroqModels(false));
    }, [llmProvider, secondaryProvider, fallbackProvider]);

    function getDefaultModel(provider: string): string {
        const defaults: Record<string, string> = {
            ollama: ollamaModels[0]?.name ?? "llama3",
            openai: "gpt-4o",
            anthropic: "claude-3-5-sonnet-20241022",
            google: "gemini-1.5-pro",
            openrouter: openRouterModels[0]?.id ?? "openai/gpt-4o",
            perplexity: perplexityModels[0]?.id ?? "sonar-pro",
            groq: groqModels[0]?.id ?? "llama3-8b-8192",
        };
        return defaults[provider] ?? "";
    }

    function handleProviderChange(provider: string) {
        setLlmProvider(provider);
        setLlmModel(getDefaultModel(provider));
    }

    function handleSecondaryProviderChange(provider: string) {
        setSecondaryProvider(provider);
        setSecondaryModel(provider ? getDefaultModel(provider) : "");
    }

    function handleFallbackProviderChange(provider: string) {
        setFallbackProvider(provider);
        setFallbackModel(provider ? getDefaultModel(provider) : "");
    }

    function toggleTool(toolId: string) {
        setEnabledTools((prev) =>
            prev.includes(toolId)
                ? prev.filter((t) => t !== toolId)
                : [...prev, toolId]
        );
    }

    async function handleSave(e: React.FormEvent) {
        e.preventDefault();
        setSaving(true);
        try {
            await agentsApi.update(agentId, {
                name,
                description: description || null,
                avatar_url: avatarUrl,
                system_prompt: systemPrompt,
                temperature,
                max_tokens: maxTokens,
                purpose_id: purposeId || null,
                llm_provider: llmProvider,
                llm_model: llmModel,
                secondary_provider: secondaryProvider || null,
                secondary_model: secondaryModel || null,
                fallback_provider: fallbackProvider || null,
                fallback_model: fallbackModel || null,
                enabled_tools: enabledTools,
                folder_id: folderId || null,
                telegram_chat_id: telegramChatId || null,
                telegram_enabled: telegramEnabled,
                online_notification_enabled: onlineNotificationEnabled,
                auto_approve_below: autoApproveBelow || null,
                max_tool_calls_per_run: maxToolCallsPerRun,
                max_tokens_per_day: maxTokensPerDay,
            });
            // Reload agent data
            const updated = await agentsApi.get(agentId);
            setAgent(updated);
        } catch (err) {
            console.error("Failed to save agent:", err);
            alert("Failed to save. Check console for details.");
        } finally {
            setSaving(false);
        }
    }

    async function handleStart() {
        try {
            await agentsApi.start(agentId);
            const updated = await agentsApi.get(agentId);
            setAgent(updated);
        } catch (err) {
            console.error("Failed to start agent:", err);
        }
    }

    async function handleStop() {
        try {
            await agentsApi.stop(agentId);
            const updated = await agentsApi.get(agentId);
            setAgent(updated);
        } catch (err) {
            console.error("Failed to stop agent:", err);
        }
    }

    async function handleDelete() {
        if (!confirm(`Delete agent "${name}"? This cannot be undone.`)) return;
        try {
            await agentsApi.delete(agentId);
            router.push("/agents");
        } catch (err) {
            console.error("Failed to delete agent:", err);
        }
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64 text-gray-400">
                Loading agent...
            </div>
        );
    }

    if (!agent) {
        return (
            <div className="text-center py-20">
                <p className="text-gray-400">Agent not found</p>
            </div>
        );
    }

    return (
        <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <button onClick={() => router.push("/agents")} className="btn-icon">
                        <ArrowLeft className="w-5 h-5" />
                    </button>
                    <div>
                        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                            {agent.name}
                        </h1>
                        <div className="flex items-center gap-2 mt-1">
                            <div
                                className={`status-dot ${agent.status === "running"
                                    ? "status-dot-running"
                                    : agent.status === "error"
                                        ? "status-dot-error"
                                        : "status-dot-stopped"
                                    }`}
                            />
                            <span className="text-sm text-gray-400 capitalize">
                                {agent.status}
                            </span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {agent.status === "running" ? (
                        <>
                            <button onClick={handleStop} className="btn-secondary flex items-center gap-1.5">
                                <Square className="w-4 h-4" /> Stop
                            </button>
                            <button
                                onClick={() => router.push(`/chat`)}
                                className="btn-primary flex items-center gap-1.5"
                            >
                                <MessageSquare className="w-4 h-4" /> Chat
                            </button>
                        </>
                    ) : (
                        <button onClick={handleStart} className="btn-primary flex items-center gap-1.5">
                            <Play className="w-4 h-4" /> Start
                        </button>
                    )}
                </div>
            </div>

            {/* Edit Form (same structure as create) */}
            <form onSubmit={handleSave} className="space-y-6">
                {/* Identity */}
                <div className="glass-card p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Bot className="w-5 h-5 text-stone-600" /> Identity
                    </h2>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Avatar
                        </label>
                        <div className="flex items-center gap-4 mb-1">
                            <AgentAvatar name={name} avatarUrl={avatarUrl} size="lg" />
                            <p className="text-xs text-gray-500">Pick an avatar to give your agent personality</p>
                        </div>
                        <AvatarPicker selected={avatarUrl} onSelect={setAvatarUrl} />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Agent Name
                            </label>
                            <input
                                type="text"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                className="input"
                                required
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Description
                            </label>
                            <input
                                type="text"
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                className="input"
                            />
                        </div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            System Prompt
                        </label>
                        <textarea
                            value={systemPrompt}
                            onChange={(e) => setSystemPrompt(e.target.value)}
                            className="textarea h-32 font-mono text-sm"
                        />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Temperature: {temperature.toFixed(1)}
                            </label>
                            <input
                                type="range"
                                min={0}
                                max={2}
                                step={0.1}
                                value={temperature}
                                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                                className="w-full accent-stone-600"
                            />
                            <div className="flex justify-between text-xs text-gray-400 mt-1">
                                <span>Precise</span>
                                <span>Creative</span>
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Max Tokens
                            </label>
                            <input
                                type="number"
                                value={maxTokens}
                                onChange={(e) => setMaxTokens(parseInt(e.target.value) || 0)}
                                className="input"
                            />
                        </div>
                    </div>
                </div>

                {/* LLM Purpose */}
                <div className="glass-card p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Cpu className="w-5 h-5 text-emerald-500" /> LLM Purpose
                    </h2>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            Purpose (Smart Routing)
                        </label>
                        <select
                            value={purposeId}
                            onChange={(e) => setPurposeId(e.target.value)}
                            className="input"
                        >
                            <option value="">Select a purpose...</option>
                            {purposes.map((p) => (
                                <option key={p.id} value={p.id}>
                                    {p.name}{p.description ? ` — ${p.description}` : ""}
                                </option>
                            ))}
                        </select>
                        <p className="text-xs text-gray-400 mt-1">
                            The smart router picks the best available model per-request based on rate limits and priority slots.
                        </p>
                        {purposeId && (() => {
                            const selected = purposes.find(p => p.id === purposeId);
                            if (!selected) return null;
                            const slots = [selected.priority_1, selected.priority_2, selected.priority_3, selected.priority_4, selected.priority_5];
                            return (
                                <div className="mt-2 flex flex-wrap gap-2">
                                    {slots.map((slot, i) => slot ? (
                                        <span key={i} className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-stone-100 dark:bg-stone-800 text-xs font-mono text-stone-700 dark:text-stone-300">
                                            P{i + 1}: {slot.provider}/{slot.model}
                                        </span>
                                    ) : null)}
                                </div>
                            );
                        })()}
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 flex items-center gap-1">
                            <FolderIcon className="w-4 h-4 text-gray-400" />
                            Folder (Optional)
                        </label>
                        <select
                            value={folderId}
                            onChange={(e) => setFolderId(e.target.value)}
                            className="input"
                        >
                            <option value="">Uncategorized</option>
                            {folders.map((f) => (
                                <option key={f.id} value={f.id}>
                                    {f.name}
                                </option>
                            ))}
                        </select>
                    </div>
                </div>

                {/* Integrations */}
                <div className="glass-card p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Send className="w-5 h-5 text-sky-500" /> Telegram Integration
                    </h2>
                    <div className="space-y-4">
                        <label className="flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all duration-200 bg-surface-1 dark:bg-surface-dark2 border-gray-200 dark:border-gray-700">
                            <input
                                type="checkbox"
                                checked={telegramEnabled}
                                onChange={(e) => setTelegramEnabled(e.target.checked)}
                                className="w-4 h-4 rounded border-gray-300 text-stone-600 focus:ring-stone-600"
                            />
                            <div>
                                <p className="text-sm font-medium text-gray-900 dark:text-white">Enable Telegram Integration</p>
                                <p className="text-xs text-gray-500">Allow users to interact with this agent via Telegram bot</p>
                            </div>
                        </label>

                        {telegramEnabled && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 animate-slide-up">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                        Primary Chat ID (Optional)
                                    </label>
                                    <input
                                        type="text"
                                        value={telegramChatId}
                                        onChange={(e) => setTelegramChatId(e.target.value)}
                                        className="input"
                                        placeholder="e.g. 123456789"
                                    />
                                    <p className="text-xs text-gray-500 mt-1">If set, the bot will notify this ID on agent startup.</p>
                                </div>
                                <div>
                                    <label className="flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all duration-200 bg-surface-1 dark:bg-surface-dark2 border-gray-200 dark:border-gray-700">
                                        <input
                                            type="checkbox"
                                            checked={onlineNotificationEnabled}
                                            onChange={(e) => setOnlineNotificationEnabled(e.target.checked)}
                                            className="w-4 h-4 rounded border-gray-300 text-stone-600 focus:ring-stone-600"
                                        />
                                        <div>
                                            <p className="text-sm font-medium text-gray-900 dark:text-white">Online Notifications</p>
                                            <p className="text-xs text-gray-500">Send a Telegram message when this agent starts</p>
                                        </div>
                                    </label>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Autonomy Controls */}
                <div className="glass-card p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-cyan-500" /> Autonomy Controls
                    </h2>
                    <p className="text-xs text-gray-500">Configure how independently this agent can operate.</p>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Auto-Approve Below
                            </label>
                            <select
                                value={autoApproveBelow}
                                onChange={(e) => setAutoApproveBelow(e.target.value)}
                                className="input"
                            >
                                <option value="">Disabled (all approvals require human)</option>
                                <option value="low">Low risk only</option>
                                <option value="medium">Low + Medium risk</option>
                            </select>
                            <p className="text-xs text-gray-500 mt-1">
                                Actions at or below this risk level proceed without human sign-off. High and critical always require approval.
                            </p>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Max Tool Calls / Run
                            </label>
                            <input
                                type="number"
                                min={0}
                                value={maxToolCallsPerRun}
                                onChange={(e) => setMaxToolCallsPerRun(parseInt(e.target.value) || 0)}
                                className="input"
                                placeholder="0 = unlimited"
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                Limit tool calls per single invocation. 0 = unlimited.
                            </p>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Daily Token Budget
                            </label>
                            <input
                                type="number"
                                min={0}
                                step={10000}
                                value={maxTokensPerDay}
                                onChange={(e) => setMaxTokensPerDay(parseInt(e.target.value) || 0)}
                                className="input"
                                placeholder="0 = unlimited"
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                Max tokens across all invocations today. 0 = unlimited.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Tools */}
                <ToolsSection
                    tools={tools}
                    enabledTools={enabledTools}
                    onToggle={toggleTool}
                />

                {/* Skills */}
                <SkillsSection agentId={agentId} />

                {/* Actions */}
                <div className="flex items-center justify-between">
                    <button type="button" onClick={handleDelete} className="btn-danger flex items-center gap-1.5">
                        <Trash2 className="w-4 h-4" /> Delete Agent
                    </button>
                    <div className="flex gap-3">
                        <button type="button" onClick={() => router.push("/agents")} className="btn-secondary">
                            Cancel
                        </button>
                        <button type="submit" disabled={saving} className="btn-primary flex items-center gap-2">
                            <Save className="w-4 h-4" />
                            {saving ? "Saving..." : "Save Changes"}
                        </button>
                    </div>
                </div>
            </form>
        </div>
    );
}
