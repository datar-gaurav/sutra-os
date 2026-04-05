"use client";

import { useEffect, useRef, useState } from "react";
import {
    forgeApi,
    llmsApi,
    ForgeRequest,
    ForgeLogEntry,
    ForgePlan,
    ForgeStatus,
    ForgeTestResults,
    LLMProvider,
} from "@/lib/api";
import { wsClient } from "@/lib/ws";

// ─── Status helpers ──────────────────────────────────────────────────────────

const STATUS_LABEL: Record<ForgeStatus, string> = {
    queued: "Queued",
    planning: "Planning",
    awaiting_plan_approval: "Awaiting Plan Approval",
    coding: "Coding",
    testing: "Testing",
    pr_created: "PR Created",
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
};

const STATUS_COLOR: Record<ForgeStatus, string> = {
    queued: "bg-stone-100 text-stone-600",
    planning: "bg-blue-100 text-blue-700",
    awaiting_plan_approval: "bg-yellow-100 text-yellow-700",
    coding: "bg-orange-100 text-orange-700",
    testing: "bg-purple-100 text-purple-700",
    pr_created: "bg-green-100 text-green-700",
    completed: "bg-emerald-100 text-emerald-700",
    failed: "bg-red-100 text-red-700",
    cancelled: "bg-stone-100 text-stone-500",
};

const STATUS_STEPS: ForgeStatus[] = [
    "planning",
    "awaiting_plan_approval",
    "coding",
    "testing",
    "pr_created",
    "completed",
];

function StatusBadge({ status }: { status: ForgeStatus }) {
    return (
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_COLOR[status] || "bg-stone-100 text-stone-600"}`}>
            {STATUS_LABEL[status] || status}
        </span>
    );
}

function StatusTimeline({ status }: { status: ForgeStatus }) {
    const currentIdx = STATUS_STEPS.indexOf(status);
    return (
        <div className="flex items-center gap-0 my-4">
            {STATUS_STEPS.map((s, i) => {
                const done = i < currentIdx || status === "completed";
                const active = i === currentIdx && status !== "completed" && status !== "failed" && status !== "cancelled";
                const failed = status === "failed" && i === currentIdx;
                return (
                    <div key={s} className="flex items-center flex-1 min-w-0">
                        <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold border-2 transition-all
                            ${failed ? "bg-red-500 border-red-500 text-white" : done ? "bg-emerald-500 border-emerald-500 text-white" : active ? "bg-stone-700 border-stone-600 text-white animate-pulse" : "bg-white border-stone-200 text-stone-400"}`}
                            title={STATUS_LABEL[s]}
                        >
                            {done ? "✓" : i + 1}
                        </div>
                        {i < STATUS_STEPS.length - 1 && (
                            <div className={`h-0.5 flex-1 ${done ? "bg-emerald-400" : "bg-stone-200"}`} />
                        )}
                    </div>
                );
            })}
        </div>
    );
}

// ─── Common provider/model options ───────────────────────────────────────────

const COMMON_PROVIDERS = [
    { value: "groq", label: "Groq" },
    { value: "openai", label: "OpenAI" },
    { value: "anthropic", label: "Anthropic" },
    { value: "google", label: "Google" },
    { value: "openrouter", label: "OpenRouter" },
    { value: "ollama", label: "Ollama" },
    { value: "clod", label: "Clod.io" },
];

// Fallback models when API is unreachable
const FALLBACK_MODELS: Record<string, { value: string; label: string }[]> = {
    groq: [
        { value: "qwen/qwen3-32b", label: "Qwen 3 32B" },
        { value: "llama-3.3-70b-versatile", label: "Llama 3.3 70B" },
    ],
    openai: [
        { value: "gpt-4o", label: "GPT-4o" },
        { value: "gpt-4o-mini", label: "GPT-4o Mini" },
    ],
    anthropic: [
        { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
        { value: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
    ],
    google: [
        { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
        { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
    ],
};

// Map provider → API call to fetch live models
function fetchModelsForProvider(providerType: string): Promise<{ value: string; label: string }[]> | null {
    switch (providerType) {
        case "groq":
            return llmsApi.groqModels().then(models =>
                models
                    .filter(m => !m.id.startsWith("whisper"))  // skip audio models
                    .map(m => ({ value: m.id, label: m.name || m.id }))
            );
        case "google":
            return llmsApi.googleModels().then(models =>
                models.map(m => ({ value: m.id, label: m.name || m.id }))
            );
        case "openrouter":
            return llmsApi.openRouterModels().then(models =>
                models.slice(0, 30).map(m => ({ value: m.id, label: m.name || m.id }))
            );
        case "ollama":
            return llmsApi.ollamaModels().then(models =>
                models.map(m => ({ value: m.name, label: m.name }))
            );
        case "clod":
            return llmsApi.clodModels().then(models =>
                models.map(m => ({ value: m.id, label: m.name || m.id }))
            );
        default:
            return null;
    }
}

// ─── New Request Modal ────────────────────────────────────────────────────────

function NewForgeModal({ onClose, onCreated }: { onClose: () => void; onCreated: (r: ForgeRequest) => void }) {
    const [repo, setRepo] = useState("");
    const [description, setDescription] = useState("");
    const [provider, setProvider] = useState("groq");
    const [model, setModel] = useState("qwen/qwen3-32b");
    const [customModel, setCustomModel] = useState("");
    const [autoApprove, setAutoApprove] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [providers, setProviders] = useState<LLMProvider[]>([]);
    const [modelOptions, setModelOptions] = useState<{ value: string; label: string }[]>([]);
    const [modelsLoading, setModelsLoading] = useState(false);

    useEffect(() => {
        llmsApi.list().then(setProviders).catch(() => {});
    }, []);

    // Load models dynamically when provider changes
    useEffect(() => {
        let cancelled = false;
        const fetcher = fetchModelsForProvider(provider);
        if (fetcher) {
            setModelsLoading(true);
            fetcher
                .then(models => {
                    if (!cancelled) {
                        setModelOptions(models);
                        if (models.length > 0 && !models.find(m => m.value === model)) {
                            setModel(models[0].value);
                        }
                    }
                })
                .catch(() => {
                    if (!cancelled) {
                        setModelOptions(FALLBACK_MODELS[provider] || []);
                    }
                })
                .finally(() => { if (!cancelled) setModelsLoading(false); });
        } else {
            // Providers without a dynamic API (openai, anthropic) use fallback
            setModelOptions(FALLBACK_MODELS[provider] || []);
        }
        return () => { cancelled = true; };
    }, [provider]);

    // Merge configured providers with common options
    const providerOptions = [...COMMON_PROVIDERS];
    for (const p of providers) {
        if (!providerOptions.find(o => o.value === p.provider_type)) {
            providerOptions.push({ value: p.provider_type, label: p.name });
        }
    }

    function handleProviderChange(newProvider: string) {
        setProvider(newProvider);
        setModel("");
        setCustomModel("");
    }

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (!repo.trim() || !description.trim()) return;
        const finalModel = customModel.trim() || model;
        if (!finalModel) return;
        setLoading(true);
        setError("");
        try {
            const req = await forgeApi.create({
                repo_url: repo.trim(),
                description: description.trim(),
                llm_provider: provider,
                llm_model: finalModel,
                auto_approve_plan: autoApprove,
            });
            onCreated(req);
        } catch (err: any) {
            setError(err.message || "Failed to create forge request");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6 space-y-4">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-stone-900">New Forge Request</h2>
                    <button onClick={onClose} className="text-stone-400 hover:text-stone-600 text-xl">×</button>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">GitHub Repo</label>
                        <input
                            type="text"
                            placeholder="owner/repo"
                            value={repo}
                            onChange={e => setRepo(e.target.value)}
                            required
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-500"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">Feature Description</label>
                        <textarea
                            placeholder="Describe the feature or change you want to implement..."
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            required
                            rows={4}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-500 resize-none"
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">LLM Provider</label>
                            <select value={provider} onChange={e => handleProviderChange(e.target.value)}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-500">
                                {providerOptions.map(p => (
                                    <option key={p.value} value={p.value}>{p.label}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">Model</label>
                            {modelsLoading ? (
                                <div className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-400">
                                    Loading models...
                                </div>
                            ) : modelOptions.length > 0 ? (
                                <select value={model} onChange={e => setModel(e.target.value)}
                                    className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-500">
                                    {modelOptions.map(m => (
                                        <option key={m.value} value={m.value}>{m.label}</option>
                                    ))}
                                </select>
                            ) : (
                                <input
                                    type="text"
                                    placeholder="model-name"
                                    value={customModel}
                                    onChange={e => setCustomModel(e.target.value)}
                                    className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-500"
                                />
                            )}
                        </div>
                    </div>
                    {modelOptions.length > 0 && (
                        <div>
                            <label className="block text-xs text-stone-400 mb-1">Or enter a custom model name</label>
                            <input
                                type="text"
                                placeholder="custom-model-name (overrides dropdown)"
                                value={customModel}
                                onChange={e => setCustomModel(e.target.value)}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-500"
                            />
                        </div>
                    )}
                    <div className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            id="autoApprove"
                            checked={autoApprove}
                            onChange={e => setAutoApprove(e.target.checked)}
                            className="rounded border-stone-300"
                        />
                        <label htmlFor="autoApprove" className="text-sm text-stone-700">Auto-approve plan (skip review step)</label>
                    </div>
                    {error && <p className="text-red-500 text-sm">{error}</p>}
                    <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                        <p className="text-xs text-amber-700">
                            🕐 Request will be added to the queue and processed at <strong>7 PM PST</strong> daily. All queued requests run one-by-one in order.
                        </p>
                    </div>
                    <div className="flex gap-2 justify-end">
                        <button type="button" onClick={onClose}
                            className="px-4 py-2 text-sm border border-stone-200 rounded-lg hover:bg-stone-50">
                            Cancel
                        </button>
                        <button type="submit" disabled={loading}
                            className="px-4 py-2 text-sm bg-stone-700 text-white rounded-lg hover:bg-stone-800 disabled:opacity-50">
                            {loading ? "Adding to Queue..." : "Add to Queue"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ─── Plan view ────────────────────────────────────────────────────────────────

function PlanView({ req, onApprove, onFeedback, onCancel }: {
    req: ForgeRequest;
    onApprove: () => void;
    onFeedback: (text: string) => void;
    onCancel: () => void;
}) {
    const plan = req.plan as ForgePlan | null;
    const [feedbackMode, setFeedbackMode] = useState(false);
    const [feedbackText, setFeedbackText] = useState("");

    const actionColors: Record<string, string> = {
        create: "bg-green-100 text-green-700",
        modify: "bg-blue-100 text-blue-700",
        delete: "bg-red-100 text-red-700",
    };

    return (
        <div className="space-y-4">
            <div className="bg-stone-50 rounded-lg p-4">
                <p className="text-sm font-medium text-stone-700 mb-1">Summary</p>
                <p className="text-sm text-stone-600">{plan?.summary || "No summary available."}</p>
            </div>
            {plan?.steps && plan.steps.length > 0 && (
                <div>
                    <p className="text-sm font-medium text-stone-700 mb-2">Steps ({plan.steps.length})</p>
                    <div className="space-y-2">
                        {plan.steps.map((step, i) => (
                            <div key={i} className="flex gap-3 p-3 bg-white border border-stone-100 rounded-lg">
                                <span className={`text-xs font-bold px-1.5 py-0.5 rounded self-start flex-shrink-0 ${actionColors[step.action] || "bg-stone-100 text-stone-600"}`}>
                                    {step.action.toUpperCase()}
                                </span>
                                <div className="min-w-0">
                                    <p className="text-xs font-mono text-stone-700 truncate">{step.file}</p>
                                    <p className="text-xs text-stone-500 mt-0.5">{step.description}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
            {(req.plan_feedback?.length ?? 0) > 0 && (
                <div className="text-xs text-stone-400">{req.plan_feedback!.length} feedback round(s) applied</div>
            )}
            {feedbackMode ? (
                <div className="space-y-2">
                    <textarea
                        value={feedbackText}
                        onChange={e => setFeedbackText(e.target.value)}
                        placeholder="Describe the changes you want to the plan..."
                        rows={3}
                        className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-500 resize-none"
                    />
                    <div className="flex gap-2">
                        <button onClick={() => { onFeedback(feedbackText); setFeedbackMode(false); setFeedbackText(""); }}
                            disabled={!feedbackText.trim()}
                            className="px-3 py-1.5 text-sm bg-stone-700 text-white rounded-lg hover:bg-stone-800 disabled:opacity-50">
                            Submit Feedback
                        </button>
                        <button onClick={() => setFeedbackMode(false)}
                            className="px-3 py-1.5 text-sm border border-stone-200 rounded-lg hover:bg-stone-50">
                            Cancel
                        </button>
                    </div>
                </div>
            ) : (
                <div className="flex gap-2">
                    <button onClick={onApprove}
                        className="px-4 py-2 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700">
                        Approve & Code
                    </button>
                    <button onClick={() => setFeedbackMode(true)}
                        className="px-4 py-2 text-sm border border-stone-200 rounded-lg hover:bg-stone-50">
                        Suggest Changes
                    </button>
                    <button onClick={onCancel}
                        className="px-4 py-2 text-sm border border-red-200 text-red-600 rounded-lg hover:bg-red-50">
                        Cancel
                    </button>
                </div>
            )}
        </div>
    );
}

// ─── Test results view ────────────────────────────────────────────────────────

function TestResultsView({ results }: { results: ForgeTestResults }) {
    const [expanded, setExpanded] = useState(false);

    if (!results || results.framework === "none") {
        return (
            <div className="bg-stone-50 rounded-lg p-4 text-sm text-stone-500 italic">
                No test framework detected.
            </div>
        );
    }

    const passed = results.exit_code === 0;

    return (
        <div className={`rounded-lg border p-4 space-y-3 ${passed ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"}`}>
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <span className={`text-sm font-medium ${passed ? "text-emerald-700" : "text-amber-700"}`}>
                        {passed ? "Tests Passed" : "Tests Failed"}
                    </span>
                    <span className="text-xs text-stone-500 font-mono">{results.framework}</span>
                </div>
                <span className={`text-xs font-mono px-2 py-0.5 rounded ${passed ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                    exit {results.exit_code}
                </span>
            </div>
            <div className="flex gap-4 text-xs">
                {results.passed != null && (
                    <span className="text-emerald-600 font-medium">{results.passed} passed</span>
                )}
                {results.failed != null && results.failed > 0 && (
                    <span className="text-red-600 font-medium">{results.failed} failed</span>
                )}
                {results.skipped != null && results.skipped > 0 && (
                    <span className="text-stone-500">{results.skipped} skipped</span>
                )}
            </div>
            {(results.stdout || results.stderr) && (
                <div>
                    <button onClick={() => setExpanded(!expanded)}
                        className="text-xs text-stone-500 hover:text-stone-700 underline">
                        {expanded ? "Hide output" : "Show output"}
                    </button>
                    {expanded && (
                        <pre className="mt-2 bg-stone-900 text-stone-200 rounded-lg p-3 text-xs font-mono overflow-x-auto max-h-60 overflow-y-auto whitespace-pre-wrap">
                            {results.stdout || ""}{results.stderr ? `\n--- stderr ---\n${results.stderr}` : ""}
                        </pre>
                    )}
                </div>
            )}
        </div>
    );
}

// ─── Coding log view ─────────────────────────────────────────────────────────

function CodingLogView({ log }: { log: ForgeLogEntry[] }) {
    const bottomRef = useRef<HTMLDivElement>(null);
    const prevLen = useRef(0);

    useEffect(() => {
        if (log.length > prevLen.current) {
            bottomRef.current?.scrollIntoView({ behavior: "smooth" });
            prevLen.current = log.length;
        }
    }, [log.length]);

    return (
        <div className="bg-stone-900 rounded-lg p-4 font-mono text-xs text-stone-200 h-72 overflow-y-auto space-y-0.5">
            {log.length === 0 && (
                <p className="text-stone-500 italic">Waiting for coding to start...</p>
            )}
            {log.map((entry, i) => (
                <div key={i} className={`${entry.event === "error" ? "text-red-400" : entry.event === "done" ? "text-emerald-400" : "text-stone-200"}`}>
                    <span className="text-stone-500 mr-2">{new Date(entry.timestamp).toLocaleTimeString()}</span>
                    {entry.message}
                </div>
            ))}
            <div ref={bottomRef} />
        </div>
    );
}

// ─── PR section (read-only) ──────────────────────────────────────────────────

function PRSection({ req }: { req: ForgeRequest }) {
    return (
        <div className="space-y-4">
            <div className="bg-stone-50 rounded-lg p-4 flex items-start gap-4">
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-stone-700">Pull Request #{req.pr_number}</p>
                    {req.pr_url && (
                        <a href={req.pr_url} target="_blank" rel="noopener noreferrer"
                            className="text-sm text-stone-700 hover:underline break-all">
                            {req.pr_url}
                        </a>
                    )}
                    <p className="text-xs text-stone-400 mt-1">Branch: {req.branch_name}</p>
                </div>
                {req.pr_url && (
                    <a href={req.pr_url} target="_blank" rel="noopener noreferrer"
                        className="px-3 py-1.5 text-xs bg-stone-700 text-white rounded-lg hover:bg-stone-800 flex-shrink-0">
                        View on GitHub
                    </a>
                )}
            </div>
        </div>
    );
}

// ─── Request detail panel ─────────────────────────────────────────────────────

function ForgeDetail({ req: initialReq, onUpdate }: { req: ForgeRequest; onUpdate: (r: ForgeRequest) => void }) {
    const [req, setReq] = useState(initialReq);
    const [loading, setLoading] = useState(false);

    useEffect(() => { setReq(initialReq); }, [initialReq]);

    // Subscribe to WebSocket updates for this request
    useEffect(() => {
        wsClient.connect();
        const unsub = wsClient.on("forge_update", (data: any) => {
            if (data.forge_request_id === req.id) {
                forgeApi.get(req.id).then(updated => {
                    setReq(updated);
                    onUpdate(updated);
                }).catch(() => { });
            }
        });
        return unsub;
    }, [req.id, onUpdate]);

    // Polling fallback — refresh every 3s while request is active
    useEffect(() => {
        const isActive = !["completed", "failed", "cancelled"].includes(req.status);
        if (!isActive) return;
        const interval = setInterval(() => {
            forgeApi.get(req.id).then(updated => {
                setReq(updated);
                onUpdate(updated);
            }).catch(() => {});
        }, 3000);
        return () => clearInterval(interval);
    }, [req.id, req.status, onUpdate]);

    async function doAction(action: () => Promise<ForgeRequest>) {
        setLoading(true);
        try {
            const updated = await action();
            setReq(updated);
            onUpdate(updated);
        } catch (e: any) {
            alert(e.message || "Action failed");
        } finally {
            setLoading(false);
        }
    }

    const isPlanPhase = req.status === "awaiting_plan_approval" || req.status === "planning";
    const isCodingPhase = req.status === "coding";
    const isTestingPhase = req.status === "testing";
    const isTerminal = ["completed", "failed", "cancelled"].includes(req.status);
    const isActive = ["queued", "planning", "coding", "testing"].includes(req.status);
    const isQueued = req.status === "queued";

    return (
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                    <h2 className="text-lg font-semibold text-stone-900 truncate">{req.title}</h2>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                        <StatusBadge status={req.status} />
                        <span className="text-xs text-stone-400 font-mono">{req.repo_url}</span>
                        <span className="text-xs text-stone-400">
                            {req.llm_provider}/{req.llm_model}
                        </span>
                    </div>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                    {(req.status === "queued" || req.status === "failed") && (
                        <button
                            onClick={() => doAction(() => forgeApi.runNow(req.id))}
                            disabled={loading}
                            className="text-xs font-medium text-white bg-stone-800 hover:bg-stone-700 rounded px-2 py-1">
                            Run Now
                        </button>
                    )}
                    {(req.status === "failed" || req.status === "planning" || req.status === "queued") && (
                        <button
                            onClick={() => doAction(() => forgeApi.retry(req.id))}
                            disabled={loading}
                            className="text-xs text-blue-600 hover:text-blue-700 border border-blue-200 rounded px-2 py-1">
                            {req.status === "queued" ? "Re-queue" : "Retry"}
                        </button>
                    )}
                    {!isTerminal && (
                        <button
                            onClick={() => doAction(() => forgeApi.cancel(req.id))}
                            disabled={loading}
                            className="text-xs text-stone-400 hover:text-red-500 border border-stone-200 rounded px-2 py-1">
                            Cancel
                        </button>
                    )}
                </div>
            </div>

            {/* Queue position banner */}
            {isQueued && (
                <div className="bg-stone-50 border border-stone-200 rounded-lg p-4 flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-stone-200 flex items-center justify-center text-sm font-bold text-stone-600 flex-shrink-0">
                        {req.queue_position ?? "—"}
                    </div>
                    <div className="flex-1">
                        <p className="text-sm font-medium text-stone-700">
                            {req.queue_position === 1 ? "Next up in queue" : `Position ${req.queue_position ?? "—"} in queue`}
                        </p>
                        <p className="text-xs text-stone-400 mt-0.5">
                            Scheduled to run at <strong>7 PM PST</strong> daily · requests run one-by-one
                        </p>
                    </div>
                    <button
                        onClick={() => doAction(() => forgeApi.runNow(req.id))}
                        disabled={loading}
                        className="text-xs font-medium text-white bg-stone-800 hover:bg-stone-700 rounded px-3 py-1.5 flex-shrink-0">
                        Run Now
                    </button>
                </div>
            )}

            {/* Timeline — only show once work has started */}
            {req.status !== "queued" && <StatusTimeline status={req.status} />}

            {/* Description */}
            <div>
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-wide mb-1">Request</p>
                <p className="text-sm text-stone-600">{req.description}</p>
            </div>

            {/* Spinner for active states */}
            {(isActive && !isQueued) && (
                <div className="flex items-center gap-2 text-sm text-stone-500">
                    <div className="w-4 h-4 border-2 border-stone-500 border-t-transparent rounded-full animate-spin" />
                    {req.status === "planning" ? "Generating plan..." :
                     req.status === "coding" ? "Coding in progress..." :
                     "Running tests..."}
                </div>
            )}

            {/* Plan section */}
            {req.plan && (
                <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-wide mb-2">Implementation Plan</p>
                    {isPlanPhase ? (
                        <PlanView
                            req={req}
                            onApprove={() => doAction(() => forgeApi.approvePlan(req.id))}
                            onFeedback={(text) => doAction(() => forgeApi.requestChanges(req.id, text))}
                            onCancel={() => doAction(() => forgeApi.cancel(req.id))}
                        />
                    ) : (
                        <div className="bg-stone-50 rounded-lg p-4">
                            <p className="text-sm text-stone-500 italic">{req.plan.summary}</p>
                            <p className="text-xs text-stone-400 mt-1">{req.plan.steps?.length ?? 0} step(s)</p>
                        </div>
                    )}
                </div>
            )}

            {/* Coding log */}
            {(isCodingPhase || isTestingPhase || (req.coding_log && req.coding_log.length > 0)) && (
                <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-wide mb-2">Coding Log</p>
                    <CodingLogView log={req.coding_log || []} />
                </div>
            )}

            {/* Test results */}
            {req.test_results && (
                <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-wide mb-2">Test Results</p>
                    <TestResultsView results={req.test_results} />
                </div>
            )}

            {/* PR section */}
            {req.pr_url && (
                <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-wide mb-2">Pull Request</p>
                    <PRSection req={req} />
                </div>
            )}

            {/* Error */}
            {req.error_log && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                    <p className="text-xs font-semibold text-red-600 mb-1">Error</p>
                    <p className="text-xs font-mono text-red-700 whitespace-pre-wrap">{req.error_log}</p>
                </div>
            )}

            {/* Completed */}
            {req.status === "completed" && (
                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
                    <p className="text-sm font-medium text-emerald-700">Forge request completed!</p>
                    <p className="text-xs text-emerald-600 mt-1">Review and merge the PR on GitHub.</p>
                </div>
            )}
        </div>
    );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function ForgePage() {
    const [requests, setRequests] = useState<ForgeRequest[]>([]);
    const [selected, setSelected] = useState<ForgeRequest | null>(null);
    const [showModal, setShowModal] = useState(false);
    const [loading, setLoading] = useState(true);

    async function loadRequests() {
        try {
            const data = await forgeApi.list();
            setRequests(data);
            // Keep selected in sync
            if (selected) {
                const updated = data.find(r => r.id === selected.id);
                if (updated) setSelected(updated);
            }
        } catch { }
    }

    useEffect(() => {
        wsClient.connect();
        loadRequests().finally(() => setLoading(false));
        const unsub = wsClient.on("forge_update", () => loadRequests());
        return unsub;
    }, []);

    function handleUpdate(updated: ForgeRequest) {
        setRequests(prev => prev.map(r => r.id === updated.id ? updated : r));
    }

    function handleCreated(req: ForgeRequest) {
        setRequests(prev => [req, ...prev]);
        setSelected(req);
        setShowModal(false);
    }

    const timeAgo = (dateStr: string) => {
        const diff = Date.now() - new Date(dateStr).getTime();
        const m = Math.floor(diff / 60000);
        if (m < 1) return "just now";
        if (m < 60) return `${m}m ago`;
        const h = Math.floor(m / 60);
        if (h < 24) return `${h}h ago`;
        return `${Math.floor(h / 24)}d ago`;
    };

    return (
        <div className="flex h-full">
            {/* Left: Request list */}
            <div className="w-80 flex-shrink-0 border-r border-stone-200 flex flex-col bg-[#F8F9FA]">
                <div className="p-4 border-b border-stone-200 flex items-center justify-between">
                    <div>
                        <h1 className="text-base font-semibold text-stone-900">Forge</h1>
                        <p className="text-xs text-stone-400">Autonomous coding pipeline</p>
                    </div>
                    <button
                        onClick={() => setShowModal(true)}
                        className="px-3 py-1.5 text-xs bg-stone-700 text-white rounded-lg hover:bg-stone-800">
                        + New
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto">
                    {loading && (
                        <div className="p-4 text-sm text-stone-400 text-center">Loading...</div>
                    )}
                    {!loading && requests.length === 0 && (
                        <div className="p-6 text-center space-y-3">
                            <div className="text-3xl">⚒️</div>
                            <p className="text-sm text-stone-500">No forge requests yet.</p>
                            <button onClick={() => setShowModal(true)}
                                className="text-sm text-stone-700 hover:underline">
                                Start your first one
                            </button>
                        </div>
                    )}
                    {requests.map(req => (
                        <div
                            key={req.id}
                            onClick={() => setSelected(req)}
                            className={`w-full text-left p-4 border-b border-stone-100 hover:bg-white transition-colors cursor-pointer group ${selected?.id === req.id ? "bg-white border-l-2 border-l-stone-600" : ""}`}
                        >
                            <div className="flex items-start justify-between gap-2 mb-1">
                                <p className="text-sm font-medium text-stone-800 truncate flex-1">{req.title}</p>
                                <div className="flex items-center gap-1 flex-shrink-0">
                                    <StatusBadge status={req.status} />
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            if (!confirm("Delete this forge request?")) return;
                                            forgeApi.delete(req.id).then(() => {
                                                setRequests(prev => prev.filter(r => r.id !== req.id));
                                                if (selected?.id === req.id) setSelected(null);
                                            }).catch(() => {});
                                        }}
                                        className="opacity-0 group-hover:opacity-100 text-stone-300 hover:text-red-500 transition-opacity ml-1"
                                        title="Delete request"
                                    >
                                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                                    </button>
                                </div>
                            </div>
                            <p className="text-xs text-stone-400 truncate">{req.repo_url}</p>
                            <p className="text-xs text-stone-300 mt-1">{timeAgo(req.created_at)}</p>
                        </div>
                    ))}
                </div>
            </div>

            {/* Right: Detail panel */}
            <div className="flex-1 flex flex-col min-w-0">
                {selected ? (
                    <ForgeDetail key={selected.id} req={selected} onUpdate={handleUpdate} />
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-center p-12 space-y-4">
                        <div className="text-5xl">⚒️</div>
                        <h2 className="text-xl font-semibold text-stone-700">Sutra Forge</h2>
                        <p className="text-sm text-stone-500 max-w-sm">
                            Describe a feature in natural language. Forge will clone your repo,
                            plan the implementation with any LLM, code it, run tests, and open a pull request — all autonomously.
                        </p>
                        <button onClick={() => setShowModal(true)}
                            className="px-5 py-2.5 bg-stone-700 text-white rounded-lg hover:bg-stone-800 text-sm font-medium">
                            Start a Forge Request
                        </button>
                    </div>
                )}
            </div>

            {showModal && (
                <NewForgeModal onClose={() => setShowModal(false)} onCreated={handleCreated} />
            )}
        </div>
    );
}
