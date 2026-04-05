import React from "react";
import {
    OllamaModel,
    OpenRouterModel,
    GeminiModel,
    PerplexityModel,
    GroqModel,
    NvidiaModel,
} from "@/lib/api";

interface ProviderModelSelectProps {
    label: string;
    provider: string;
    model: string;
    onProviderChange: (provider: string) => void;
    onModelChange: (model: string) => void;
    // Model lists
    ollamaModels: OllamaModel[];
    openRouterModels: OpenRouterModel[];
    geminiModels: GeminiModel[];
    perplexityModels: PerplexityModel[];
    groqModels: GroqModel[];
    nvidiaModels?: NvidiaModel[];
    // Loading states
    loadingOpenRouterModels: boolean;
    loadingGeminiModels: boolean;
    loadingPerplexityModels: boolean;
    loadingGroqModels: boolean;
    loadingNvidiaModels?: boolean;
    // Allow an empty "None" provider option (for secondary/fallback)
    allowNone?: boolean;
}

/* Reusable loading spinner */
function Spinner() {
    return (
        <div className="input flex items-center gap-2 text-gray-400">
            <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            Loading models...
        </div>
    );
}

/* Reusable searchable model list */
function SearchableModelSelect({
    models,
    model,
    onModelChange,
    modelSearch,
    setModelSearch,
    size = 6,
}: {
    models: { id: string; name: string; context_length?: number; description?: string }[];
    model: string;
    onModelChange: (v: string) => void;
    modelSearch: string;
    setModelSearch: (v: string) => void;
    size?: number;
}) {
    const filtered = models.filter(
        (m) =>
            modelSearch === "" ||
            m.name.toLowerCase().includes(modelSearch.toLowerCase()) ||
            m.id.toLowerCase().includes(modelSearch.toLowerCase())
    );
    return (
        <div className="space-y-1.5">
            <input
                type="text"
                value={modelSearch}
                onChange={(e) => setModelSearch(e.target.value)}
                className="input text-sm"
                placeholder="Search models..."
            />
            <select
                size={size}
                value={model}
                onChange={(e) => onModelChange(e.target.value)}
                className="input h-auto py-1 text-sm font-mono"
            >
                {filtered.map((m) => (
                    <option key={m.id} value={m.id} title={m.description}>
                        {m.name}
                        {m.context_length ? ` (${(m.context_length / 1000).toFixed(0)}k ctx)` : ""}
                    </option>
                ))}
            </select>
            <p className="text-xs text-gray-400">
                Selected: <code className="font-mono">{model}</code>
            </p>
        </div>
    );
}

export function ProviderModelSelect({
    label,
    provider,
    model,
    onProviderChange,
    onModelChange,
    ollamaModels,
    openRouterModels,
    geminiModels,
    perplexityModels,
    groqModels,
    nvidiaModels = [],
    loadingOpenRouterModels,
    loadingGeminiModels,
    loadingPerplexityModels,
    loadingGroqModels,
    loadingNvidiaModels = false,
    allowNone = false,
}: ProviderModelSelectProps) {
    const [modelSearch, setModelSearch] = React.useState("");

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                    {label} Provider
                </label>
                <select
                    value={provider}
                    onChange={(e) => onProviderChange(e.target.value)}
                    className="input"
                >
                    {allowNone && <option value="">None</option>}
                    <option value="ollama">Ollama (Local)</option>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="google">Google Gemini</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="perplexity">Perplexity</option>
                    <option value="groq">Groq</option>
                    <option value="nvidia_nim">NVIDIA NIM</option>
                    <option value="openai_compatible">OpenAI Compatible</option>
                </select>
            </div>

            {(provider || !allowNone) && (
                <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                        {label} Model
                    </label>

                    {/* Ollama: dropdown of locally installed models */}
                    {provider === "ollama" && ollamaModels.length > 0 ? (
                        <select
                            value={model}
                            onChange={(e) => onModelChange(e.target.value)}
                            className="input"
                        >
                            {ollamaModels.map((m) => (
                                <option key={m.name} value={m.name}>
                                    {m.name} ({m.size})
                                </option>
                            ))}
                        </select>

                    ) : provider === "openrouter" ? (
                        /* OpenRouter: searchable dropdown or loading state */
                        loadingOpenRouterModels ? <Spinner /> : openRouterModels.length > 0 ? (
                            <SearchableModelSelect
                                models={openRouterModels}
                                model={model}
                                onModelChange={onModelChange}
                                modelSearch={modelSearch}
                                setModelSearch={setModelSearch}
                            />
                        ) : (
                            <div className="space-y-1">
                                <input
                                    type="text"
                                    value={model}
                                    onChange={(e) => onModelChange(e.target.value)}
                                    className="input"
                                    placeholder="openai/gpt-4o"
                                />
                                <p className="text-xs text-amber-500">
                                    ⚠ Add your OpenRouter API key in Settings to browse models.
                                </p>
                            </div>
                        )

                    ) : provider === "google" ? (
                        /* Google Gemini: searchable dropdown or loading state */
                        loadingGeminiModels ? <Spinner /> : geminiModels.length > 0 ? (
                            <SearchableModelSelect
                                models={geminiModels.map((m) => ({
                                    id: m.id,
                                    name: m.name,
                                    context_length: m.input_token_limit,
                                    description: m.description,
                                }))}
                                model={model}
                                onModelChange={onModelChange}
                                modelSearch={modelSearch}
                                setModelSearch={setModelSearch}
                            />
                        ) : (
                            <div className="space-y-1">
                                <input
                                    type="text"
                                    value={model}
                                    onChange={(e) => onModelChange(e.target.value)}
                                    className="input"
                                    placeholder="gemini-1.5-pro"
                                />
                                <p className="text-xs text-amber-500">
                                    ⚠ Add your Google API key in Settings to browse models.
                                </p>
                            </div>
                        )

                    ) : provider === "perplexity" ? (
                        /* Perplexity: searchable dropdown or loading state */
                        loadingPerplexityModels ? <Spinner /> : perplexityModels.length > 0 ? (
                            <SearchableModelSelect
                                models={perplexityModels}
                                model={model}
                                onModelChange={onModelChange}
                                modelSearch={modelSearch}
                                setModelSearch={setModelSearch}
                                size={4}
                            />
                        ) : (
                            <div className="space-y-1">
                                <input
                                    type="text"
                                    value={model}
                                    onChange={(e) => onModelChange(e.target.value)}
                                    className="input"
                                    placeholder="sonar-pro"
                                />
                                <p className="text-xs text-amber-500">
                                    ⚠ Add your Perplexity API key in Settings to browse models.
                                </p>
                            </div>
                        )

                    ) : provider === "groq" ? (
                        /* Groq: searchable dropdown or loading state */
                        loadingGroqModels ? <Spinner /> : groqModels.length > 0 ? (
                            <SearchableModelSelect
                                models={groqModels}
                                model={model}
                                onModelChange={onModelChange}
                                modelSearch={modelSearch}
                                setModelSearch={setModelSearch}
                                size={4}
                            />
                        ) : (
                            <div className="space-y-1">
                                <input
                                    type="text"
                                    value={model}
                                    onChange={(e) => onModelChange(e.target.value)}
                                    className="input"
                                    placeholder="llama3-8b-8192"
                                />
                                <p className="text-xs text-amber-500">
                                    ⚠ Add your Groq API key in Settings to browse models.
                                </p>
                            </div>
                        )

                    ) : provider === "nvidia_nim" ? (
                        /* NVIDIA NIM: searchable dropdown or loading state */
                        loadingNvidiaModels ? <Spinner /> : nvidiaModels.length > 0 ? (
                            <SearchableModelSelect
                                models={nvidiaModels}
                                model={model}
                                onModelChange={onModelChange}
                                modelSearch={modelSearch}
                                setModelSearch={setModelSearch}
                                size={4}
                            />
                        ) : (
                            <div className="space-y-1">
                                <input
                                    type="text"
                                    value={model}
                                    onChange={(e) => onModelChange(e.target.value)}
                                    className="input"
                                    placeholder="meta/llama-3.1-8b-instruct"
                                />
                                <p className="text-xs text-amber-500">
                                    ⚠ Add your NVIDIA NIM API key in Settings to browse models.
                                </p>
                            </div>
                        )

                    ) : provider === "openai_compatible" ? (
                        /* Generic OpenAI-compatible: always free-text */
                        <div className="space-y-1">
                            <input
                                type="text"
                                value={model}
                                onChange={(e) => onModelChange(e.target.value)}
                                className="input"
                                placeholder="model-name"
                            />
                            <p className="text-xs text-gray-400">
                                Configure base URL via the API Key Providers panel in Settings.
                            </p>
                        </div>

                    ) : (
                        /* Other providers (openai, anthropic, etc.): plain text input */
                        <input
                            type="text"
                            value={model}
                            onChange={(e) => onModelChange(e.target.value)}
                            className="input"
                            placeholder={
                                provider === "openai" ? "gpt-4o"
                                    : provider === "anthropic" ? "claude-3-5-sonnet-20241022"
                                        : "llama3"
                            }
                        />
                    )}
                </div>
            )}
        </div>
    );
}


