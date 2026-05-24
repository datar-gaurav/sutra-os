/** API client for communicating with the Sutra backend. */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ─── Types ──────────────────────────────────────────────────────────────────

export interface Agent {
    id: string;
    name: string;
    description: string | null;
    avatar_url: string | null;
    system_prompt: string;
    temperature: number;
    max_tokens: number;
    purpose_id: string | null;
    llm_provider: string;
    llm_model: string;
    secondary_provider: string | null;
    secondary_model: string | null;
    fallback_provider: string | null;
    fallback_model: string | null;
    enabled_tools: string[];
    is_active: boolean;
    status: "stopped" | "starting" | "running" | "error";
    folder_id: string | null;
    slack_channel_id: string | null;
    telegram_chat_id: string | null;
    telegram_enabled: boolean;
    online_notification_enabled: boolean;
    // Phase 1.4 org fields
    role_id: string | null;
    team_id: string | null;
    reports_to_agent_id: string | null;
    skills: string[];
    // Autonomy fields
    auto_approve_below: string | null;
    max_tool_calls_per_run: number;
    max_tokens_per_day: number;
    // Voice
    voice_enabled: boolean;
    voice_id: string | null;
    voice_provider_tts: string | null;
    voice_provider_stt: string | null;
    voice_speed: number;
    telegram_voice_enabled: boolean;
    web_voice_enabled: boolean;
    created_at: string;
    updated_at: string;
}

// ─── Voice ───────────────────────────────────────────────────────────────────

export interface VoiceOption {
    id: string;
    name: string;
    lang: string;
}

export interface VoiceCatalog {
    providers: { stt: string[]; tts: string[] };
    defaults: {
        tts_provider: string;
        stt_provider: string;
        voice_id: string;
    };
    voices: Record<string, VoiceOption[]>;
}

// ─── Rate Limit Types ────────────────────────────────────────────────────────

export interface ModelRateLimit {
    id: string;
    provider: string;
    model: string;
    label: string | null;
    requests_per_minute: number | null;
    requests_per_day: number | null;
    tokens_per_minute: number | null;
    tokens_per_day: number | null;
    refresh_interval_hours: number;
    created_at: string;
    updated_at: string;
}

export interface PrioritySlot {
    provider: string;
    model: string;
}

export interface LLMPurpose {
    id: string;
    name: string;
    description: string | null;
    is_default: boolean;
    priority_1: PrioritySlot | null;
    priority_2: PrioritySlot | null;
    priority_3: PrioritySlot | null;
    priority_4: PrioritySlot | null;
    priority_5: PrioritySlot | null;
    created_at: string;
    updated_at: string;
}

export interface RateLimitUsageEntry {
    id: string;
    provider: string;
    model: string;
    label: string | null;
    limits: { rpm: number | null; rpd: number | null; tpm: number | null; tpd: number | null };
    current: { rpm: number; rpd: number; tpm: number; tpd: number };
}

export interface PurposeSlotStatus {
    priority: number;
    provider: string | null;
    model: string | null;
    has_capacity: boolean;
    reason: string;
    usage: { rpm: number; rpd: number; tpm: number; tpd: number } | null;
}

export interface PurposeStatusResponse {
    purpose_id: string;
    purpose_name: string;
    overall_status: "green" | "yellow" | "red";
    active_priority: number | null;
    slots: PurposeSlotStatus[];
}

export interface Folder {
    id: string;
    name: string;
    created_at: string;
    updated_at: string;
}

export interface LLMProvider {
    id: string;
    name: string;
    provider_type: string;
    base_url: string | null;
    is_enabled: boolean;
    is_default: boolean;
    supports_tool_calling: boolean;
    has_api_key: boolean;
    created_at: string;
    updated_at: string;
}

export interface ToolInfo {
    id: string;
    name: string;
    description: string;
    category: string;
    is_dangerous: boolean;
}

export interface OllamaModel {
    name: string;
    size: string;
    modified_at: string;
    details: Record<string, any> | null;
}

export interface PerplexityModel {
    id: string;
    name: string;
    description: string;
    context_length: number;
}

export interface GroqModel {
    id: string;
    name: string;
    context_length?: number;
    description?: string;
}

export interface ClodModel {
    id: string;
    name: string;
    context_length?: number;
    description?: string;
}

export interface OpenRouterModel {
    id: string;
    name: string;
    context_length: number;
    description: string;
    pricing: { prompt: string; completion: string };
}

export interface GeminiModel {
    id: string;
    name: string;
    description: string;
    input_token_limit: number;
    output_token_limit: number;
}

export interface NvidiaModel {
    id: string;
    name: string;
    context_length?: number;
    description?: string;
}

export interface OpenRouterQuota {
    limit: number | null;
    limit_remaining: number | null;
    usage: number | null;
    usage_daily: number | null;
    error?: string;
}

export interface ModelUsage {
    provider: string;
    model: string;
    request_count: number;
}

export interface ModelLimit {
    provider: string;
    model: string;
    daily_limit: number;
}

export interface MonitorUsageOverview {
    usages: ModelUsage[];
    limits: ModelLimit[];
}

export interface AgentDailyUsage {
    agent_id: string;
    date: string;
    request_count: number;
}

export interface ChatMessage {
    id: string;
    role: "user" | "assistant" | "system" | "tool";
    content: string;
    tool_calls: any | null;
    created_at: string;
}

export interface Conversation {
    id: string;
    title: string;
    source: string;
    created_at: string;
    updated_at: string;
}

// ─── Helper ─────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
    const token = typeof window !== "undefined" ? localStorage.getItem("sutra_access_token") : null;

    // Destructure headers out of options so that spreading `...rest` below does
    // NOT overwrite the already-merged headers object (which includes the auth token).
    const { headers: optionHeaders, ...rest } = options ?? {};

    // Don't set Content-Type for FormData — the browser sets it with the correct boundary automatically.
    const isFormData = options?.body instanceof FormData;

    const res = await fetch(`${API_BASE}${path}`, {
        headers: {
            ...(isFormData ? {} : { "Content-Type": "application/json" }),
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...optionHeaders,
        },
        ...rest,
    });

    if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth/")) {
        localStorage.removeItem("sutra_access_token");
        localStorage.removeItem("sutra_refresh_token");
        localStorage.removeItem("sutra_user");
        window.location.href = "/login";
        throw new Error("Unauthorized");
    }

    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: res.statusText }));
        const detail = error.detail;
        // Preserve structured error details (e.g. validation_errors from workflow DAG check)
        if (detail && typeof detail === "object") {
            const err: any = new Error(`API error: ${res.status}`);
            err.detail = detail;
            throw err;
        }
        throw new Error(detail || `API error: ${res.status}`);
    }

    if (res.status === 204) return undefined as T;
    return res.json();
}

// ─── Agents ─────────────────────────────────────────────────────────────────

export const agentsApi = {
    list: () => apiFetch<Agent[]>("/api/agents/"),
    get: (id: string) => apiFetch<Agent>(`/api/agents/${id}`),
    create: (data: Partial<Agent>) =>
        apiFetch<Agent>("/api/agents/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Agent>) =>
        apiFetch<Agent>(`/api/agents/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
        apiFetch<void>(`/api/agents/${id}`, { method: "DELETE" }),
    start: (id: string) =>
        apiFetch<{ status: string }>(`/api/agents/${id}/start`, { method: "POST" }),
    stop: (id: string) =>
        apiFetch<{ status: string }>(`/api/agents/${id}/stop`, { method: "POST" }),
    restart: (id: string) =>
        apiFetch<{ status: string }>(`/api/agents/${id}/restart`, { method: "POST" }),
    clone: (id: string) =>
        apiFetch<Agent>(`/api/agents/${id}/clone`, { method: "POST" }),
};

// ─── Composed Agents ────────────────────────────────────────────────────────

export interface GuardrailAttachment {
    id: string;
    type: string;
    config: Record<string, any>;
    on_reject?: "abort" | "warn";
    // Provenance — set when loaded from the SavedGuardrail library.
    source_id?: string | null;
    source_version?: number | null;
}

export interface SavedGuardrail {
    id: string;
    name: string;
    description: string | null;
    type: string;
    config: Record<string, any>;
    version: number;
}

export interface GuardrailEvent {
    id: string;
    composed_agent_id: string;
    run_id: string;
    guardrail_id: string;
    stage: "input" | "output";
    action: "allow" | "mutate" | "reject" | "warn";
    passed: boolean;
    reason: string | null;
    score: number | null;
    latency_ms: number;
    created_at: string | null;
}

export interface ComposedAgentNode {
    id: string;
    kind: "input" | "llm" | "output";
    ui?: { position?: { x: number; y: number }; label?: string };
    guardrails?: GuardrailAttachment[];
    system_prompt?: string;
    llm_provider?: string | null;
    llm_model?: string | null;
    temperature?: number;
    max_tokens?: number;
    output_schema?: Record<string, any> | null;
    pre_guardrails?: GuardrailAttachment[];
    post_guardrails?: GuardrailAttachment[];
}

export interface ComposedAgentEdge {
    source: string;
    target: string;
    condition?: string | null;
}

export interface ComposedAgentGraphSpec {
    nodes: ComposedAgentNode[];
    edges: ComposedAgentEdge[];
    entry: string;
}

export interface ComposedAgent {
    id: string;
    name: string;
    description: string | null;
    graph_spec: ComposedAgentGraphSpec;
    state_schema: Record<string, any>;
    version: number;
    published_version: number | null;
    is_active: boolean;
    status: string;
}

export interface GuardrailDescriptor {
    id: string;
    name: string;
    description: string;
    kind: "input" | "output" | "both";
    config_schema: Record<string, any>;
}

export interface GuardrailRunResult {
    guardrail_id: string;
    stage: "input" | "output";
    passed: boolean;
    action: "allow" | "mutate" | "reject" | "warn";
    reason: string;
    score: number | null;
    latency_ms: number;
    mutated_text: string | null;
}

export interface ComposedRunResponse {
    run_id: string;
    output: string;
    rejected: boolean;
    rejection_reason: string | null;
    guardrail_results: GuardrailRunResult[];
    scratchpad: Record<string, any>;
}

export const composedAgentsApi = {
    list: () => apiFetch<ComposedAgent[]>("/api/composed-agents/"),
    get: (id: string) => apiFetch<ComposedAgent>(`/api/composed-agents/${id}`),
    create: (data: { name: string; description?: string; graph_spec?: ComposedAgentGraphSpec }) =>
        apiFetch<ComposedAgent>("/api/composed-agents/", {
            method: "POST",
            body: JSON.stringify(data),
        }),
    update: (id: string, data: Partial<ComposedAgent>) =>
        apiFetch<ComposedAgent>(`/api/composed-agents/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        apiFetch<void>(`/api/composed-agents/${id}`, { method: "DELETE" }),
    publish: (id: string) =>
        apiFetch<ComposedAgent>(`/api/composed-agents/${id}/publish`, { method: "POST" }),
    run: (id: string, input: string, usePublished = false) =>
        apiFetch<ComposedRunResponse>(`/api/composed-agents/${id}/run`, {
            method: "POST",
            body: JSON.stringify({ input, use_published: usePublished }),
        }),
    listGuardrails: () => apiFetch<GuardrailDescriptor[]>("/api/composed-agents/guardrails"),
    testGuardrail: (data: { type: string; config: Record<string, any>; input: string; stage?: string }) =>
        apiFetch<GuardrailRunResult>("/api/composed-agents/test-guardrail", {
            method: "POST",
            body: JSON.stringify(data),
        }),
    // Saved guardrails library
    listSaved: () => apiFetch<SavedGuardrail[]>("/api/composed-agents/saved-guardrails"),
    createSaved: (data: { name: string; description?: string; type: string; config: Record<string, any> }) =>
        apiFetch<SavedGuardrail>("/api/composed-agents/saved-guardrails", {
            method: "POST",
            body: JSON.stringify(data),
        }),
    updateSaved: (id: string, data: Partial<SavedGuardrail>) =>
        apiFetch<SavedGuardrail>(`/api/composed-agents/saved-guardrails/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    deleteSaved: (id: string) =>
        apiFetch<void>(`/api/composed-agents/saved-guardrails/${id}`, { method: "DELETE" }),
    // Audit log
    listEvents: (id: string, params?: { run_id?: string; limit?: number }) => {
        const qs = new URLSearchParams();
        if (params?.run_id) qs.set("run_id", params.run_id);
        if (params?.limit) qs.set("limit", String(params.limit));
        const tail = qs.toString() ? `?${qs}` : "";
        return apiFetch<GuardrailEvent[]>(`/api/composed-agents/${id}/events${tail}`);
    },
};

// ─── Voice ──────────────────────────────────────────────────────────────────

export const voiceApi = {
    catalog: () => apiFetch<VoiceCatalog>("/api/voice/voices"),
    health: () =>
        apiFetch<{ stt: Record<string, boolean>; tts: Record<string, boolean> }>(
            "/api/voice/health",
        ),
    transcribe: async (file: Blob, language = "en", provider?: string) => {
        const form = new FormData();
        form.append("file", file, "audio.webm");
        form.append("language", language);
        if (provider) form.append("provider", provider);
        const res = await fetch(`${API_BASE}/api/voice/transcribe`, {
            method: "POST",
            body: form,
            credentials: "include",
        });
        if (!res.ok) throw new Error(`transcribe failed: ${res.status}`);
        return res.json() as Promise<{ text: string; provider: string; language: string | null }>;
    },
    synthesizeUrl: (text: string, voice?: string, speed = 1.0, provider?: string) => {
        // Returns a Blob URL the caller can drop into <audio>
        return fetch(`${API_BASE}/api/voice/synthesize`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: JSON.stringify({ text, voice, speed, provider, format: "mp3" }),
        })
            .then(async (res) => {
                if (!res.ok) throw new Error(`synthesize failed: ${res.status}`);
                const blob = await res.blob();
                return URL.createObjectURL(blob);
            });
    },
};

// ─── Folders ────────────────────────────────────────────────────────────────

export const foldersApi = {
    list: () => apiFetch<Folder[]>("/api/agents/folders"),
    create: (data: Partial<Folder>) =>
        apiFetch<Folder>("/api/agents/folders", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Folder>) =>
        apiFetch<Folder>(`/api/agents/folders/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
        apiFetch<void>(`/api/agents/folders/${id}`, { method: "DELETE" }),
};

// ─── LLM Providers ──────────────────────────────────────────────────────────

export const llmsApi = {
    list: () => apiFetch<LLMProvider[]>("/api/llms/"),
    create: (data: any) =>
        apiFetch<LLMProvider>("/api/llms/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: any) =>
        apiFetch<LLMProvider>(`/api/llms/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
        apiFetch<void>(`/api/llms/${id}`, { method: "DELETE" }),
    ollamaModels: () => apiFetch<OllamaModel[]>("/api/llms/ollama/models"),
    ollamaStatus: () => apiFetch<{ connected: boolean }>("/api/llms/ollama/status"),
    openRouterModels: () => apiFetch<OpenRouterModel[]>("/api/llms/openrouter/models"),
    perplexityModels: () => apiFetch<PerplexityModel[]>("/api/llms/perplexity/models"),
    groqModels: () => apiFetch<GroqModel[]>("/api/llms/groq/models"),
    googleModels: () => apiFetch<GeminiModel[]>("/api/llms/google/models"),
    clodModels: () => apiFetch<ClodModel[]>("/api/llms/clod/models"),
    nvidiaModels: () => apiFetch<NvidiaModel[]>("/api/llms/nvidia_nim/models"),
    anthropicModels: () => apiFetch<{ id: string; name: string }[]>("/api/llms/anthropic/models"),
    openaiModels: () => apiFetch<{ id: string; name: string }[]>("/api/llms/openai/models"),
    openRouterQuota: () => apiFetch<OpenRouterQuota>("/api/llms/openrouter/quota"),
};

// ─── Tools ──────────────────────────────────────────────────────────────────

export const toolsApi = {
    list: () => apiFetch<ToolInfo[]>("/api/tools/"),
};

// ─── Chat ───────────────────────────────────────────────────────────────────

export const chatApi = {
    send: (agentId: string, message: string, conversationId?: string) =>
        apiFetch<{ conversation_id: string; message_id: string; content: string }>("/api/chat/", {
            method: "POST",
            body: JSON.stringify({ agent_id: agentId, message, conversation_id: conversationId }),
        }),

    streamUrl: (agentId: string, message: string, conversationId?: string) => {
        return `${API_BASE}/api/chat/stream`;
    },

    conversations: (agentId: string) =>
        apiFetch<Conversation[]>(`/api/chat/conversations/${agentId}`),

    messages: (agentId: string, conversationId: string) =>
        apiFetch<ChatMessage[]>(`/api/chat/conversations/${agentId}/${conversationId}/messages`),

    deleteConversation: (agentId: string, conversationId: string) =>
        apiFetch<{ status: string }>(`/api/chat/conversations/${agentId}/${conversationId}`, {
            method: "DELETE",
        }),

    dailyUsage: (agentId: string) =>
        apiFetch<AgentDailyUsage>(`/api/chat/usage/${agentId}`),

    extractFileContext: (file: File) => {
        const form = new FormData();
        form.append("file", file);
        return apiFetch<{ filename: string; content: string; char_count: number; truncated: boolean }>(
            "/api/chat/extract-file-context",
            { method: "POST", body: form },
        );
    },
};

// ─── System ─────────────────────────────────────────────────────────────────

export const systemApi = {
    health: () =>
        apiFetch<{ status: string; version: string; ollama_connected: boolean }>("/api/system/health"),
    status: () => apiFetch<any>("/api/system/status"),
    restart: () => apiFetch<{ status: string }>("/api/system/restart", { method: "POST" }),
};

// ─── Monitor ────────────────────────────────────────────────────────────────

export interface AgentMetrics {
    agent_id: string;
    requests: number;
    errors: number;
    error_rate: number;
    avg_latency_ms: number;
}

export interface RecentError {
    trace_id: string;
    agent_id: string;
    error_message: string | null;
    created_at: string;
}

export interface MonitorMetrics {
    period: string;
    total_requests: number;
    total_errors: number;
    avg_latency_ms: number;
    error_rate: number;
    agents: AgentMetrics[];
    recent_errors: RecentError[];
}

export interface MonitorAlert {
    id: string;
    severity: "warning" | "critical";
    type: "quota_exhausted" | "quota_warning" | "high_error_rate" | "recent_failure";
    title: string;
    message: string;
    agent_id?: string;
    provider?: string;
    model?: string;
}

export interface MonitorAlerts {
    alerts: MonitorAlert[];
    count: number;
}

export const monitorApi = {
    getUsage: () => apiFetch<MonitorUsageOverview>("/api/monitor/usage"),
    updateLimit: (provider: string, daily_limit: number, model: string) =>
        apiFetch<{ status: string }>(`/api/monitor/limits/${provider}`, {
            method: "POST",
            body: JSON.stringify({ daily_limit, model }),
        }),
    getMetrics: () => apiFetch<MonitorMetrics>("/api/monitor/metrics"),
    getAlerts: () => apiFetch<MonitorAlerts>("/api/monitor/alerts"),
};

// ─── MCP Server Types ───────────────────────────────────────────────────────

export interface MCPServer {
    id: string;
    name: string;
    description: string | null;
    transport_type: "stdio" | "sse" | "streamable_http";
    command: string | null;
    args: string[] | null;
    url: string | null;
    env_vars: Record<string, string> | null;
    is_active: boolean;
    status: "stopped" | "starting" | "running" | "error";
    tools: any[] | null;
    resources: any[] | null;
    prompts: any[] | null;
    icon: string | null;
    tags: string[] | null;
    created_at: string;
    updated_at: string;
}

// ─── Auth Types & API ────────────────────────────────────────────────────────

export interface AuthUser {
    id: string;
    email: string;
    username: string;
    role: string;
    is_active: boolean;
    is_first_login: boolean;
    created_at: string;
}

export interface TokenResponse {
    access_token: string;
    refresh_token: string;
    token_type: string;
    user: AuthUser;
}

export const authApi = {
    login: (email: string, password: string) =>
        apiFetch<TokenResponse>("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ email, password }),
        }),
    register: (email: string, username: string, password: string) =>
        apiFetch<TokenResponse>("/api/auth/register", {
            method: "POST",
            body: JSON.stringify({ email, username, password }),
        }),
    refresh: (refresh_token: string) =>
        apiFetch<TokenResponse>("/api/auth/refresh", {
            method: "POST",
            body: JSON.stringify({ refresh_token }),
        }),
    logout: (refresh_token: string) =>
        apiFetch<void>("/api/auth/logout", {
            method: "POST",
            body: JSON.stringify({ refresh_token }),
        }),
    me: () => apiFetch<AuthUser>("/api/auth/me"),
};

// ─── Memory Types & API ──────────────────────────────────────────────────────

export type MemoryType = "fact" | "episode" | "procedure";
export type MemoryTier = "core" | "recall" | "archival";

export interface Memory {
    id: string;
    agent_id: string | null;
    type: MemoryType;
    content: string;
    importance_score: number;
    access_count: number;
    last_accessed_at: string | null;
    tier: MemoryTier;
    decay_score: number;
    source: string;
    is_deleted: boolean;
    created_at: string;
}

export interface MemoryCreate {
    content: string;
    agent_id?: string | null;
    type?: MemoryType;
    importance_score?: number;
    tier?: MemoryTier;
}

export const memoryApi = {
    list: (agentId?: string, includeShared = false, tier?: MemoryTier) => {
        const params = new URLSearchParams();
        if (agentId) params.set("agent_id", agentId);
        if (includeShared) params.set("include_shared", "true");
        if (tier) params.set("tier", tier);
        return apiFetch<Memory[]>(`/api/memory/?${params}`);
    },
    listShared: () => apiFetch<Memory[]>("/api/memory/shared"),
    search: (q: string, agentId?: string, includeShared = true, tier?: MemoryTier) => {
        const params = new URLSearchParams({ q, include_shared: String(includeShared) });
        if (agentId) params.set("agent_id", agentId);
        if (tier) params.set("tier", tier);
        return apiFetch<Memory[]>(`/api/memory/search?${params}`);
    },
    create: (data: MemoryCreate) =>
        apiFetch<Memory>("/api/memory/", { method: "POST", body: JSON.stringify(data) }),
    promote: (id: string, targetTier: MemoryTier) =>
        apiFetch<Memory>(`/api/memory/${id}/promote?target_tier=${targetTier}`, { method: "PATCH" }),
    delete: (id: string) => apiFetch<void>(`/api/memory/${id}`, { method: "DELETE" }),
    clearAll: (agentId?: string) => {
        const params = agentId ? `?agent_id=${agentId}` : "";
        return apiFetch<{ deleted: number }>(`/api/memory/clear${params}`, { method: "DELETE" });
    },
};

// ─── System Settings ────────────────────────────────────────────────────────

export interface SystemSettingSchema {
    type: string;
    group: string;
    label: string;
    description: string;
    value: any;
    is_overridden: boolean;
    min?: number;
    max?: number;
}

export const systemSettingsApi = {
    get: () => apiFetch<Record<string, SystemSettingSchema>>("/api/settings/system/"),
    update: (updates: Record<string, any>) =>
        apiFetch<{ updated: string[]; values: Record<string, any> }>("/api/settings/system/", {
            method: "PATCH",
            body: JSON.stringify({ updates }),
        }),
    reset: () => apiFetch<{ status: string; values: Record<string, any> }>("/api/settings/system/reset", {
        method: "DELETE",
    }),
};

// ─── Environment Variables ───────────────────────────────────────────────────

export interface EnvVarItem {
    key: string;
    group: string;
    label: string;
    description: string;
    placeholder: string;
    is_secret: boolean;
    is_set: boolean;
    masked_value: string;   // plaintext for non-secrets, "••••abcd" for secrets
    source: "db" | "env" | "default";
}

export const envVarsApi = {
    list: () => apiFetch<EnvVarItem[]>("/api/settings/env/"),
    upsert: (vars: { key: string; value: string }[]) =>
        apiFetch<EnvVarItem[]>("/api/settings/env/", {
            method: "PUT",
            body: JSON.stringify({ vars }),
        }),
    delete: (key: string) =>
        apiFetch<{ ok: boolean; key: string }>(`/api/settings/env/${key}`, { method: "DELETE" }),
};


// ─── MCP Servers ────────────────────────────────────────────────────────────

// ─── Execution Traces ────────────────────────────────────────────────────────

export interface ExecutionTrace {
    id: string;
    agent_id: string;
    conversation_id: string | null;
    request_id: string | null;
    input_message: string;
    output_message: string | null;
    tool_calls: { name: string; input: string; output?: string }[];
    latency_ms: number | null;
    had_error: boolean;
    error_message: string | null;
    created_at: string;
}

export const tracesApi = {
    byAgent: (agentId: string, limit = 100, offset = 0) =>
        apiFetch<ExecutionTrace[]>(`/api/traces/agent/${agentId}?limit=${limit}&offset=${offset}`),
    get: (traceId: string) => apiFetch<ExecutionTrace>(`/api/traces/${traceId}`),
};

// ─── Audit Log ───────────────────────────────────────────────────────────────

export interface AuditEntry {
    id: string;
    actor_type: string;
    actor_id: string | null;
    action: string;
    resource_type: string | null;
    resource_id: string | null;
    details: Record<string, any> | null;
    ip_address: string | null;
    request_id: string | null;
    created_at: string;
}

export const auditApi = {
    list: (params?: { actor_id?: string; action?: string; resource_type?: string; resource_id?: string; limit?: number; offset?: number }) => {
        const q = new URLSearchParams();
        if (params?.actor_id) q.set("actor_id", params.actor_id);
        if (params?.action) q.set("action", params.action);
        if (params?.resource_type) q.set("resource_type", params.resource_type);
        if (params?.resource_id) q.set("resource_id", params.resource_id);
        if (params?.limit) q.set("limit", String(params.limit));
        if (params?.offset) q.set("offset", String(params.offset));
        return apiFetch<AuditEntry[]>(`/api/audit/?${q}`);
    },
};

// ─── MCP Servers ────────────────────────────────────────────────────────────

// ─── Discussion Types & API ──────────────────────────────────────────────────

export type DiscussionType = "brainstorm" | "debate" | "review" | "standup" | "retrospective";
export type DiscussionStatus = "pending" | "active" | "concluded" | "failed";

export interface DiscussionMessage {
    agent_id: string;
    agent_name: string;
    content: string;
    round: number;
    is_moderator: boolean;
    timestamp: string;
}

export interface Discussion {
    id: string;
    title: string;
    topic: string;
    type: DiscussionType;
    status: DiscussionStatus;
    participant_agent_ids: string[];
    moderator_agent_id: string | null;
    messages: DiscussionMessage[];
    summary: string | null;
    action_items: string[] | null;
    max_rounds: number;
    task_id: string | null;
    created_by_user_id: string | null;
    created_by_agent_id: string | null;
    concluded_at: string | null;
    created_at: string;
    updated_at: string;
}

export const discussionsApi = {
    list: (params?: { status?: string }) => {
        const q = new URLSearchParams();
        if (params?.status) q.set("status", params.status);
        return apiFetch<Discussion[]>(`/api/discussions/?${q}`);
    },
    get: (id: string) => apiFetch<Discussion>(`/api/discussions/${id}`),
    create: (data: Partial<Discussion>) =>
        apiFetch<Discussion>("/api/discussions/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Discussion>) =>
        apiFetch<Discussion>(`/api/discussions/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
        apiFetch<void>(`/api/discussions/${id}`, { method: "DELETE" }),
    reset: (id: string) =>
        apiFetch<Discussion>(`/api/discussions/${id}/reset`, { method: "POST" }),
    addMessage: (id: string, content: string) =>
        apiFetch<Discussion>(`/api/discussions/${id}/message`, { method: "POST", body: JSON.stringify({ content }) }),
};

// ─── Council Types & API ─────────────────────────────────────────────────────

export type CouncilDebateMode = "role_based" | "model_native";
export type CouncilStatus = "pending" | "active" | "concluded" | "failed";

export interface CouncilContext {
    background?: string | null;
    constraints?: string | null;
    non_negotiables?: string | null;
    success_criteria?: string | null;
}

export interface CouncilMessage {
    agent_id: string;
    agent_name: string;
    role: string;
    content: string;
    round: number;
    phase: string;
    timestamp: string;
}

export interface Council {
    id: string;
    title: string;
    question: string;
    context: CouncilContext;
    advisor_agent_ids: string[];
    arbitrator_agent_id: string;
    debate_mode: CouncilDebateMode;
    role_assignments: Record<string, string>;
    num_rounds: number;
    status: CouncilStatus;
    messages: CouncilMessage[];
    final_report: string | null;
    created_by_user_id: string | null;
    concluded_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface CouncilCreatePayload {
    title: string;
    question: string;
    context?: CouncilContext;
    advisor_agent_ids: string[];
    arbitrator_agent_id: string;
    debate_mode: CouncilDebateMode;
    role_assignments?: Record<string, string>;
    num_rounds: number;
}

export const councilsApi = {
    list: (params?: { status?: string }) => {
        const q = new URLSearchParams();
        if (params?.status) q.set("status", params.status);
        return apiFetch<Council[]>(`/api/councils/?${q}`);
    },
    get: (id: string) => apiFetch<Council>(`/api/councils/${id}`),
    create: (data: CouncilCreatePayload) =>
        apiFetch<Council>("/api/councils/", { method: "POST", body: JSON.stringify(data) }),
    delete: (id: string) =>
        apiFetch<void>(`/api/councils/${id}`, { method: "DELETE" }),
    reset: (id: string) =>
        apiFetch<Council>(`/api/councils/${id}/reset`, { method: "POST" }),
};

// ─── Task & Project Types ────────────────────────────────────────────────────

export type TaskStatus = "backlog" | "todo" | "in_progress" | "review" | "done";
export type TaskPriority = "critical" | "high" | "medium" | "low";
export type ProjectStatus = "active" | "on_hold" | "completed" | "archived";

export interface Project {
    id: string;
    name: string;
    slug: string | null;
    description: string | null;
    status: ProjectStatus;
    color: string | null;
    icon: string | null;
    owner_user_id: string | null;
    default_agent_id: string | null;
    memory_count: number;
    conversation_count: number;
    task_count: number;
    last_active_at: string | null;
    compaction_summary: string | null;
    created_at: string;
    updated_at: string;
}

export interface ProjectDecision {
    id: string;
    project_id: string;
    title: string;
    decision: string;
    reasoning: string;
    alternatives_considered: string[] | null;
    importance: string;
    tags: string[];
    data_points: Record<string, any> | null;
    conversation_id: string | null;
    agent_id: string | null;
    created_by_user_id: string | null;
    is_superseded: boolean;
    superseded_by_id: string | null;
    created_at: string;
    updated_at: string;
}

export interface ProjectFile {
    id: string;
    project_id: string;
    file_name: string;
    file_path: string;
    file_size: number;
    mime_type: string | null;
    description: string | null;
    uploaded_by_user_id: string | null;
    created_at: string;
    updated_at: string;
}

export interface Task {
    id: string;
    title: string;
    description: string | null;
    status: TaskStatus;
    priority: TaskPriority;
    project_id: string | null;
    parent_task_id: string | null;
    assignee_agent_id: string | null;
    assignee_user_id: string | null;
    creator_agent_id: string | null;
    creator_user_id: string | null;
    due_date: string | null;
    notes: string | null;
    created_at: string;
    updated_at: string;
}

export const projectsApi = {
    list: (params?: { status?: string }) => {
        const q = new URLSearchParams();
        if (params?.status) q.set("status", params.status);
        const qs = q.toString();
        return apiFetch<Project[]>(`/api/projects${qs ? `?${qs}` : ""}`);
    },
    get: (id: string) => apiFetch<Project>(`/api/projects/${id}`),
    create: (data: Partial<Project>) =>
        apiFetch<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Project>) =>
        apiFetch<Project>(`/api/projects/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
        apiFetch<void>(`/api/projects/${id}`, { method: "DELETE" }),

    // Project switching
    switchAgent: (projectId: string, agentId: string) =>
        apiFetch<{ detail: string; project_id: string }>(`/api/projects/${projectId}/switch/${agentId}`, { method: "POST" }),
    clearSwitch: (projectId: string, agentId: string) =>
        apiFetch<{ detail: string }>(`/api/projects/${projectId}/switch/${agentId}`, { method: "DELETE" }),

    // Project memories
    listMemories: (id: string, params?: { tier?: string; memory_type?: string }) => {
        const q = new URLSearchParams();
        if (params?.tier) q.set("tier", params.tier);
        if (params?.memory_type) q.set("memory_type", params.memory_type);
        const qs = q.toString();
        return apiFetch<any[]>(`/api/projects/${id}/memories${qs ? `?${qs}` : ""}`);
    },
    createMemory: (id: string, data: any) =>
        apiFetch<any>(`/api/projects/${id}/memories`, { method: "POST", body: JSON.stringify(data) }),
    searchMemories: (id: string, q: string) =>
        apiFetch<any[]>(`/api/projects/${id}/memories/search?q=${encodeURIComponent(q)}`),

    // Project tasks
    listTasks: (id: string, params?: { status?: string }) => {
        const q = new URLSearchParams();
        if (params?.status) q.set("status", params.status);
        const qs = q.toString();
        return apiFetch<any[]>(`/api/projects/${id}/tasks${qs ? `?${qs}` : ""}`);
    },

    // Project conversations
    listConversations: (id: string) =>
        apiFetch<any[]>(`/api/projects/${id}/conversations`),

    // Project decisions
    listDecisions: (id: string, params?: { importance?: string; include_superseded?: boolean }) => {
        const q = new URLSearchParams();
        if (params?.importance) q.set("importance", params.importance);
        if (params?.include_superseded) q.set("include_superseded", "true");
        const qs = q.toString();
        return apiFetch<ProjectDecision[]>(`/api/projects/${id}/decisions${qs ? `?${qs}` : ""}`);
    },
    createDecision: (id: string, data: Partial<ProjectDecision>) =>
        apiFetch<ProjectDecision>(`/api/projects/${id}/decisions`, { method: "POST", body: JSON.stringify(data) }),
    updateDecision: (projectId: string, decisionId: string, data: Partial<ProjectDecision>) =>
        apiFetch<ProjectDecision>(`/api/projects/${projectId}/decisions/${decisionId}`, { method: "PUT", body: JSON.stringify(data) }),

    // Project files
    listFiles: (id: string) =>
        apiFetch<ProjectFile[]>(`/api/projects/${id}/files`),
    deleteFile: (projectId: string, fileId: string) =>
        apiFetch<void>(`/api/projects/${projectId}/files/${fileId}`, { method: "DELETE" }),

    // Compaction
    compact: (id: string) =>
        apiFetch<{ decay_updated: number; consolidated: number; conversations_summarized: number }>(`/api/projects/${id}/compact`, { method: "POST" }),
};

export const tasksApi = {
    list: (params?: { project_id?: string; status?: string; assignee_agent_id?: string }) => {
        const q = new URLSearchParams();
        if (params?.project_id) q.set("project_id", params.project_id);
        if (params?.status) q.set("status", params.status);
        if (params?.assignee_agent_id) q.set("assignee_agent_id", params.assignee_agent_id);
        return apiFetch<Task[]>(`/api/tasks?${q}`);
    },
    get: (id: string) => apiFetch<Task>(`/api/tasks/${id}`),
    create: (data: Partial<Task>) =>
        apiFetch<Task>("/api/tasks", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Task>) =>
        apiFetch<Task>(`/api/tasks/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
        apiFetch<void>(`/api/tasks/${id}`, { method: "DELETE" }),
    subtasks: (id: string) => apiFetch<Task[]>(`/api/tasks/${id}/subtasks`),
    decompose: (taskId: string, data?: { agent_id?: string; guidance?: string; max_subtasks?: number }) =>
        apiFetch<Task[]>(`/api/tasks/${taskId}/decompose`, { method: "POST", body: JSON.stringify(data ?? {}) }),
};

// ─── Roles & Teams (Phase 1.4) ───────────────────────────────────────────────

export interface AgentRole {
    id: string;
    name: string;
    description: string | null;
    system_prompt_template: string | null;
    default_tools: string[];
    permissions: Record<string, any>;
    reports_to_role: string | null;
    color: string | null;
    icon: string | null;
    created_at: string;
    updated_at: string;
}

export interface RoleTemplate {
    name: string;
    description: string;
    system_prompt_template: string;
    default_tools: string[];
    permissions: Record<string, any>;
    reports_to_role: string | null;
    color: string | null;
    icon: string | null;
}

export interface Team {
    id: string;
    name: string;
    description: string | null;
    shared_context: string | null;
    lead_agent_id: string | null;
    member_agent_ids: string[];
    color: string | null;
    created_at: string;
    updated_at: string;
}

export interface OrgChartNode {
    id: string;
    name: string;
    status: string;
    role_id: string | null;
    role_name: string | null;
    role_color: string | null;
    role_icon: string | null;
    team_id: string | null;
    reports_to_agent_id: string | null;
    skills: string[];
    avatar_url: string | null;
}

export const rolesApi = {
    templates: () => apiFetch<RoleTemplate[]>("/api/roles/templates"),
    list: () => apiFetch<AgentRole[]>("/api/roles/"),
    get: (id: string) => apiFetch<AgentRole>(`/api/roles/${id}`),
    create: (data: Partial<AgentRole>) =>
        apiFetch<AgentRole>("/api/roles/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<AgentRole>) =>
        apiFetch<AgentRole>(`/api/roles/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) => apiFetch<void>(`/api/roles/${id}`, { method: "DELETE" }),
    reseed: () => apiFetch<{ updated: string[] }>("/api/roles/reseed", { method: "POST" }),
};

export const teamsApi = {
    list: () => apiFetch<Team[]>("/api/teams/"),
    get: (id: string) => apiFetch<Team>(`/api/teams/${id}`),
    create: (data: Partial<Team>) =>
        apiFetch<Team>("/api/teams/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Team>) =>
        apiFetch<Team>(`/api/teams/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) => apiFetch<void>(`/api/teams/${id}`, { method: "DELETE" }),
};

export const orgApi = {
    chart: () => apiFetch<OrgChartNode[]>("/api/agents/org-chart"),
    applyRole: (agentId: string, data: {
        role_id: string;
        apply_prompt?: boolean;
        apply_tools?: boolean;
        reports_to_agent_id?: string | null;
        team_id?: string | null;
        skills?: string[];
    }) => apiFetch<Agent>(`/api/agents/${agentId}/apply-role`, { method: "POST", body: JSON.stringify(data) }),
};

// ─── Goals, Check-ins, Initiatives, Triggers (Phase 2.1) ─────────────────────

export type GoalStatus = "active" | "paused" | "completed" | "abandoned";
export type GoalPriority = "critical" | "high" | "medium" | "low";
export type InitiativeStatus = "pending" | "approved" | "rejected" | "implemented";
export type TriggerType = "webhook" | "schedule" | "manual";

export interface AgentGoal {
    id: string;
    agent_id: string;
    title: string;
    description: string | null;
    status: GoalStatus;
    priority: GoalPriority;
    deadline: string | null;
    success_criteria: string | null;
    progress_notes: { note: string; timestamp: string }[];
    created_by_user_id: string | null;
    created_at: string;
    updated_at: string;
}

export interface AgentCheckIn {
    id: string;
    agent_id: string;
    summary: string | null;
    goals_reviewed: { goal_id: string; title: string; progress: string; status_update: string; next_step: string }[];
    tasks_reviewed: { task_id: string; title: string; status: string; note: string }[];
    blockers: string[];
    proposed_actions: string[];
    stuck_items: { task_id: string; title: string; status: string; days_stale: number }[];
    proposed_initiatives: any[];
    had_error: boolean;
    raw_response: string | null;
    created_at: string;
}

export interface AgentInitiative {
    id: string;
    agent_id: string;
    checkin_id: string | null;
    title: string;
    description: string | null;
    rationale: string | null;
    proposed_actions: string[];
    estimated_impact: string | null;
    status: InitiativeStatus;
    reviewed_by_user_id: string | null;
    reviewer_note: string | null;
    reviewed_at: string | null;
    created_at: string;
}

export interface AgentTrigger {
    id: string;
    agent_id: string;
    name: string;
    description: string | null;
    trigger_type: TriggerType;
    is_active: boolean;
    cron_expression: string | null;
    webhook_token: string;
    prompt_template: string;
    last_fired_at: string | null;
    fire_count: number;
    last_output: string | null;
    last_error: string | null;
    created_at: string;
    updated_at: string;
}

export const goalsApi = {
    list: (params?: { agent_id?: string; status?: string }) => {
        const q = new URLSearchParams();
        if (params?.agent_id) q.set("agent_id", params.agent_id);
        if (params?.status) q.set("status", params.status);
        return apiFetch<AgentGoal[]>(`/api/goals/?${q}`);
    },
    get: (id: string) => apiFetch<AgentGoal>(`/api/goals/${id}`),
    create: (data: Partial<AgentGoal>) =>
        apiFetch<AgentGoal>("/api/goals/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<AgentGoal>) =>
        apiFetch<AgentGoal>(`/api/goals/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) => apiFetch<void>(`/api/goals/${id}`, { method: "DELETE" }),
    addProgress: (id: string, note: string) =>
        apiFetch<AgentGoal>(`/api/goals/${id}/progress`, { method: "POST", body: JSON.stringify({ note }) }),
};

export const checkinsApi = {
    list: (params?: { agent_id?: string; limit?: number }) => {
        const q = new URLSearchParams();
        if (params?.agent_id) q.set("agent_id", params.agent_id);
        if (params?.limit) q.set("limit", String(params.limit));
        return apiFetch<AgentCheckIn[]>(`/api/checkins/?${q}`);
    },
    get: (id: string) => apiFetch<AgentCheckIn>(`/api/checkins/${id}`),
    run: (agentId: string) =>
        apiFetch<{ message: string }>(`/api/checkins/run/${agentId}`, { method: "POST" }),
    delete: (id: string) => apiFetch<void>(`/api/checkins/${id}`, { method: "DELETE" }),
};

export const initiativesApi = {
    list: (params?: { agent_id?: string; status?: string }) => {
        const q = new URLSearchParams();
        if (params?.agent_id) q.set("agent_id", params.agent_id);
        if (params?.status) q.set("status", params.status);
        return apiFetch<AgentInitiative[]>(`/api/initiatives/?${q}`);
    },
    create: (data: Partial<AgentInitiative>) =>
        apiFetch<AgentInitiative>("/api/initiatives/", { method: "POST", body: JSON.stringify(data) }),
    approve: (id: string, note?: string) =>
        apiFetch<AgentInitiative>(`/api/initiatives/${id}/approve`, { method: "POST", body: JSON.stringify({ note }) }),
    reject: (id: string, note?: string) =>
        apiFetch<AgentInitiative>(`/api/initiatives/${id}/reject`, { method: "POST", body: JSON.stringify({ note }) }),
    delete: (id: string) =>
        apiFetch<void>(`/api/initiatives/${id}`, { method: "DELETE" }),
};

export const triggersApi = {
    list: (agentId?: string) => {
        const q = agentId ? `?agent_id=${agentId}` : "";
        return apiFetch<AgentTrigger[]>(`/api/triggers/${q}`);
    },
    get: (id: string) => apiFetch<AgentTrigger>(`/api/triggers/${id}`),
    create: (data: Partial<AgentTrigger>) =>
        apiFetch<AgentTrigger>("/api/triggers/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<AgentTrigger>) =>
        apiFetch<AgentTrigger>(`/api/triggers/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) => apiFetch<void>(`/api/triggers/${id}`, { method: "DELETE" }),
    fire: (id: string, payload?: Record<string, any>) =>
        apiFetch<{ message: string }>(`/api/triggers/${id}/fire`, { method: "POST", body: JSON.stringify(payload || {}) }),
};

export const mcpServersApi = {
    list: () => apiFetch<MCPServer[]>("/api/mcp-servers/"),
    get: (id: string) => apiFetch<MCPServer>(`/api/mcp-servers/${id}`),
    create: (data: Partial<MCPServer>) =>
        apiFetch<MCPServer>("/api/mcp-servers/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<MCPServer>) =>
        apiFetch<MCPServer>(`/api/mcp-servers/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) =>
        apiFetch<void>(`/api/mcp-servers/${id}`, { method: "DELETE" }),
    start: (id: string) =>
        apiFetch<{ message: string; status: string }>(`/api/mcp-servers/${id}/start`, { method: "POST" }),
    stop: (id: string) =>
        apiFetch<{ message: string; status: string }>(`/api/mcp-servers/${id}/stop`, { method: "POST" }),
};

// ─── Approval Request Types & API ────────────────────────────────────────────

export type ApprovalCategory = "financial" | "external" | "destructive" | "strategic" | "general";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type ApprovalStatus = "pending" | "approved" | "rejected" | "expired";

export interface ApprovalRequest {
    id: string;
    title: string;
    description: string | null;
    category: ApprovalCategory | null;
    risk_level: RiskLevel | null;
    context: {
        reasoning?: string;
        alternatives?: string;
        risk_assessment?: string;
        recommended_action?: string;
        [key: string]: any;
    } | null;
    action_payload: Record<string, any> | null;
    status: ApprovalStatus;
    requester_agent_id: string | null;
    workflow_id: string | null;
    node_id: string | null;
    reviewer_user_id: string | null;
    reviewer_note: string | null;
    decided_at: string | null;
    expires_at: string | null;
    created_at: string;
    updated_at: string;
}

export const approvalsApi = {
    list: (params?: { status?: string }) => {
        const q = new URLSearchParams();
        if (params?.status) q.set("status", params.status);
        const qs = q.toString();
        return apiFetch<ApprovalRequest[]>(`/api/approvals/${qs ? `?${qs}` : ""}`);
    },
    get: (id: string) => apiFetch<ApprovalRequest>(`/api/approvals/${id}`),
    create: (data: Partial<ApprovalRequest> & { expires_in_minutes?: number }) =>
        apiFetch<ApprovalRequest>("/api/approvals/", { method: "POST", body: JSON.stringify(data) }),
    approve: (id: string, note?: string) =>
        apiFetch<ApprovalRequest>(`/api/approvals/${id}/approve`, {
            method: "POST",
            body: JSON.stringify({ note }),
        }),
    reject: (id: string, note?: string) =>
        apiFetch<ApprovalRequest>(`/api/approvals/${id}/reject`, {
            method: "POST",
            body: JSON.stringify({ note }),
        }),
    pendingCount: () => apiFetch<{ count: number }>("/api/approvals/pending-count"),
};

// ─── Workflows ───────────────────────────────────────────────────────────────

export interface WorkflowSummary {
    id: string;
    name: string;
    description: string | null;
    schedule_interval: number | null;
    is_active: boolean;
    last_run_status?: string | null;
    last_run_at?: string | null;
    last_run_logs?: { timestamp: string; node_id?: string; type: string; message: string }[] | null;
    definition?: any;
}

export const workflowsApi = {
    list: () => apiFetch<WorkflowSummary[]>("/api/workflows/"),
    get: (id: string) => apiFetch<WorkflowSummary>(`/api/workflows/${id}`),
    create: (data: Partial<WorkflowSummary>) =>
        apiFetch<WorkflowSummary>("/api/workflows/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<WorkflowSummary>) =>
        apiFetch<WorkflowSummary>(`/api/workflows/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) => apiFetch<void>(`/api/workflows/${id}`, { method: "DELETE" }),
    execute: (id: string) =>
        apiFetch<any>(`/api/workflows/${id}/execute`, { method: "POST" }),
    exportUrl: (id: string, format: "json" | "markdown") =>
        `${API_BASE}/api/workflows/${id}/export?format=${format}`,
    import: (content: string, format: "json" | "markdown", nameOverride?: string) =>
        apiFetch<WorkflowSummary>("/api/workflows/import", {
            method: "POST",
            body: JSON.stringify({ content, format, name_override: nameOverride ?? null }),
        }),
    generateFromText: (description: string, agentId?: string) =>
        apiFetch<WorkflowSummary>("/api/workflows/generate", {
            method: "POST",
            body: JSON.stringify({ description, agent_id: agentId ?? null }),
        }),
};

// ─── Scheduled Jobs ──────────────────────────────────────────────────────────

export interface Job {
    id: string;
    name: string;
    description: string | null;
    execution_type: string;
    target_id: string | null;
    prompt_text: string | null;
    n8n_webhook_url: string | null;
    cron_expression: string;
    timezone: string;
    is_active: boolean;
    notify_email: string | null;
    notify_telegram_chat_id: string | null;
    last_run_at: string | null;
    last_run_status: string | null;
    created_at: string;
}

export const jobsApi = {
    list: () => apiFetch<Job[]>("/api/jobs/"),
    listScripts: () => apiFetch<string[]>("/api/jobs/scripts"),
    get: (id: string) => apiFetch<Job>(`/api/jobs/${id}`),
    create: (data: Partial<Job>) =>
        apiFetch<Job>("/api/jobs/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Job>) =>
        apiFetch<Job>(`/api/jobs/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) => apiFetch<void>(`/api/jobs/${id}`, { method: "DELETE" }),
    run: (id: string) =>
        apiFetch<{ message: string }>(`/api/jobs/${id}/run`, { method: "POST" }),
};

// ─── Batch Jobs ───────────────────────────────────────────────────────────────

export interface BatchJob {
    id: string;
    name: string;
    description: string | null;
    job_ids: string[];
    cron_expression: string;
    timezone: string;
    execution_mode: string;
    is_active: boolean;
    notify_email: string | null;
    notify_telegram_chat_id: string | null;
    last_run_at: string | null;
    last_run_status: string | null;
    created_at: string;
    updated_at: string;
}

export interface BatchJobRun {
    id: string;
    batch_job_id: string;
    started_at: string;
    completed_at: string | null;
    status: string;
    results: Record<string, { status: string; duration_ms: number; error?: string; output?: string }>;
}

export const batchJobsApi = {
    list: () => apiFetch<BatchJob[]>("/api/batch-jobs/"),
    get: (id: string) => apiFetch<BatchJob>(`/api/batch-jobs/${id}`),
    create: (data: Partial<BatchJob>) =>
        apiFetch<BatchJob>("/api/batch-jobs/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<BatchJob>) =>
        apiFetch<BatchJob>(`/api/batch-jobs/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) => apiFetch<void>(`/api/batch-jobs/${id}`, { method: "DELETE" }),
    run: (id: string) =>
        apiFetch<{ message: string }>(`/api/batch-jobs/${id}/run`, { method: "POST" }),
    listRuns: (id: string) => apiFetch<BatchJobRun[]>(`/api/batch-jobs/${id}/runs`),
    getRun: (id: string, runId: string) => apiFetch<BatchJobRun>(`/api/batch-jobs/${id}/runs/${runId}`),
};

// ─── Financial Management Types & API ────────────────────────────────────────

export type BudgetScope = "agent" | "team" | "org";
export type BudgetPeriod = "daily" | "weekly" | "monthly";

export interface Budget {
    id: string;
    name: string;
    description: string | null;
    scope: BudgetScope;
    agent_id: string | null;
    team_id: string | null;
    period: BudgetPeriod;
    limit_usd: number;
    alert_threshold_pct: number;
    created_by_user_id: string | null;
    created_at: string;
    updated_at: string;
}

export interface BudgetStatus {
    budget_id: string;
    name: string;
    scope: string;
    period: string;
    limit_usd: number;
    spent_usd: number;
    remaining_usd: number;
    utilization_pct: number;
    alert_threshold_pct: number;
    is_over_budget: boolean;
    is_near_threshold: boolean;
}

export interface ModelPricingRow {
    id: string | null;
    provider: string;
    model: string;
    input_cost_per_1k: number;
    output_cost_per_1k: number;
    is_custom: boolean;
}

export interface CostOverview {
    period: string;
    since: string | null;
    total_cost_usd: number;
    total_tokens: number;
    by_agent: { agent_id: string; agent_name: string; cost_usd: number }[];
    by_provider: { provider_model: string; cost_usd: number }[];
}

export interface TrendData {
    days: number;
    data: { date: string; cost_usd: number }[];
}

export const financialsApi = {
    overview: (period?: string) =>
        apiFetch<CostOverview>(`/api/financials/overview${period ? `?period=${period}` : ""}`),
    trends: (days?: number) =>
        apiFetch<TrendData>(`/api/financials/trends${days ? `?days=${days}` : ""}`),

    listBudgets: () => apiFetch<Budget[]>("/api/financials/budgets"),
    createBudget: (data: Partial<Budget>) =>
        apiFetch<Budget>("/api/financials/budgets", { method: "POST", body: JSON.stringify(data) }),
    updateBudget: (id: string, data: Partial<Budget>) =>
        apiFetch<Budget>(`/api/financials/budgets/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteBudget: (id: string) =>
        apiFetch<void>(`/api/financials/budgets/${id}`, { method: "DELETE" }),
    getBudgetStatus: (id: string) =>
        apiFetch<BudgetStatus>(`/api/financials/budgets/${id}/status`),
    getBudgetAlerts: () =>
        apiFetch<{ alerts: any[]; count: number }>("/api/financials/budget-alerts"),

    listPricing: () => apiFetch<ModelPricingRow[]>("/api/financials/pricing"),
    upsertPricing: (provider: string, model: string, data: { input_cost_per_1k: number; output_cost_per_1k: number }) =>
        apiFetch<ModelPricingRow>(`/api/financials/pricing/${provider}/${model}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
};


// ─── Knowledge Base / RAG Types ──────────────────────────────────────────────

export interface KnowledgeBase {
    id: string;
    name: string;
    description: string | null;
    is_shared: boolean;
    owner_user_id: string | null;
    document_count: number;
    created_at: string;
}

export interface KBDocument {
    id: string;
    knowledge_base_id: string;
    title: string;
    source_type: "file" | "url" | "text";
    source_url: string | null;
    file_name: string | null;
    status: "pending" | "processing" | "ready" | "failed";
    chunk_count: number;
    token_count: number;
    error_message: string | null;
    created_at: string;
}

export interface KBSearchResult {
    chunk_id: string;
    content: string;
    score: number;
    document_id: string;
    document_title: string;
    source_url: string | null;
    knowledge_base_id: string;
}

export const knowledgeApi = {
    list: () => apiFetch<KnowledgeBase[]>("/api/knowledge-bases/"),
    create: (data: { name: string; description?: string; is_shared?: boolean }) =>
        apiFetch<KnowledgeBase>("/api/knowledge-bases/", { method: "POST", body: JSON.stringify(data) }),
    delete: (id: string) => apiFetch<void>(`/api/knowledge-bases/${id}`, { method: "DELETE" }),

    listDocuments: (kbId: string) => apiFetch<KBDocument[]>(`/api/knowledge-bases/${kbId}/documents`),
    deleteDocument: (kbId: string, docId: string) =>
        apiFetch<void>(`/api/knowledge-bases/${kbId}/documents/${docId}`, { method: "DELETE" }),

    ingest: (kbId: string, data: { title: string; source_type: string; source_url?: string; content?: string }) =>
        apiFetch<KBDocument>(`/api/knowledge-bases/${kbId}/ingest`, { method: "POST", body: JSON.stringify(data) }),

    upload: (kbId: string, file: File, title?: string) => {
        const form = new FormData();
        form.append("file", file);
        if (title) form.append("title", title);
        return apiFetch<KBDocument>(`/api/knowledge-bases/${kbId}/upload`, { method: "POST", body: form });
    },

    reindex: (kbId: string, docId: string) =>
        apiFetch<KBDocument>(`/api/knowledge-bases/${kbId}/documents/${docId}/reindex`, { method: "POST" }),

    search: (kbId: string, q: string, topK?: number) =>
        apiFetch<KBSearchResult[]>(`/api/knowledge-bases/${kbId}/search?q=${encodeURIComponent(q)}${topK ? `&top_k=${topK}` : ""}`),

    searchAll: (q: string, topK?: number) =>
        apiFetch<KBSearchResult[]>(`/api/knowledge-bases/search/all?q=${encodeURIComponent(q)}${topK ? `&top_k=${topK}` : ""}`),
};

// ─── Agent Templates (Phase 2.4) ─────────────────────────────────────────────

export interface AgentTemplate {
    id: string;
    name: string;
    description: string | null;
    category: string;
    system_prompt: string;
    default_tools: string[];
    default_llm_provider: string;
    default_llm_model: string;
    temperature: number;
    role_name: string | null;
    icon: string | null;
    color: string | null;
    tags: string[];
    is_builtin: boolean;
    created_by_agent_id: string | null;
    usage_count: number;
    created_at: string;
    updated_at: string;
}

export interface AgentPerformance {
    agent_id: string;
    agent_name: string;
    total_invocations: number;
    error_count: number;
    error_rate: number;
    avg_latency_ms: number;
    total_tasks_created: number;
    total_tasks_completed: number;
    task_completion_rate: number;
    total_cost_usd: number;
    performance_score: number;
}

export const agentTemplatesApi = {
    list: (category?: string) => {
        const q = category ? `?category=${encodeURIComponent(category)}` : "";
        return apiFetch<AgentTemplate[]>(`/api/agent-templates/${q}`);
    },
    categories: () => apiFetch<{ category: string; count: number }[]>("/api/agent-templates/categories"),
    get: (id: string) => apiFetch<AgentTemplate>(`/api/agent-templates/${id}`),
    create: (data: Partial<AgentTemplate>) =>
        apiFetch<AgentTemplate>("/api/agent-templates/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<AgentTemplate>) =>
        apiFetch<AgentTemplate>(`/api/agent-templates/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) => apiFetch<void>(`/api/agent-templates/${id}`, { method: "DELETE" }),
    fromAgent: (agentId: string, data: { name: string; description?: string; category?: string; tags?: string[] }) =>
        apiFetch<AgentTemplate>(`/api/agent-templates/from-agent/${agentId}`, { method: "POST", body: JSON.stringify(data) }),
    instantiate: (id: string, data: { name: string; description?: string; custom_instructions?: string; llm_provider?: string; llm_model?: string }) =>
        apiFetch<Agent>(`/api/agent-templates/${id}/instantiate`, { method: "POST", body: JSON.stringify(data) }),
    reseed: () => apiFetch<{ updated: string[]; created: string[] }>("/api/agent-templates/reseed", { method: "POST" }),
};

export const agentPerformanceApi = {
    get: (agentId: string) => apiFetch<AgentPerformance>(`/api/agents/${agentId}/performance`),
};

export const agentArchiveApi = {
    archive: (agentId: string, reason: string) =>
        apiFetch<Agent>(`/api/agents/${agentId}/archive`, { method: "POST", body: JSON.stringify({ reason }) }),
    unarchive: (agentId: string) =>
        apiFetch<Agent>(`/api/agents/${agentId}/unarchive`, { method: "POST" }),
    listArchived: () => apiFetch<Agent[]>("/api/agents/?include_archived=true"),
};

// ─── Email Types & API ───────────────────────────────────────────────────────

export interface EmailConfig {
    id: string;
    agent_id: string | null;
    label: string | null;
    provider: "SMTP" | "GMAIL";
    google_email: string | null;
    smtp_host: string | null;
    smtp_port: number | null;
    smtp_username: string | null;
    smtp_from_email: string | null;
    smtp_from_name: string | null;
    smtp_use_tls: boolean;
    smtp_use_ssl: boolean;
    imap_host: string | null;
    imap_port: number;
    imap_username: string | null;
    imap_use_ssl: boolean;
    imap_folder: string;
    created_at: string;
    updated_at: string;
}

export interface EmailWhitelistEntry {
    id: string;
    agent_id: string | null;
    email_address: string;
    label: string | null;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

// ─── Webhook Types & API ─────────────────────────────────────────────────────

export interface WebhookSubscription {
    id: string;
    name: string;
    url: string;
    events: string[];
    is_active: boolean;
    agent_id: string | null;
    headers: Record<string, string> | null;
    delivery_count: number;
    failure_count: number;
    last_delivery_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface WebhookDelivery {
    id: string;
    subscription_id: string;
    event_type: string;
    payload: Record<string, unknown>;
    status: "pending" | "delivered" | "failed";
    response_status: number | null;
    response_body: string | null;
    attempt_count: number;
    delivered_at: string | null;
    error: string | null;
    created_at: string;
}

export const webhooksApi = {
    // Event types
    listEvents: () => apiFetch<{ events: string[] }>("/api/webhooks/events"),

    // Subscriptions
    listSubscriptions: (agentId?: string) => {
        const qs = agentId ? `?agent_id=${agentId}` : "";
        return apiFetch<WebhookSubscription[]>(`/api/webhooks/subscriptions${qs}`);
    },
    createSubscription: (data: Partial<WebhookSubscription> & { url: string; secret?: string }) =>
        apiFetch<WebhookSubscription>("/api/webhooks/subscriptions", { method: "POST", body: JSON.stringify(data) }),
    updateSubscription: (id: string, data: Partial<WebhookSubscription> & { secret?: string }) =>
        apiFetch<WebhookSubscription>(`/api/webhooks/subscriptions/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteSubscription: (id: string) =>
        apiFetch<void>(`/api/webhooks/subscriptions/${id}`, { method: "DELETE" }),
    testSubscription: (id: string) =>
        apiFetch<{ message: string }>(`/api/webhooks/subscriptions/${id}/test`, { method: "POST" }),

    // Deliveries
    listDeliveries: (subscriptionId?: string, status?: string, limit?: number) => {
        const params = new URLSearchParams();
        if (subscriptionId) params.set("subscription_id", subscriptionId);
        if (status) params.set("status", status);
        if (limit) params.set("limit", String(limit));
        return apiFetch<WebhookDelivery[]>(`/api/webhooks/deliveries?${params}`);
    },
    retryDelivery: (id: string) =>
        apiFetch<{ message: string }>(`/api/webhooks/deliveries/${id}/retry`, { method: "POST" }),
};

// ─── Analytics Types & API (Phase 4.2) ───────────────────────────────────────

export interface ExecutiveSummary {
    period: string;
    since: string | null;
    // Task KPIs
    tasks_created: number;
    tasks_completed: number;
    tasks_in_progress: number;
    completion_rate: number;
    avg_time_to_done_hours: number;
    // Cost KPIs
    total_cost_usd: number;
    total_tokens: number;
    cost_per_task: number;
    // Request KPIs
    total_requests: number;
    avg_latency_ms: number;
    error_rate: number;
    // Agent KPIs
    active_agents: number;
    total_agents: number;
    top_agents_by_tasks: { agent_id: string; agent_name: string; tasks_completed: number }[];
    // Governance
    approvals_pending: number;
    budget_utilization: number;
}

export interface AgentSummary {
    agent_id: string;
    agent_name: string;
    status: string;
    llm_provider: string;
    llm_model: string;
    total_requests: number;
    error_rate: number;
    avg_latency_ms: number;
    total_cost_usd: number;
    tasks_completed: number;
    tasks_assigned: number;
}

export interface AgentScorecard {
    agent_id: string;
    agent_name: string;
    period: string;
    llm_provider: string;
    llm_model: string;
    status: string;
    total_requests: number;
    total_tokens: number;
    error_count: number;
    error_rate: number;
    avg_latency_ms: number;
    total_cost_usd: number;
    cost_per_request: number;
    tasks_assigned: number;
    tasks_completed: number;
    tasks_in_progress: number;
    task_completion_rate: number;
    top_tools: { tool: string; count: number }[];
    unique_tools_used: number;
    daily_trend: { date: string; requests: number }[];
}

export interface TeamMemberStat {
    agent_id: string;
    agent_name: string;
    status: string;
    tasks_completed: number;
    tasks_assigned: number;
    requests: number;
    cost_usd: number;
}

export interface TeamAnalytics {
    team_id: string;
    team_name: string;
    period: string;
    member_count: number;
    tasks_completed: number;
    tasks_in_progress: number;
    total_tasks: number;
    total_requests: number;
    total_cost_usd: number;
    discussions_participated: number;
    collaboration_index: number;
    members: TeamMemberStat[];
}

export interface AnalyticsTrendPoint {
    date: string;
    cost_usd: number;
    requests: number;
    errors: number;
    tasks_completed: number;
}

export interface AnalyticsTrends {
    days: number;
    data: AnalyticsTrendPoint[];
}

export const analyticsApi = {
    executive: (period?: string) =>
        apiFetch<ExecutiveSummary>(`/api/analytics/executive${period ? `?period=${period}` : ""}`),

    allAgents: (period?: string) =>
        apiFetch<{ period: string; agents: AgentSummary[] }>(`/api/analytics/agents${period ? `?period=${period}` : ""}`),

    agentScorecard: (agentId: string, period?: string) =>
        apiFetch<AgentScorecard>(`/api/analytics/agent-scorecard/${agentId}${period ? `?period=${period}` : ""}`),

    listTeams: () =>
        apiFetch<{ id: string; name: string; member_count: number }[]>("/api/analytics/teams"),

    team: (teamId: string, period?: string) =>
        apiFetch<TeamAnalytics>(`/api/analytics/team/${teamId}${period ? `?period=${period}` : ""}`),

    trends: (days?: number) =>
        apiFetch<AnalyticsTrends>(`/api/analytics/trends${days ? `?days=${days}` : ""}`),
};

export const emailApi = {
    // Configs
    listConfigs: () => apiFetch<EmailConfig[]>("/api/email/configs"),
    getConfig: (id: string) => apiFetch<EmailConfig>(`/api/email/configs/${id}`),
    getAgentConfig: (agentId: string) => apiFetch<EmailConfig>(`/api/email/configs/agent/${agentId}`),
    createConfig: (data: Partial<EmailConfig> & { smtp_password: string }) =>
        apiFetch<EmailConfig>("/api/email/configs", { method: "POST", body: JSON.stringify(data) }),
    updateConfig: (id: string, data: Partial<EmailConfig> & { smtp_password?: string }) =>
        apiFetch<EmailConfig>(`/api/email/configs/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteConfig: (id: string) =>
        apiFetch<void>(`/api/email/configs/${id}`, { method: "DELETE" }),
    testConfig: (id: string, to: string) =>
        apiFetch<{ status: string; message: string }>(`/api/email/configs/${id}/test`, {
            method: "POST", body: JSON.stringify({ to }),
        }),

    // Whitelist
    listWhitelist: (agentId?: string | null) => {
        const qs = agentId != null ? `?agent_id=${agentId}` : "";
        return apiFetch<EmailWhitelistEntry[]>(`/api/email/whitelist${qs}`);
    },
    addWhitelist: (data: { agent_id?: string | null; email_address: string; label?: string; is_active?: boolean }) =>
        apiFetch<EmailWhitelistEntry>("/api/email/whitelist", { method: "POST", body: JSON.stringify(data) }),
    updateWhitelist: (id: string, data: Partial<EmailWhitelistEntry>) =>
        apiFetch<EmailWhitelistEntry>(`/api/email/whitelist/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteWhitelist: (id: string) =>
        apiFetch<void>(`/api/email/whitelist/${id}`, { method: "DELETE" }),
};


// ─── Skills ───────────────────────────────────────────────────────────────────

export interface Skill {
    id: string;
    slug: string;
    name: string;
    description: string | null;
    is_active: boolean;
    routing_threshold: number | null;
    trigger_embed_model: string | null;
    created_at: string;
    updated_at: string;
    // Filesystem manifest fields (populated by list/get endpoints)
    body?: string;
    tools?: string[];
    config_schema?: Record<string, any> | null;
    icon?: string | null;
    color?: string | null;
    version?: string;
    category?: string;
    source?: "builtin" | "custom";
    files?: string[];
}

export interface AgentSkill {
    id: string;
    agent_id: string;
    skill_id: string;
    priority: number;
    config_overrides: Record<string, any>;
    is_active: boolean;
    always_load: boolean;
    skill: Skill;
    created_at: string;
    updated_at: string;
}

export interface RoleSkill {
    id: string;
    role_id: string;
    skill_id: string;
    priority: number;
    config_overrides: Record<string, any>;
    always_load: boolean;
    skill: Skill;
    created_at: string;
    updated_at: string;
}

export interface SkillReseedSummary {
    created: string[];
    updated: string[];
    deactivated: string[];
    re_embedded: string[];
    embed_model: string;
}

export const skillsApi = {
    // Skill CRUD
    list: (params?: { category?: string; source?: string; search?: string }) => {
        const qs = params ? `?${new URLSearchParams(params as Record<string, string>)}` : "";
        return apiFetch<Skill[]>(`/api/skills/${qs}`);
    },
    get: (id: string) => apiFetch<Skill>(`/api/skills/${id}`),
    update: (id: string, data: { routing_threshold?: number | null; is_active?: boolean }) =>
        apiFetch<Skill>(`/api/skills/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    reseed: () => apiFetch<SkillReseedSummary>("/api/skills/reseed", { method: "POST" }),
    exportBundle: (skillIds: string[]) =>
        apiFetch<{ version: string; exported_at: string; skills: Skill[] }>("/api/skills/export", {
            method: "POST",
            body: JSON.stringify({ skill_ids: skillIds }),
        }),
    importBundle: (file: File) => {
        const form = new FormData();
        form.append("file", file);
        return apiFetch<{ created: string[]; skipped: string[]; note?: string }>("/api/skills/import", {
            method: "POST",
            body: form,
            headers: {},
        });
    },
    // Agent-skill associations
    listForAgent: (agentId: string) =>
        apiFetch<AgentSkill[]>(`/api/agents/${agentId}/skills/`),
    attachToAgent: (
        agentId: string,
        data: { skill_id: string; priority?: number; config_overrides?: Record<string, any>; always_load?: boolean },
    ) =>
        apiFetch<AgentSkill>(`/api/agents/${agentId}/skills/`, {
            method: "POST",
            body: JSON.stringify(data),
        }),
    updateAgentSkill: (agentId: string, agentSkillId: string, data: Partial<AgentSkill>) =>
        apiFetch<AgentSkill>(`/api/agents/${agentId}/skills/${agentSkillId}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    detachFromAgent: (agentId: string, agentSkillId: string) =>
        apiFetch<void>(`/api/agents/${agentId}/skills/${agentSkillId}`, { method: "DELETE" }),
    reorderAgentSkills: (agentId: string, items: Array<{ agent_skill_id: string; priority: number }>) =>
        apiFetch<{ status: string }>(`/api/agents/${agentId}/skills/reorder`, {
            method: "POST",
            body: JSON.stringify(items),
        }),
    // Role-skill associations
    listForRole: (roleId: string) =>
        apiFetch<RoleSkill[]>(`/api/roles/${roleId}/skills/`),
    attachToRole: (roleId: string, data: { skill_id: string; priority?: number; config_overrides?: Record<string, any> }) =>
        apiFetch<RoleSkill>(`/api/roles/${roleId}/skills/`, {
            method: "POST",
            body: JSON.stringify(data),
        }),
    detachFromRole: (roleId: string, roleSkillId: string) =>
        apiFetch<void>(`/api/roles/${roleId}/skills/${roleSkillId}`, { method: "DELETE" }),
};

// ─── Integration Types ───────────────────────────────────────────────────────

export interface IntegrationCredentialField {
    key: string;
    label: string;
    secret: boolean;
    placeholder?: string;
}

export interface IntegrationType {
    name: string;
    description: string;
    icon: string;
    credential_fields: IntegrationCredentialField[];
    config_fields: IntegrationCredentialField[];
    tool_ids: string[];
    oauth?: boolean;
    is_extension?: boolean;
    version?: string;
    author?: string;
}

export interface Integration {
    id: string;
    type: string;
    name: string;
    agent_id: string | null;
    extra_config: Record<string, string>;
    is_active: boolean;
    has_credentials: boolean;
    created_at: string;
    updated_at: string;
}

export const integrationsApi = {
    getTypes: () => apiFetch<Record<string, IntegrationType>>("/api/integrations/types"),
    list: (params?: { agent_id?: string; type?: string }) => {
        const qs = params ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v != null) as [string, string][]).toString() : "";
        return apiFetch<Integration[]>(`/api/integrations/${qs}`);
    },
    get: (id: string) => apiFetch<Integration>(`/api/integrations/${id}`),
    create: (data: {
        type: string;
        name: string;
        agent_id?: string | null;
        credentials?: Record<string, string>;
        extra_config?: Record<string, string>;
        is_active?: boolean;
    }) => apiFetch<Integration>("/api/integrations/", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<{
        name: string;
        agent_id: string | null;
        credentials: Record<string, string>;
        extra_config: Record<string, string>;
        is_active: boolean;
    }>) => apiFetch<Integration>(`/api/integrations/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    delete: (id: string) => apiFetch<void>(`/api/integrations/${id}`, { method: "DELETE" }),
    test: (id: string) => apiFetch<{ ok: boolean; detail: string }>(`/api/integrations/${id}/test`, { method: "POST" }),
};

export const extensionsApi = {
    refresh: () => apiFetch<{ ok: boolean; extensions_loaded: number; loaded: string[]; errors: Record<string, string[]> }>(
        "/api/integrations/extensions/refresh",
        { method: "POST" },
    ),
};

// ─── Forge ───────────────────────────────────────────────────────────────────

export type ForgeStatus =
    | "queued"
    | "planning"
    | "awaiting_plan_approval"
    | "coding"
    | "testing"
    | "pr_created"
    | "completed"
    | "failed"
    | "cancelled";

export interface ForgeLogEntry {
    timestamp: string;
    event: "log" | "done" | "error";
    message: string;
}

export interface ForgePlanStep {
    file: string;
    action: "create" | "modify" | "delete";
    description: string;
}

export interface ForgePlan {
    summary: string;
    steps: ForgePlanStep[];
}

export interface ForgeTestResults {
    framework: string | null;
    exit_code: number | null;
    stdout: string;
    stderr: string;
    passed: number | null;
    failed: number | null;
    skipped: number | null;
}

export interface ForgeRequest {
    id: string;
    title: string;
    description: string;
    repo_url: string;
    branch_name: string | null;
    llm_provider: string;
    llm_model: string;
    auto_approve_plan: boolean;
    status: ForgeStatus;
    queue_position: number | null;  // position in queue when status === "queued" (1 = next)
    plan: ForgePlan | null;
    plan_feedback: { round: number; feedback: string; timestamp: string }[] | null;
    pr_url: string | null;
    pr_number: number | null;
    coding_log: ForgeLogEntry[] | null;
    test_results: ForgeTestResults | null;
    error_log: string | null;
    source_channel: string;
    creator_user_id: string | null;
    created_at: string;
    updated_at: string;
}

export const forgeApi = {
    list: (status?: ForgeStatus) => {
        const qs = status ? `?status=${status}` : "";
        return apiFetch<ForgeRequest[]>(`/api/forge/${qs}`);
    },
    get: (id: string) => apiFetch<ForgeRequest>(`/api/forge/${id}`),
    create: (data: {
        repo_url: string;
        description: string;
        llm_provider?: string;
        llm_model?: string;
        auto_approve_plan?: boolean;
    }) => apiFetch<ForgeRequest>("/api/forge/", { method: "POST", body: JSON.stringify(data) }),
    approvePlan: (id: string) =>
        apiFetch<ForgeRequest>(`/api/forge/${id}/approve-plan`, { method: "POST" }),
    requestChanges: (id: string, feedback: string) =>
        apiFetch<ForgeRequest>(`/api/forge/${id}/request-changes`, {
            method: "POST",
            body: JSON.stringify({ feedback }),
        }),
    cancel: (id: string) =>
        apiFetch<ForgeRequest>(`/api/forge/${id}/cancel`, { method: "POST" }),
    retry: (id: string) =>
        apiFetch<ForgeRequest>(`/api/forge/${id}/retry`, { method: "POST" }),
    runNow: (id: string) =>
        apiFetch<ForgeRequest>(`/api/forge/${id}/run-now`, { method: "POST" }),
    delete: (id: string) =>
        apiFetch<{ ok: boolean; id: string }>(`/api/forge/${id}`, { method: "DELETE" }),
    config: () => apiFetch<{ max_concurrent: number; default_provider: string; default_model: string; workspace_root: string }>("/api/forge/config/settings"),
};


// ─── Fleet ───────────────────────────────────────────────────────────────────

export type FleetStatus =
    | "queued"
    | "claimed"
    | "running"
    | "pushing"
    | "pr_created"
    | "failed"
    | "cancelled";

export interface FleetLogLine {
    timestamp: string;
    stream: "stdout" | "stderr" | "event";
    line: string;
}

export interface FleetDecision {
    timestamp: string;
    decision: string;
    detail: string;
}

export interface FleetJob {
    id: string;
    repo_url: string;
    issue_ref: string | null;
    title: string;
    prompt: string;
    branch_name: string | null;
    status: FleetStatus;
    triage: { reason?: string; candidate_count?: number; model?: string } | null;
    decisions: FleetDecision[] | null;
    run_log: FleetLogLine[] | null;
    claimed_by: string | null;
    claimed_at: string | null;
    pr_url: string | null;
    pr_number: number | null;
    error_log: string | null;
    created_at: string;
    updated_at: string;
}

export interface FleetWorkerHealth {
    online: boolean;
    busy?: boolean;
    version?: string;
    worker_id?: string;
    auth_ready?: boolean;
    gemini_home?: string;
    error?: string;
}

export const fleetApi = {
    list: (status?: FleetStatus) => {
        const qs = status ? `?status=${status}` : "";
        return apiFetch<FleetJob[]>(`/api/fleet/${qs}`);
    },
    get: (id: string) => apiFetch<FleetJob>(`/api/fleet/${id}`),
    create: (data: { repo_url: string; prompt: string; title?: string; issue_ref?: string }) =>
        apiFetch<FleetJob>("/api/fleet/", { method: "POST", body: JSON.stringify(data) }),
    triage: () => apiFetch<FleetJob | null>("/api/fleet/triage", { method: "POST" }),
    cancel: (id: string) =>
        apiFetch<FleetJob>(`/api/fleet/${id}/cancel`, { method: "POST" }),
    remove: (id: string) =>
        apiFetch<{ ok: boolean }>(`/api/fleet/${id}`, { method: "DELETE" }),
    workerHealth: () => apiFetch<FleetWorkerHealth>("/api/fleet/worker-health"),
    dispatch: () => apiFetch<{ dispatched: boolean }>("/api/fleet/dispatch", { method: "POST" }),
};


// ─── API Key Management ───────────────────────────────────────────────────────

export interface ApiKey {
    id: string;
    name: string;
    key_prefix: string;
    is_active: boolean;
    last_used_at: string | null;
    expires_at: string | null;
    created_at: string;
}

export interface ApiKeyCreated extends ApiKey {
    key: string;  // Full key — shown once only
}

export const apiKeysApi = {
    list: () => apiFetch<ApiKey[]>("/api/auth/api-keys"),
    create: (data: { name: string; expires_in_days?: number }) =>
        apiFetch<ApiKeyCreated>("/api/auth/api-keys", { method: "POST", body: JSON.stringify(data) }),
    revoke: (id: string) =>
        apiFetch<void>(`/api/auth/api-keys/${id}`, { method: "DELETE" }),
};


// ─── Social Pulse ─────────────────────────────────────────────────────────────

export interface SocialPulseItem {
    id: string;
    platform: string;
    category: string;
    title: string;
    url: string | null;
    description: string | null;
    metrics: {
        views?: number;
        likes?: number;
        comments?: number;
        score?: number;
        velocity?: number;
        growth_pct?: number;
        virality_score?: number;
        freshness_hours?: number;
        rank?: number;
    };
    virality_score: number;
    sentiment: string | null;
    region: string;
    niche_id: string | null;
    tags: string[];
    fetched_at: string | null;
}

export interface SocialPulseTheme {
    theme: string;
    description: string;
    virality_score: number;
    related_platforms: string[];
    keywords: string[];
}

export interface SocialPulseDashboard {
    total_trending: number;
    viral_count: number;
    active_niches: number;
    keyword_count: number;
    last_refreshed: string | null;
    by_platform: Record<string, SocialPulseItem[]>;
    top_viral: SocialPulseItem[];
}

export interface PulseNiche {
    id: string;
    name: string;
    description: string | null;
    is_active: boolean;
    is_builtin: boolean;
    google_trends_keywords: string[];
    subreddits: string[];
    youtube_category_ids: number[];
    color: string | null;
    created_at: string;
}

export interface TrendKeyword {
    id: string;
    keyword: string;
    is_active: boolean;
    platforms: string[];
    created_at: string;
}

export const socialPulseApi = {
    dashboard: (niche_id?: string, tracked_only?: boolean) => {
        const params = new URLSearchParams();
        if (niche_id) params.set("niche_id", niche_id);
        if (tracked_only) params.set("tracked_only", "true");
        return apiFetch<SocialPulseDashboard>(`/api/social-pulse/dashboard?${params.toString()}`);
    },
    trends: (params?: { platform?: string; category?: string; region?: string; niche_id?: string; tracked_only?: boolean; limit?: number }) => {
        const qs = new URLSearchParams();
        if (params?.platform) qs.set("platform", params.platform);
        if (params?.category) qs.set("category", params.category);
        if (params?.region) qs.set("region", params.region);
        if (params?.niche_id) qs.set("niche_id", params.niche_id);
        if (params?.tracked_only) qs.set("tracked_only", "true");
        if (params?.limit) qs.set("limit", String(params.limit));
        return apiFetch<SocialPulseItem[]>(`/api/social-pulse/trends?${qs.toString()}`);
    },
    niches: {
        list: () => apiFetch<PulseNiche[]>("/api/social-pulse/niches"),
        create: (data: Partial<PulseNiche>) =>
            apiFetch<{ id: string; name: string }>("/api/social-pulse/niches", {
                method: "POST",
                body: JSON.stringify(data),
            }),
        update: (id: string, data: Partial<PulseNiche>) =>
            apiFetch<{ message: string }>(`/api/social-pulse/niches/${id}`, {
                method: "PUT",
                body: JSON.stringify(data),
            }),
        delete: (id: string) =>
            apiFetch<void>(`/api/social-pulse/niches/${id}`, { method: "DELETE" }),
    },
    keywords: {
        list: () => apiFetch<TrendKeyword[]>("/api/social-pulse/keywords"),
        add: (keyword: string, platforms?: string[]) =>
            apiFetch<{ id: string; keyword: string }>("/api/social-pulse/keywords", {
                method: "POST",
                body: JSON.stringify({ keyword, platforms }),
            }),
        delete: (id: string) =>
            apiFetch<void>(`/api/social-pulse/keywords/${id}`, { method: "DELETE" }),
    },
    refresh: (region?: string) =>
        apiFetch<{ message: string }>(`/api/social-pulse/refresh${region ? `?region=${region}` : ""}`, {
            method: "POST",
        }),
    purge: () =>
        apiFetch<{ deleted: number; message: string }>("/api/social-pulse/purge", { method: "DELETE" }),
    purgeLowScore: (minScore = 60) =>
        apiFetch<{ deleted: number; message: string }>(`/api/social-pulse/purge-low-score?min_score=${minScore}`, { method: "DELETE" }),
    status: () =>
        apiFetch<Record<string, { ok: boolean; status?: number; error?: string; fix?: string; note?: string }>>("/api/social-pulse/status"),
    models: () =>
        apiFetch<{ provider: string; model: string; label: string }[]>("/api/social-pulse/models"),
    themes: (params: { niche_id?: string; provider: string; model: string }) =>
        apiFetch<SocialPulseTheme[]>("/api/social-pulse/themes", {
            method: "POST",
            body: JSON.stringify(params),
        }),
    insights: (params?: { niche_id?: string; provider?: string; model?: string; queued_titles?: string[]; tracked_keywords?: string[] }) => {
        return apiFetch<{ insights: string; items_analyzed: number; model?: string; keywords_used?: string[]; queue_size?: number }>("/api/social-pulse/insights", {
            method: "POST",
            body: JSON.stringify({
                niche_id: params?.niche_id,
                provider: params?.provider || "anthropic",
                model: params?.model || "claude-haiku-4-5-20251001",
                queued_titles: params?.queued_titles || [],
                tracked_keywords: params?.tracked_keywords || [],
            }),
        });
    },
};


// ─── Job Applications ─────────────────────────────────────────────────────────

export const JOB_APP_STATUSES = [
    "captured",
    "resume_generated",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "archived",
] as const;

export type JobAppStatus = (typeof JOB_APP_STATUSES)[number];

export interface JobApplicationPerson {
    name: string;
    title: string | null;
    profile_url: string;
    role: "hiring_manager" | "connection" | "poster" | string;
}

export interface JobApplication {
    id: string;
    job_title: string;
    company: string | null;
    location: string | null;
    salary: string | null;
    job_description: string | null;
    job_url: string | null;
    source: string;
    status: JobAppStatus;
    notes: string | null;
    tags: string[];
    resume_drive_url: string | null;
    resume_drive_file_id: string | null;
    analysis_drive_url: string | null;
    fit_score: number | null;
    review_rounds: number;
    review_log: JobApplicationReviewEntry[] | null;
    people: JobApplicationPerson[] | null;
    applied_at: string | null;
    last_status_change_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface JobApplicationReviewEntry {
    round: number;
    role: "builder" | "critic" | "system";
    agent: string;
    content: unknown; // string (builder), structured JSON (critic), or {status, message} (system)
    ts: string;
}

export interface JobApplicationStats {
    total: number;
    this_week: number;
    by_status: Record<string, number>;
    top_companies: { company: string; count: number }[];
    daily: { day: string; count: number }[];
    response_rate: number;
}

export const jobApplicationsApi = {
    list: (params?: { status?: string; company?: string; search?: string; since_days?: number }) => {
        const qs = new URLSearchParams();
        if (params?.status) qs.set("status", params.status);
        if (params?.company) qs.set("company", params.company);
        if (params?.search) qs.set("search", params.search);
        if (params?.since_days) qs.set("since_days", String(params.since_days));
        return apiFetch<JobApplication[]>(`/api/job-applications/?${qs.toString()}`);
    },
    get: (id: string) => apiFetch<JobApplication>(`/api/job-applications/${id}`),
    update: (id: string, data: Partial<JobApplication>) =>
        apiFetch<JobApplication>(`/api/job-applications/${id}`, {
            method: "PATCH",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        apiFetch<void>(`/api/job-applications/${id}`, { method: "DELETE" }),
    stats: () => apiFetch<JobApplicationStats>(`/api/job-applications/stats`),
    /** Open an SSE stream of review-loop log entries. Caller owns cleanup. */
    reviewStream: (id: string): EventSource =>
        new EventSource(`${API_BASE}/api/job-applications/${id}/review-stream`),
    /** Rerun the build → critic → revise loop. Pass reset=true to wipe prior state. */
    retryReview: (id: string, reset = false) =>
        apiFetch<{ status: string; application_id: string; reset: boolean }>(
            `/api/job-applications/${id}/retry-review?reset=${reset}`,
            { method: "POST" },
        ),
};


// ─── Job Discovery ───────────────────────────────────────────────────────────

export type JobDiscoverySource =
    | "greenhouse"
    | "lever"
    | "ashby"
    | "smartrecruiters"
    | "discovery"
    | string;

export interface JobSearchConfig {
    id: string;
    name: string;
    title_query: string;
    keywords: string[];
    exclude_keywords: string[];
    location_filter: string | null;
    lookback_hours: number;
    schedule_cron: string;
    timezone: string;
    sources_enabled: JobDiscoverySource[];
    max_results_per_run: number;
    h1b_only: boolean;
    h1b_min_tier: number;
    exclude_companies: string[];
    is_active: boolean;
    last_run_at: string | null;
    last_run_status: string | null;
    last_run_count_new: number;
    last_run_count_seen: number;
    last_run_summary: Record<string, unknown> | null;
    last_run_error: string | null;
    created_at: string;
    updated_at: string;
}

export type JobPostingStatus = "new" | "seen" | "dismissed" | "applied";

export interface JobPosting {
    id: string;
    config_id: string | null;
    source: JobDiscoverySource;
    source_company_token: string | null;
    external_id: string | null;
    job_title: string;
    company: string;
    location: string | null;
    salary: string | null;
    remote: boolean | null;
    job_url: string;
    description_snippet: string | null;
    posted_at: string | null;
    first_seen_at: string;
    last_seen_at: string;
    matched_terms: string[];
    status: JobPostingStatus;
    sponsor_tier: number | null;
    sponsor_match_method: string | null;
    no_sponsorship_signal: boolean;
    application_id: string | null;
    created_at: string;
}

export interface JobDiscoverySourceMeta {
    name: string;
    supports_server_search: boolean;
    needs_board_token: boolean;
}

export interface CompanyBoard {
    id: string;
    company_name: string;
    source: JobDiscoverySource;
    board_token: string;
    is_active: boolean;
    consecutive_failures: number;
    last_success_at: string | null;
    last_failure_reason: string | null;
    created_at: string;
    updated_at: string;
}

export interface JobDiscoveryRunSummary {
    status: string;
    config_id: string;
    new?: number;
    seen?: number;
    per_source?: Record<string, number>;
    errors?: Record<string, string>;
}

export interface H1bStats {
    total_rows: number;
    by_fiscal_year: { fiscal_year: number; count: number }[];
    default_sources: { fiscal_year: number; url: string }[];
}

export const jobDiscoveryApi = {
    listConfigs: () => apiFetch<JobSearchConfig[]>(`/api/job-discovery/configs`),
    createConfig: (data: Partial<JobSearchConfig>) =>
        apiFetch<JobSearchConfig>(`/api/job-discovery/configs`, {
            method: "POST",
            body: JSON.stringify(data),
        }),
    updateConfig: (id: string, data: Partial<JobSearchConfig>) =>
        apiFetch<JobSearchConfig>(`/api/job-discovery/configs/${id}`, {
            method: "PATCH",
            body: JSON.stringify(data),
        }),
    deleteConfig: (id: string) =>
        apiFetch<{ deleted: boolean }>(`/api/job-discovery/configs/${id}`, { method: "DELETE" }),
    runConfig: (id: string, inline = false) =>
        apiFetch<JobDiscoveryRunSummary | { status: string; config_id: string }>(
            `/api/job-discovery/configs/${id}/run?inline=${inline}`,
            { method: "POST" },
        ),

    listPostings: (params?: {
        config_id?: string;
        status?: JobPostingStatus;
        source?: string;
        since_hours?: number;
        search?: string;
        h1b_only?: boolean;
        h1b_min_tier?: number;
        limit?: number;
        offset?: number;
    }) => {
        const qs = new URLSearchParams();
        for (const [k, v] of Object.entries(params || {})) {
            if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
        }
        return apiFetch<JobPosting[]>(`/api/job-discovery/postings?${qs.toString()}`);
    },
    updatePosting: (id: string, data: { status?: JobPostingStatus }) =>
        apiFetch<JobPosting>(`/api/job-discovery/postings/${id}`, {
            method: "PATCH",
            body: JSON.stringify(data),
        }),
    applyPosting: (id: string) =>
        apiFetch<{
            status: string;
            posting_id: string;
            application_id?: string;
            deduped?: boolean;
            resume_loop_fired?: boolean;
        }>(`/api/job-discovery/postings/${id}/apply`, { method: "POST" }),

    listSources: () => apiFetch<JobDiscoverySourceMeta[]>(`/api/job-discovery/sources`),
    listBoards: () => apiFetch<CompanyBoard[]>(`/api/job-discovery/boards`),
    createBoard: (data: Omit<CompanyBoard, "id" | "consecutive_failures" | "last_success_at" | "last_failure_reason" | "created_at" | "updated_at">) =>
        apiFetch<CompanyBoard>(`/api/job-discovery/boards`, {
            method: "POST",
            body: JSON.stringify(data),
        }),
    updateBoard: (id: string, data: Partial<CompanyBoard>) =>
        apiFetch<CompanyBoard>(`/api/job-discovery/boards/${id}`, {
            method: "PATCH",
            body: JSON.stringify(data),
        }),
    deleteBoard: (id: string) =>
        apiFetch<{ deleted: boolean }>(`/api/job-discovery/boards/${id}`, { method: "DELETE" }),

    h1bStats: () => apiFetch<H1bStats>(`/api/job-discovery/h1b/stats`),
    h1bRefresh: (data?: { url?: string; fiscal_year?: number }) =>
        apiFetch<{
            status: string;
            url?: string;
            fiscal_year?: number;
            rows_seen?: number;
            employers?: number;
            written?: number;
            error?: string;
            headers?: string[];
            content_type?: string;
            sources?: { fiscal_year: number; url: string }[];
        }>(`/api/job-discovery/h1b/refresh`, {
            method: "POST",
            body: JSON.stringify(data || {}),
        }),
    h1bUpload: (file: File, fiscal_year: number) => {
        const fd = new FormData();
        fd.append("fiscal_year", String(fiscal_year));
        fd.append("file", file);
        return apiFetch<{
            status: string;
            fiscal_year?: number;
            rows_seen?: number;
            employers?: number;
            written?: number;
            error?: string;
            headers?: string[];
        }>(`/api/job-discovery/h1b/upload`, {
            method: "POST",
            body: fd,
        });
    },
};


// ─── Google Drive ─────────────────────────────────────────────────────────────

export const googleDriveApi = {
    /** List all Google Drive Integration rows (optionally scoped to an agent). */
    list: (agent_id?: string) =>
        integrationsApi.list({ type: "google_drive", ...(agent_id ? { agent_id } : {}) }),

    /** Update extra_config (e.g. default_folder_id) for a Drive integration. */
    update: (id: string, extra_config: Record<string, string>) =>
        integrationsApi.update(id, { extra_config }),

    /** Soft-delete (disconnect) a Drive integration. */
    disconnect: (id: string) => integrationsApi.delete(id),

    /** Test whether the stored credentials are still valid. */
    test: (id: string) => integrationsApi.test(id),

    /** Build the OAuth URL that initiates the Google Drive consent flow. */
    connectUrl: (agent_id?: string): string => {
        const base = `${API_BASE}/api/auth/google/login?service=drive`;
        return agent_id ? `${base}&agent_id=${agent_id}` : base;
    },

    /** Search Drive files. Passes agent_id so agent-specific credentials are preferred. Returns [] if not connected. */
    searchFiles: (q: string, agent_id?: string) => {
        const params = new URLSearchParams({ q });
        if (agent_id) params.set("agent_id", agent_id);
        return apiFetch<{ id: string; name: string; mimeType: string; modifiedTime: string }[]>(
            `/api/integrations/google-drive/files?${params}`
        );
    },

    /** Get a short-lived access token + keys for the Google Picker API. */
    getPickerToken: (agent_id?: string) => {
        const params = agent_id ? `?agent_id=${encodeURIComponent(agent_id)}` : "";
        return apiFetch<{ access_token: string; client_id: string; api_key: string }>(
            `/api/integrations/google-drive/picker-token${params}`
        );
    },

    /** Fetch metadata (name, mimeType, link) for one Drive file by id. */
    getFileMetadata: (file_id: string, agent_id?: string) => {
        const params = agent_id ? `?agent_id=${encodeURIComponent(agent_id)}` : "";
        return apiFetch<{ id: string; name: string; mimeType: string; modifiedTime: string; webViewLink: string }>(
            `/api/integrations/google-drive/file/${encodeURIComponent(file_id)}${params}`
        );
    },
};


// ─── Evolve ──────────────────────────────────────────────────────────────────

export interface EvolveSuggestion {
    id: string;
    evolve_agent_id: string | null;
    category: string;
    source: string;
    title: string;
    description: string;
    evidence: Record<string, unknown> | null;
    priority: string;
    status: string;
    approval_request_id: string | null;
    action_type: string | null;
    action_config: Record<string, unknown> | null;
    result_id: string | null;
    result_type: string | null;
    run_id: string | null;
    created_at: string;
    updated_at: string;
}

export interface EvolveRun {
    id: string;
    run_type: string;
    started_at: string | null;
    completed_at: string | null;
    status: string;
    stats: Record<string, unknown> | null;
    error_log: string | null;
    suggestions_generated: number;
    created_at: string;
}

export interface EvolveDashboard {
    health_score: number;
    suggestion_counts: Record<string, number>;
    total_suggestions: number;
    pending_count: number;
    approved_count: number;
    rejected_count: number;
    competitor_gaps: number;
    recent_runs: EvolveRun[];
}

// ─── Alert Types ────────────────────────────────────────────────────────────

export interface AlertRecord {
    id: string;
    rule_id: string | null;
    rule_type: string;
    severity: "info" | "warning" | "critical";
    status: "firing" | "acknowledged" | "resolved" | "expired";
    title: string;
    message: string;
    agent_id: string | null;
    fingerprint: string;
    context: Record<string, any> | null;
    fired_at: string | null;
    acknowledged_at: string | null;
    acknowledged_by: string | null;
    resolved_at: string | null;
    resolved_by: string | null;
    notification_sent: boolean;
    created_at: string;
}

export interface AlertRule {
    id: string;
    name: string;
    rule_type: string;
    is_active: boolean;
    severity: string;
    agent_id: string | null;
    threshold: number;
    window_minutes: number;
    cooldown_minutes: number;
    notify_webhook: boolean;
    notify_websocket: boolean;
    notify_email: string | null;
    created_at: string;
    updated_at: string;
}

export interface AlertSummary {
    firing_count: number;
    acknowledged_count: number;
    critical_count: number;
    warning_count: number;
}

export const alertsApi = {
    list: (params?: Record<string, string>) => {
        const qs = params ? `?${new URLSearchParams(params).toString()}` : "";
        return apiFetch<AlertRecord[]>(`/api/alerts/${qs}`);
    },
    get: (id: string) => apiFetch<AlertRecord>(`/api/alerts/${id}`),
    acknowledge: (id: string) => apiFetch<any>(`/api/alerts/${id}/acknowledge`, { method: "POST" }),
    resolve: (id: string) => apiFetch<any>(`/api/alerts/${id}/resolve`, { method: "POST" }),
    acknowledgeAll: () => apiFetch<any>(`/api/alerts/acknowledge-all`, { method: "POST" }),
    summary: () => apiFetch<AlertSummary>(`/api/alerts/summary`),
    listRules: () => apiFetch<AlertRule[]>(`/api/alerts/rules`),
    createRule: (data: Partial<AlertRule>) =>
        apiFetch<any>(`/api/alerts/rules`, { method: "POST", body: JSON.stringify(data) }),
    updateRule: (id: string, data: Partial<AlertRule>) =>
        apiFetch<any>(`/api/alerts/rules/${id}`, { method: "PUT", body: JSON.stringify(data) }),
    deleteRule: (id: string) => apiFetch<any>(`/api/alerts/rules/${id}`, { method: "DELETE" }),
};

// ─── LLM Purposes ───────────────────────────────────────────────────────────

export const evolveApi = {
    suggestions: (params?: { status?: string; category?: string; priority?: string }) => {
        const q = new URLSearchParams();
        if (params?.status) q.set("status", params.status);
        if (params?.category) q.set("category", params.category);
        if (params?.priority) q.set("priority", params.priority);
        const qs = q.toString();
        return apiFetch<EvolveSuggestion[]>(`/api/evolve/suggestions${qs ? `?${qs}` : ""}`);
    },
    suggestion: (id: string) => apiFetch<EvolveSuggestion>(`/api/evolve/suggestions/${id}`),
    dismiss: (id: string) => apiFetch<EvolveSuggestion>(`/api/evolve/suggestions/${id}/dismiss`, { method: "POST" }),
    runs: () => apiFetch<EvolveRun[]>("/api/evolve/runs"),
    trigger: (runType: string) => apiFetch<EvolveRun>(`/api/evolve/trigger/${runType}`, { method: "POST" }),
    dashboard: () => apiFetch<EvolveDashboard>("/api/evolve/dashboard"),
    getCompetitorRepos: () => apiFetch<{ repos: string[] }>("/api/evolve/competitor-repos"),
    updateCompetitorRepos: (repos: string[]) =>
        apiFetch<{ repos: string[] }>("/api/evolve/competitor-repos", {
            method: "PUT",
            body: JSON.stringify({ repos }),
        }),
};

// ─── Rate Limits API ─────────────────────────────────────────────────────────

export const rateLimitsApi = {
    list: () => apiFetch<ModelRateLimit[]>("/api/rate-limits"),
    create: (data: Partial<ModelRateLimit>) =>
        apiFetch<ModelRateLimit>("/api/rate-limits", {
            method: "POST",
            body: JSON.stringify(data),
        }),
    update: (id: string, data: Partial<ModelRateLimit>) =>
        apiFetch<ModelRateLimit>(`/api/rate-limits/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        apiFetch<void>(`/api/rate-limits/${id}`, { method: "DELETE" }),
    usage: () => apiFetch<RateLimitUsageEntry[]>("/api/rate-limits/usage"),
    sync: (provider: string) =>
        apiFetch<{ provider: string; synced: number; models: string[] }>(
            `/api/rate-limits/sync/${provider}`,
            { method: "POST" },
        ),
};

// ─── Purposes API ────────────────────────────────────────────────────────────

export const purposesApi = {
    list: () => apiFetch<LLMPurpose[]>("/api/purposes"),
    create: (data: Partial<LLMPurpose>) =>
        apiFetch<LLMPurpose>("/api/purposes", {
            method: "POST",
            body: JSON.stringify(data),
        }),
    get: (id: string) => apiFetch<LLMPurpose>(`/api/purposes/${id}`),
    update: (id: string, data: Partial<LLMPurpose>) =>
        apiFetch<LLMPurpose>(`/api/purposes/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        apiFetch<void>(`/api/purposes/${id}`, { method: "DELETE" }),
    status: (id: string) =>
        apiFetch<PurposeStatusResponse>(`/api/purposes/${id}/status`),
};
