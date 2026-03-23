import React from "react";
import {
    OllamaModel,
    OpenRouterModel,
    GeminiModel,
    PerplexityModel,
    GroqModel,
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
    // Loading states
    loadingOpenRouterModels: boolean;
    loadingGeminiModels: boolean;
    loadingPerplexityModels: boolean;
    loadingGroqModels: boolean;
    // Allow an empty "None" provider option (for secondary/fallback)
    allowNone?: boolean;
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
    loadingOpenRouterModels,
    loadingGeminiModels,
    loadingPerplexityModels,
    loadingGroqModels,
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
                        loadingOpenRouterModels ? (
                            <div className="input flex items-center gap-2 text-gray-400">
                                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                                </svg>
                                Loading models...
                            </div>
                        ) : openRouterModels.length > 0 ? (
                            <div className="space-y-1.5">
                                <input
                                    type="text"
                                    value={modelSearch}
                                    onChange={(e) => setModelSearch(e.target.value)}
                                    className="input text-sm"
                                    placeholder="Search models..."
                                />
                                <select
                                    size={6}
                                    value={model}
                                    onChange={(e) => onModelChange(e.target.value)}
                                    className="input h-auto py-1 text-sm font-mono"
                                >
                                    {openRouterModels
                                        .filter(m =>
                                            modelSearch === "" ||
                                            m.name.toLowerCase().includes(modelSearch.toLowerCase()) ||
                                            m.id.toLowerCase().includes(modelSearch.toLowerCase())
                                        )
                                        .map((m) => (
                                            <option key={m.id} value={m.id} title={m.description}>
                                                {m.name}
                                                {m.context_length ? ` (${(m.context_length / 1000).toFixed(0)}k ctx)` : ""}
                                            </option>
                                        ))
                                    }
                                </select>
                                <p className="text-xs text-gray-400">
                                    Selected: <code className="font-mono">{model}</code>
                                </p>
                            </div>
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
                        loadingGeminiModels ? (
                            <div className="input flex items-center gap-2 text-gray-400">
                                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                                </svg>
                                Loading Gemini models...
                            </div>
                        ) : geminiModels.length > 0 ? (
                            <div className="space-y-1.5">
                                <input
                                    type="text"
                                    value={modelSearch}
                                    onChange={(e) => setModelSearch(e.target.value)}
                                    className="input text-sm"
                                    placeholder="Search models..."
                                />
                                <select
                                    size={6}
                                    value={model}
                                    onChange={(e) => onModelChange(e.target.value)}
                                    className="input h-auto py-1 text-sm font-mono"
                                >
                                    {geminiModels
                                        .filter(m =>
                                            modelSearch === "" ||
                                            m.name.toLowerCase().includes(modelSearch.toLowerCase()) ||
                                            m.id.toLowerCase().includes(modelSearch.toLowerCase())
                                        )
                                        .map((m) => (
                                            <option key={m.id} value={m.id} title={m.description}>
                                                {m.name}
                                                {m.input_token_limit ? ` (${(m.input_token_limit / 1000).toFixed(0)}k ctx)` : ""}
                                            </option>
                                        ))
                                    }
                                </select>
                                <p className="text-xs text-gray-400">
                                    Selected: <code className="font-mono">{model}</code>
                                </p>
                            </div>
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
                        loadingPerplexityModels ? (
                            <div className="input flex items-center gap-2 text-gray-400">
                                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                                </svg>
                                Loading Perplexity models...
                            </div>
                        ) : perplexityModels.length > 0 ? (
                            <div className="space-y-1.5">
                                <input
                                    type="text"
                                    value={modelSearch}
                                    onChange={(e) => setModelSearch(e.target.value)}
                                    className="input text-sm"
                                    placeholder="Search models..."
                                />
                                <select
                                    size={4}
                                    value={model}
                                    onChange={(e) => onModelChange(e.target.value)}
                                    className="input h-auto py-1 text-sm font-mono"
                                >
                                    {perplexityModels
                                        .filter(m =>
                                            modelSearch === "" ||
                                            m.name.toLowerCase().includes(modelSearch.toLowerCase()) ||
                                            m.id.toLowerCase().includes(modelSearch.toLowerCase())
                                        )
                                        .map((m) => (
                                            <option key={m.id} value={m.id} title={m.description}>
                                                {m.name}
                                                {m.context_length ? ` (${(m.context_length / 1000).toFixed(0)}k ctx)` : ""}
                                            </option>
                                        ))
                                    }
                                </select>
                                <p className="text-xs text-gray-400">
                                    Selected: <code className="font-mono">{model}</code>
                                </p>
                            </div>
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
                        loadingGroqModels ? (
                            <div className="input flex items-center gap-2 text-gray-400">
                                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                                </svg>
                                Loading Groq models...
                            </div>
                        ) : groqModels.length > 0 ? (
                            <div className="space-y-1.5">
                                <input
                                    type="text"
                                    value={modelSearch}
                                    onChange={(e) => setModelSearch(e.target.value)}
                                    className="input text-sm"
                                    placeholder="Search models..."
                                />
                                <select
                                    size={4}
                                    value={model}
                                    onChange={(e) => onModelChange(e.target.value)}
                                    className="input h-auto py-1 text-sm font-mono"
                                >
                                    {groqModels
                                        .filter((m: GroqModel) =>
                                            modelSearch === "" ||
                                            m.name.toLowerCase().includes(modelSearch.toLowerCase()) ||
                                            m.id.toLowerCase().includes(modelSearch.toLowerCase())
                                        )
                                        .map((m: GroqModel) => (
                                            <option key={m.id} value={m.id} title={m.description}>
                                                {m.name}
                                                {m.context_length ? ` (${(m.context_length / 1000).toFixed(0)}k ctx)` : ""}
                                            </option>
                                        ))
                                    }
                                </select>
                                <p className="text-xs text-gray-400">
                                    Selected: <code className="font-mono">{model}</code>
                                </p>
                            </div>
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

                    ) : (
                        /* Other providers: plain text input */
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
