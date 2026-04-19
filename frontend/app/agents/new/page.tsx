"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
    Bot,
    Save,
    ArrowLeft,
    Cpu,
    Wrench,
    MessageSquare,
    Sparkles,
    AlertTriangle,
    Folder as FolderIcon,
    Shield,
    Send,
} from "lucide-react";
import { agentsApi, toolsApi, llmsApi, foldersApi, purposesApi, type ToolInfo, type OllamaModel, type OpenRouterModel, type GeminiModel, type PerplexityModel, type GroqModel, type Folder, type LLMPurpose } from "@/lib/api";
import { ProviderModelSelect } from "@/components/ProviderModelSelect";
import AgentAvatar, { AvatarPicker } from "@/components/AgentAvatar";

export default function NewAgentPage() {
    const router = useRouter();
    const [saving, setSaving] = useState(false);
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

    // Form state
    const [name, setName] = useState("");
    const [purposeId, setPurposeId] = useState<string>("");
    const [description, setDescription] = useState("");
    const [systemPrompt, setSystemPrompt] = useState(
        "You are a helpful AI assistant. Be concise and informative."
    );
    const [temperature, setTemperature] = useState(0.7);
    const [maxTokens, setMaxTokens] = useState(4096);
    const [llmProvider, setLlmProvider] = useState("ollama");
    const [llmModel, setLlmModel] = useState("llama3");
    const [secondaryProvider, setSecondaryProvider] = useState("");
    const [secondaryModel, setSecondaryModel] = useState("");
    const [fallbackProvider, setFallbackProvider] = useState("");
    const [fallbackModel, setFallbackModel] = useState("");
    const [enabledTools, setEnabledTools] = useState<string[]>([]);
    const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
    const [folderId, setFolderId] = useState<string>("");
    const [autoApproveBelow, setAutoApproveBelow] = useState("");
    const [maxToolCallsPerRun, setMaxToolCallsPerRun] = useState(0);
    const [maxTokensPerDay, setMaxTokensPerDay] = useState(0);
    const [telegramEnabled, setTelegramEnabled] = useState(false);
    const [telegramChatId, setTelegramChatId] = useState("");
    const [onlineNotificationEnabled, setOnlineNotificationEnabled] = useState(false);

    useEffect(() => {
        async function load() {
            try {
                const [toolList, models, folderList, purposeList] = await Promise.all([
                    toolsApi.list(),
                    llmsApi.ollamaModels().catch(() => []),
                    foldersApi.list().catch(() => []),
                    purposesApi.list().catch(() => []),
                ]);
                setTools(toolList);
                setOllamaModels(models);
                setFolders(folderList);
                setPurposes(purposeList);
                if (models.length > 0) {
                    setLlmModel(models[0].name);
                }
            } catch (err) {
                console.error("Failed to load form data:", err);
            }
        }
        load();
    }, []);

    // Fetch OpenRouter models when any provider is openrouter
    useEffect(() => {
        if (llmProvider !== "openrouter" && secondaryProvider !== "openrouter" && fallbackProvider !== "openrouter") return;
        if (openRouterModels.length > 0) return; // already loaded
        setLoadingOpenRouterModels(true);
        llmsApi.openRouterModels()
            .then((models) => {
                setOpenRouterModels(models);
            })
            .catch(() => { /* will show text input fallback */ })
            .finally(() => setLoadingOpenRouterModels(false));
    }, [llmProvider, secondaryProvider, fallbackProvider]);

    // Fetch Gemini models when any provider is google
    useEffect(() => {
        if (llmProvider !== "google" && secondaryProvider !== "google" && fallbackProvider !== "google") return;
        if (geminiModels.length > 0) return; // already loaded
        setLoadingGeminiModels(true);
        llmsApi.googleModels()
            .then((models) => {
                setGeminiModels(models);
            })
            .catch(() => { /* will show text input fallback */ })
            .finally(() => setLoadingGeminiModels(false));
    }, [llmProvider, secondaryProvider, fallbackProvider]);

    // Fetch Perplexity models when any provider is perplexity
    useEffect(() => {
        if (llmProvider !== "perplexity" && secondaryProvider !== "perplexity" && fallbackProvider !== "perplexity") return;
        if (perplexityModels.length > 0) return; // already loaded
        setLoadingPerplexityModels(true);
        llmsApi.perplexityModels()
            .then((models) => {
                setPerplexityModels(models);
            })
            .catch(() => { /* will show text input fallback */ })
            .finally(() => setLoadingPerplexityModels(false));
    }, [llmProvider, secondaryProvider, fallbackProvider]);

    // Fetch Groq models when any provider is groq
    useEffect(() => {
        if (llmProvider !== "groq" && secondaryProvider !== "groq" && fallbackProvider !== "groq") return;
        if (groqModels.length > 0) return; // already loaded
        setLoadingGroqModels(true);
        llmsApi.groqModels()
            .then((models) => {
                setGroqModels(models);
            })
            .catch(() => { /* will show text input fallback */ })
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

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (!name.trim()) return;

        setSaving(true);
        try {
            await agentsApi.create({
                name: name.trim(),
                description: description.trim() || null,
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
                auto_approve_below: autoApproveBelow || null,
                max_tool_calls_per_run: maxToolCallsPerRun,
                max_tokens_per_day: maxTokensPerDay,
                telegram_enabled: telegramEnabled,
                telegram_chat_id: telegramChatId || null,
                online_notification_enabled: onlineNotificationEnabled,
            });
            router.push("/agents");
        } catch (err) {
            console.error("Failed to create agent:", err);
            alert("Failed to create agent. Check the console for details.");
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center gap-4">
                <button onClick={() => router.back()} className="btn-icon">
                    <ArrowLeft className="w-5 h-5" />
                </button>
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
                        Create Agent
                    </h1>
                    <p className="text-gray-500 dark:text-gray-400 mt-1">
                        Configure a new AI agent with custom personality and tools
                    </p>
                </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
                {/* Identity */}
                <div className="glass-card p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Bot className="w-5 h-5 text-stone-600" />
                        Identity
                    </h2>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Avatar
                        </label>
                        <div className="flex items-center gap-4 mb-1">
                            <AgentAvatar name={name || "?"} avatarUrl={avatarUrl} size="lg" />
                            <p className="text-xs text-gray-500">Pick an avatar to give your agent personality</p>
                        </div>
                        <AvatarPicker selected={avatarUrl} onSelect={setAvatarUrl} />
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Agent Name *
                            </label>
                            <input
                                type="text"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                className="input"
                                placeholder="e.g., Research Assistant"
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
                                placeholder="What does this agent do?"
                            />
                        </div>
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

                {/* Personality */}
                <div className="glass-card p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-violet-500" />
                        Personality
                    </h2>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                            System Prompt
                        </label>
                        <textarea
                            value={systemPrompt}
                            onChange={(e) => setSystemPrompt(e.target.value)}
                            className="textarea h-32 font-mono text-sm"
                            placeholder="Define the agent's personality, role, and behavior..."
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
                                min={1}
                                max={128000}
                            />
                        </div>
                    </div>
                </div>

                {/* LLM Purpose */}
                <div className="glass-card p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Cpu className="w-5 h-5 text-emerald-500" />
                        LLM Purpose
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
                </div>

                {/* Tools */}
                <div className="glass-card p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Wrench className="w-5 h-5 text-amber-500" />
                        Tools
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Enable tools for this agent. Dangerous tools are marked with a warning.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {tools.map((tool) => (
                            <label
                                key={tool.id}
                                className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all duration-200 ${enabledTools.includes(tool.id)
                                    ? "bg-stone-100 dark:bg-stone-900/30 border-stone-400 dark:border-stone-600"
                                    : "bg-surface-1 dark:bg-surface-dark2 border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600"
                                    }`}
                            >
                                <input
                                    type="checkbox"
                                    checked={enabledTools.includes(tool.id)}
                                    onChange={() => toggleTool(tool.id)}
                                    className="sr-only"
                                />
                                <div
                                    className={`w-8 h-8 rounded-lg flex items-center justify-center ${enabledTools.includes(tool.id)
                                        ? "bg-stone-700 text-white"
                                        : "bg-surface-2 dark:bg-surface-dark3 text-gray-400"
                                        } transition-colors`}
                                >
                                    <Wrench className="w-4 h-4" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-1.5">
                                        <span className="text-sm font-medium text-gray-900 dark:text-white">
                                            {tool.name}
                                        </span>
                                        {tool.is_dangerous && (
                                            <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                                        )}
                                    </div>
                                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                                        {tool.description}
                                    </p>
                                </div>
                            </label>
                        ))}
                    </div>
                </div>

                {/* Autonomy Controls */}
                <div className="glass-card p-6 space-y-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Shield className="w-5 h-5 text-indigo-500" />
                        Autonomy Controls
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Configure how independently this agent can act. Leave defaults for fully supervised operation.
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Auto-Approve Threshold
                            </label>
                            <select
                                value={autoApproveBelow}
                                onChange={(e) => setAutoApproveBelow(e.target.value)}
                                className="input"
                            >
                                <option value="">None (all require approval)</option>
                                <option value="low">Low risk actions</option>
                                <option value="medium">Medium & below</option>
                            </select>
                            <p className="text-xs text-gray-400 mt-1">
                                Actions at or below this risk level skip human approval
                            </p>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Max Tool Calls / Run
                            </label>
                            <input
                                type="number"
                                value={maxToolCallsPerRun || ""}
                                onChange={(e) => setMaxToolCallsPerRun(parseInt(e.target.value) || 0)}
                                className="input"
                                min={0}
                                placeholder="0 = unlimited"
                            />
                            <p className="text-xs text-gray-400 mt-1">
                                Limit tool calls per single run (0 = no limit)
                            </p>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                                Daily Token Budget
                            </label>
                            <input
                                type="number"
                                value={maxTokensPerDay || ""}
                                onChange={(e) => setMaxTokensPerDay(parseInt(e.target.value) || 0)}
                                className="input"
                                min={0}
                                placeholder="0 = unlimited"
                            />
                            <p className="text-xs text-gray-400 mt-1">
                                Max tokens per day across all runs (0 = no limit)
                            </p>
                        </div>
                    </div>
                </div>

                {/* Telegram Integration */}
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

                {/* Submit */}
                <div className="flex items-center justify-end gap-3">
                    <button
                        type="button"
                        onClick={() => router.back()}
                        className="btn-secondary"
                    >
                        Cancel
                    </button>
                    <button
                        type="submit"
                        disabled={saving || !name.trim()}
                        className="btn-primary flex items-center gap-2"
                    >
                        <Save className="w-4 h-4" />
                        {saving ? "Creating..." : "Create Agent"}
                    </button>
                </div>
            </form>
        </div>
    );
}
