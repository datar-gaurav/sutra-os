"use client";

import { useEffect, useState } from "react";
import {
    Key,
    Server,
    Save,
    Plus,
    Trash2,
    CheckCircle2,
    XCircle,
    RefreshCw,
    Copy,
    Terminal,
    Settings2,
    RotateCcw,
} from "lucide-react";
import {
    llmsApi, apiKeysApi, systemSettingsApi, envVarsApi,
    type LLMProvider, type OllamaModel, type ApiKey, type ApiKeyCreated,
    type SystemSettingSchema, type EnvVarItem,
} from "@/lib/api";
import { Eye, EyeOff, Database } from "lucide-react";

// ── Group display order & icons ────────────────────────────────────────────

const GROUP_ORDER = ["Resilience", "Watchdog", "Cache", "Conversation", "Memory", "Embeddings", "Rate Limits"];
const ENV_GROUP_ORDER = ["Infrastructure", "Security", "LLM API Keys", "Integrations", "Email (SMTP)", "Scheduler", "Agent Tools"];

export default function SettingsPage() {
    const [providers, setProviders] = useState<LLMProvider[]>([]);
    const [ollamaModels, setOllamaModels] = useState<OllamaModel[]>([]);
    const [ollamaConnected, setOllamaConnected] = useState(false);
    const [loading, setLoading] = useState(true);

    // New provider form
    const [showAddForm, setShowAddForm] = useState(false);
    const [newProviderName, setNewProviderName] = useState("");
    const [newProviderType, setNewProviderType] = useState("openai");
    const [newApiKey, setNewApiKey] = useState("");
    const [newSupportsTools, setNewSupportsTools] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);

    // API Keys state
    const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
    const [showCreateKey, setShowCreateKey] = useState(false);
    const [newKeyName, setNewKeyName] = useState("");
    const [newKeyExpiry, setNewKeyExpiry] = useState<string>("");
    const [creatingKey, setCreatingKey] = useState(false);
    const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null);
    const [copiedKey, setCopiedKey] = useState(false);

    // System settings state
    const [sysSchema, setSysSchema] = useState<Record<string, SystemSettingSchema>>({});
    const [sysEdits, setSysEdits] = useState<Record<string, any>>({});
    const [savingSys, setSavingSys] = useState(false);
    const [sysSaved, setSysSaved] = useState(false);

    // Environment variables state
    const [envVars, setEnvVars] = useState<EnvVarItem[]>([]);
    const [envEdits, setEnvEdits] = useState<Record<string, string>>({}); // key → plaintext being typed
    const [envRevealed, setEnvRevealed] = useState<Record<string, boolean>>({});
    const [savingEnv, setSavingEnv] = useState<Record<string, boolean>>({}); // per-key saving state
    const [savedEnv, setSavedEnv] = useState<Record<string, boolean>>({});
    const [savingAllEnv, setSavingAllEnv] = useState(false);

    useEffect(() => {
        loadSettings();
    }, []);

    async function loadSettings() {
        try {
            const [providerList, models, status, keys, sysSettings, envList] = await Promise.all([
                llmsApi.list().catch(() => []),
                llmsApi.ollamaModels().catch(() => []),
                llmsApi.ollamaStatus().catch(() => ({ connected: false })),
                apiKeysApi.list().catch(() => []),
                systemSettingsApi.get().catch(() => ({})),
                envVarsApi.list().catch(() => []),
            ]);
            setProviders(providerList);
            setOllamaModels(models);
            setOllamaConnected(status.connected);
            setApiKeys(keys);
            setSysSchema(sysSettings);
            setEnvVars(envList);
        } catch (err) {
            console.error("Failed to load settings:", err);
        } finally {
            setLoading(false);
        }
    }

    // ── Provider handlers ──────────────────────────────────────────────────

    async function handleAddProvider(e: React.FormEvent) {
        e.preventDefault();
        if (!newProviderName.trim()) return;
        setSaving(true);
        setSaveError(null);
        try {
            await llmsApi.create({
                name: newProviderName.trim(),
                provider_type: newProviderType,
                api_key: newApiKey || undefined,
                supports_tool_calling: newSupportsTools,
            });
            setNewProviderName("");
            setNewProviderType("openai");
            setNewApiKey("");
            setNewSupportsTools(true);
            setShowAddForm(false);
            await loadSettings();
        } catch (err: any) {
            console.error("Failed to add provider:", err);
            setSaveError(err?.message || "Failed to save provider");
        } finally {
            setSaving(false);
        }
    }

    async function handleDeleteProvider(id: string) {
        if (!confirm("Delete this provider?")) return;
        try {
            await llmsApi.delete(id);
            await loadSettings();
        } catch (err) {
            console.error("Failed to delete provider:", err);
        }
    }

    // ── API Key handlers ───────────────────────────────────────────────────

    async function handleCreateApiKey(e: React.FormEvent) {
        e.preventDefault();
        if (!newKeyName.trim()) return;
        setCreatingKey(true);
        try {
            const created = await apiKeysApi.create({
                name: newKeyName.trim(),
                expires_in_days: newKeyExpiry ? parseInt(newKeyExpiry) : undefined,
            });
            setCreatedKey(created);
            setApiKeys(prev => [created, ...prev]);
            setNewKeyName("");
            setNewKeyExpiry("");
            setShowCreateKey(false);
        } catch (err) {
            console.error("Failed to create API key:", err);
        } finally {
            setCreatingKey(false);
        }
    }

    async function handleRevokeApiKey(id: string) {
        if (!confirm("Revoke this API key? It cannot be undone.")) return;
        await apiKeysApi.revoke(id);
        setApiKeys(prev => prev.map(k => k.id === id ? { ...k, is_active: false } : k));
    }

    function handleCopyKey() {
        if (createdKey) {
            navigator.clipboard.writeText(createdKey.key);
            setCopiedKey(true);
            setTimeout(() => setCopiedKey(false), 2000);
        }
    }

    // ── System settings handlers ───────────────────────────────────────────

    function handleSysChange(key: string, value: any) {
        setSysEdits(prev => ({ ...prev, [key]: value }));
        setSysSaved(false);
    }

    async function handleSaveSysSettings() {
        if (Object.keys(sysEdits).length === 0) return;
        setSavingSys(true);
        try {
            await systemSettingsApi.update(sysEdits);
            setSysEdits({});
            setSysSaved(true);
            setTimeout(() => setSysSaved(false), 3000);
            // Reload to get fresh values
            const fresh = await systemSettingsApi.get();
            setSysSchema(fresh);
        } catch (err) {
            console.error("Failed to save system settings:", err);
        } finally {
            setSavingSys(false);
        }
    }

    async function handleResetSysSettings() {
        if (!confirm("Reset all system settings to defaults? This removes all customizations.")) return;
        try {
            await systemSettingsApi.reset();
            setSysEdits({});
            const fresh = await systemSettingsApi.get();
            setSysSchema(fresh);
        } catch (err) {
            console.error("Failed to reset settings:", err);
        }
    }

    // ── Env var handlers ───────────────────────────────────────────────────

    function handleEnvEdit(key: string, value: string) {
        setEnvEdits(prev => ({ ...prev, [key]: value }));
    }

    async function handleSaveEnvVar(key: string) {
        const value = envEdits[key];
        if (value === undefined || value === "") return;
        setSavingEnv(prev => ({ ...prev, [key]: true }));
        try {
            const updated = await envVarsApi.upsert([{ key, value }]);
            setEnvVars(updated);
            setEnvEdits(prev => { const n = { ...prev }; delete n[key]; return n; });
            setSavedEnv(prev => ({ ...prev, [key]: true }));
            setTimeout(() => setSavedEnv(prev => { const n = { ...prev }; delete n[key]; return n; }), 2500);
        } catch (err: any) {
            console.error("Failed to save env var:", err);
        } finally {
            setSavingEnv(prev => { const n = { ...prev }; delete n[key]; return n; });
        }
    }

    async function handleSaveAllEnvVars() {
        const toSave = Object.entries(envEdits).filter(([, v]) => v !== "");
        if (toSave.length === 0) return;
        setSavingAllEnv(true);
        try {
            const updated = await envVarsApi.upsert(toSave.map(([key, value]) => ({ key, value })));
            setEnvVars(updated);
            setEnvEdits({});
        } catch (err: any) {
            console.error("Failed to save env vars:", err);
        } finally {
            setSavingAllEnv(false);
        }
    }

    async function handleClearEnvVar(key: string) {
        if (!confirm(`Clear stored value for ${key}? It will revert to the .env file or process environment.`)) return;
        try {
            await envVarsApi.delete(key);
            setEnvVars(prev => prev.map(v => v.key === key ? { ...v, is_set: false, masked_value: "", source: "env" } : v));
            setEnvEdits(prev => { const n = { ...prev }; delete n[key]; return n; });
        } catch (err: any) {
            console.error("Failed to clear env var:", err);
        }
    }

    // Group env vars by category
    const envByGroup: Record<string, EnvVarItem[]> = {};
    for (const v of envVars) {
        if (!envByGroup[v.group]) envByGroup[v.group] = [];
        envByGroup[v.group].push(v);
    }
    const sortedEnvGroups = ENV_GROUP_ORDER.filter(g => envByGroup[g]);
    const pendingEnvEdits = Object.entries(envEdits).filter(([, v]) => v !== "").length;

    // Group settings by category
    const settingsByGroup: Record<string, [string, SystemSettingSchema][]> = {};
    for (const [key, schema] of Object.entries(sysSchema)) {
        const group = schema.group || "Other";
        if (!settingsByGroup[group]) settingsByGroup[group] = [];
        settingsByGroup[group].push([key, schema]);
    }
    const sortedGroups = GROUP_ORDER.filter(g => settingsByGroup[g]);

    const hasEdits = Object.keys(sysEdits).length > 0;

    return (
        <div className="max-w-3xl mx-auto space-y-8 animate-fade-in">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Settings</h1>
                <p className="text-gray-500 dark:text-gray-400 mt-1">
                    Manage LLM providers, API keys, and system configuration
                </p>
            </div>

            {/* Ollama Status */}
            <div className="glass-card p-6">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Server className="w-5 h-5 text-stone-600" />
                        Ollama (Local LLM)
                    </h2>
                    <div className="flex items-center gap-2">
                        {ollamaConnected ? (
                            <>
                                <CheckCircle2 className="w-4 h-4 text-accent-success" />
                                <span className="text-sm text-accent-success">Connected</span>
                            </>
                        ) : (
                            <>
                                <XCircle className="w-4 h-4 text-accent-error" />
                                <span className="text-sm text-accent-error">Not Connected</span>
                            </>
                        )}
                        <button onClick={loadSettings} className="btn-icon">
                            <RefreshCw className="w-4 h-4" />
                        </button>
                    </div>
                </div>

                {ollamaConnected && ollamaModels.length > 0 ? (
                    <div className="space-y-2">
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
                            {ollamaModels.length} model{ollamaModels.length !== 1 ? "s" : ""} available
                        </p>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            {ollamaModels.map((model) => (
                                <div
                                    key={model.name}
                                    className="flex items-center justify-between p-3 rounded-xl bg-surface-1 dark:bg-surface-dark2 border border-gray-200 dark:border-gray-700"
                                >
                                    <div>
                                        <p className="text-sm font-medium font-mono text-gray-900 dark:text-white">
                                            {model.name}
                                        </p>
                                        <p className="text-xs text-gray-400">{model.size}</p>
                                    </div>
                                    <div className="status-dot status-dot-running" />
                                </div>
                            ))}
                        </div>
                    </div>
                ) : ollamaConnected ? (
                    <p className="text-sm text-gray-400">
                        Connected but no models pulled yet. Run{" "}
                        <code className="px-1.5 py-0.5 bg-surface-2 dark:bg-surface-dark3 rounded text-stone-600 text-xs">
                            ollama pull llama3
                        </code>{" "}
                        to get started.
                    </p>
                ) : (
                    <p className="text-sm text-gray-400">
                        Ollama is not running. Start it with{" "}
                        <code className="px-1.5 py-0.5 bg-surface-2 dark:bg-surface-dark3 rounded text-stone-600 text-xs">
                            ollama serve
                        </code>
                    </p>
                )}
            </div>

            {/* API Key Providers */}
            <div className="glass-card p-6">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Key className="w-5 h-5 text-amber-500" />
                        API Key Providers
                    </h2>
                    <button
                        onClick={() => setShowAddForm(!showAddForm)}
                        className="btn-secondary flex items-center gap-1.5 text-sm"
                    >
                        <Plus className="w-4 h-4" />
                        Add Provider
                    </button>
                </div>

                {showAddForm && (
                    <form
                        onSubmit={handleAddProvider}
                        className="mb-4 p-4 rounded-xl border border-stone-300 dark:border-stone-700 bg-stone-100/50 dark:bg-stone-900/20 space-y-3 animate-slide-up"
                    >
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div>
                                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Display Name</label>
                                <input type="text" value={newProviderName} onChange={(e) => setNewProviderName(e.target.value)} className="input text-sm" placeholder="e.g., My OpenAI Key" required />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Provider</label>
                                <select value={newProviderType} onChange={(e) => {
                                    setNewProviderType(e.target.value);
                                    setNewSupportsTools(e.target.value !== "perplexity");
                                }} className="input text-sm">
                                    <option value="openai">OpenAI</option>
                                    <option value="anthropic">Anthropic</option>
                                    <option value="google">Google Gemini</option>
                                    <option value="openrouter">OpenRouter</option>
                                    <option value="perplexity">Perplexity</option>
                                    <option value="groq">Groq</option>
                                    <option value="clod">Clod.io</option>
                                    <option value="custom">Custom</option>
                                </select>
                            </div>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">API Key</label>
                            <input type="password" value={newApiKey} onChange={(e) => setNewApiKey(e.target.value)} className="input text-sm font-mono" placeholder="sk-..." />
                        </div>
                        <label className="flex items-center gap-2 cursor-pointer select-none">
                            <input
                                type="checkbox"
                                checked={newSupportsTools}
                                onChange={(e) => setNewSupportsTools(e.target.checked)}
                                className="w-4 h-4 rounded accent-stone-600"
                            />
                            <span className="text-xs text-gray-600 dark:text-gray-300">Supports tool calling</span>
                        </label>
                        {saveError && (
                            <p className="text-xs text-red-500 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">{saveError}</p>
                        )}
                        <div className="flex justify-end gap-2">
                            <button type="button" onClick={() => { setShowAddForm(false); setSaveError(null); }} className="btn-secondary text-sm">Cancel</button>
                            <button type="submit" disabled={saving} className="btn-primary text-sm flex items-center gap-1.5">
                                <Save className="w-3.5 h-3.5" />
                                {saving ? "Saving..." : "Save"}
                            </button>
                        </div>
                    </form>
                )}

                {providers.length === 0 ? (
                    <p className="text-sm text-gray-400 py-4 text-center">No API key providers configured.</p>
                ) : (
                    <div className="space-y-2">
                        {providers.map((provider) => (
                            <div key={provider.id} className="flex items-center justify-between p-3 rounded-xl bg-surface-1 dark:bg-surface-dark2 border border-gray-200 dark:border-gray-700">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center text-white font-bold text-sm">
                                        {provider.provider_type.charAt(0).toUpperCase()}
                                    </div>
                                    <div>
                                        <p className="text-sm font-medium text-gray-900 dark:text-white">{provider.name}</p>
                                        <div className="flex items-center gap-2 mt-0.5">
                                            <span className="text-xs text-gray-400 capitalize">{provider.provider_type}</span>
                                            {provider.has_api_key && (
                                                <span className="text-xs text-accent-success flex items-center gap-1">
                                                    <CheckCircle2 className="w-3 h-3" /> Key set
                                                </span>
                                            )}
                                            <span className={`text-xs flex items-center gap-1 ${provider.supports_tool_calling ? "text-blue-500" : "text-gray-400"}`}>
                                                {provider.supports_tool_calling ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                                                {provider.supports_tool_calling ? "Tools" : "No tools"}
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <button
                                        title={provider.supports_tool_calling ? "Disable tool calling" : "Enable tool calling"}
                                        onClick={async () => {
                                            await llmsApi.update(provider.id, { supports_tool_calling: !provider.supports_tool_calling });
                                            await loadSettings();
                                        }}
                                        className={`text-xs px-2 py-1 rounded-lg border transition-colors ${provider.supports_tool_calling ? "border-blue-300 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20" : "border-gray-300 text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"}`}
                                    >
                                        {provider.supports_tool_calling ? "Tools on" : "Tools off"}
                                    </button>
                                    <button onClick={() => handleDeleteProvider(provider.id)} className="btn-icon text-gray-400 hover:text-red-500">
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Programmatic API Keys */}
            <div className="glass-card p-6">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Terminal className="w-5 h-5 text-stone-600" />
                        Programmatic API Keys
                    </h2>
                    <button onClick={() => setShowCreateKey(!showCreateKey)} className="btn-secondary flex items-center gap-1.5 text-sm">
                        <Plus className="w-4 h-4" /> New Key
                    </button>
                </div>
                <p className="text-xs text-gray-400 mb-4">
                    Use <code className="px-1 py-0.5 bg-surface-2 dark:bg-surface-dark3 rounded text-stone-600">sk-sutra_...</code> keys
                    as Bearer tokens to authenticate API requests programmatically.
                </p>

                {showCreateKey && (
                    <form onSubmit={handleCreateApiKey} className="mb-4 p-4 rounded-xl border border-stone-300 dark:border-stone-700 bg-stone-100/50 dark:bg-stone-900/20 space-y-3">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div>
                                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Key Name</label>
                                <input type="text" value={newKeyName} onChange={e => setNewKeyName(e.target.value)} className="input text-sm" placeholder="e.g. CI/CD pipeline" required />
                            </div>
                            <div>
                                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">Expires in</label>
                                <select value={newKeyExpiry} onChange={e => setNewKeyExpiry(e.target.value)} className="input text-sm">
                                    <option value="">Never</option>
                                    <option value="30">30 days</option>
                                    <option value="90">90 days</option>
                                    <option value="180">180 days</option>
                                    <option value="365">1 year</option>
                                </select>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2">
                            <button type="button" onClick={() => setShowCreateKey(false)} className="btn-secondary text-sm">Cancel</button>
                            <button type="submit" disabled={creatingKey} className="btn-primary text-sm flex items-center gap-1.5">
                                <Save className="w-3.5 h-3.5" />
                                {creatingKey ? "Creating..." : "Create Key"}
                            </button>
                        </div>
                    </form>
                )}

                {createdKey && (
                    <div className="mb-4 p-4 rounded-xl border border-green-200 bg-green-50 dark:bg-green-950/20 dark:border-green-800">
                        <p className="text-xs font-semibold text-green-700 dark:text-green-400 mb-2">
                            Key created! Copy it now — it won&apos;t be shown again.
                        </p>
                        <div className="flex items-center gap-2">
                            <code className="flex-1 text-xs font-mono bg-white dark:bg-surface-dark3 border border-green-200 dark:border-green-700 rounded px-3 py-2 break-all text-stone-700 dark:text-stone-200">
                                {createdKey.key}
                            </code>
                            <button onClick={handleCopyKey} className="p-2 rounded-lg border border-green-200 bg-white hover:bg-green-50 text-green-700 flex-shrink-0" title="Copy to clipboard">
                                {copiedKey ? <CheckCircle2 className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                            </button>
                        </div>
                        <button onClick={() => setCreatedKey(null)} className="mt-2 text-xs text-green-600 hover:underline">
                            I&apos;ve saved it — dismiss
                        </button>
                    </div>
                )}

                {apiKeys.length === 0 ? (
                    <p className="text-sm text-gray-400 py-4 text-center">No API keys yet.</p>
                ) : (
                    <div className="space-y-2">
                        {apiKeys.map(k => (
                            <div key={k.id} className={`flex items-center justify-between p-3 rounded-xl border ${k.is_active ? "bg-surface-1 dark:bg-surface-dark2 border-gray-200 dark:border-gray-700" : "bg-gray-50 dark:bg-surface-dark1 border-gray-100 dark:border-gray-800 opacity-60"}`}>
                                <div className="flex items-center gap-3">
                                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${k.is_active ? "bg-stone-200 text-stone-700" : "bg-gray-200 text-gray-500"}`}>
                                        <Key className="w-4 h-4" />
                                    </div>
                                    <div>
                                        <p className="text-sm font-medium text-gray-900 dark:text-white">{k.name}</p>
                                        <div className="flex items-center gap-2 mt-0.5">
                                            <code className="text-xs text-gray-400 font-mono">{k.key_prefix}...</code>
                                            {k.expires_at && <span className="text-xs text-gray-400">Expires {new Date(k.expires_at).toLocaleDateString()}</span>}
                                            {k.last_used_at && <span className="text-xs text-gray-400">Last used {new Date(k.last_used_at).toLocaleDateString()}</span>}
                                            {!k.is_active && <span className="text-xs text-red-400">Revoked</span>}
                                        </div>
                                    </div>
                                </div>
                                {k.is_active && (
                                    <button onClick={() => handleRevokeApiKey(k.id)} className="btn-icon text-gray-400 hover:text-red-500" title="Revoke key">
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* System Configuration */}
            {sortedGroups.length > 0 && (
                <div className="glass-card p-6">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                            <Settings2 className="w-5 h-5 text-stone-600" />
                            System Configuration
                        </h2>
                        <div className="flex items-center gap-2">
                            {sysSaved && (
                                <span className="text-xs text-green-600 flex items-center gap-1">
                                    <CheckCircle2 className="w-3.5 h-3.5" /> Saved
                                </span>
                            )}
                            <button
                                onClick={handleResetSysSettings}
                                className="btn-secondary flex items-center gap-1.5 text-xs"
                                title="Reset all to defaults"
                            >
                                <RotateCcw className="w-3.5 h-3.5" />
                                Reset
                            </button>
                            <button
                                onClick={handleSaveSysSettings}
                                disabled={!hasEdits || savingSys}
                                className="btn-primary text-xs flex items-center gap-1.5 disabled:opacity-50"
                            >
                                <Save className="w-3.5 h-3.5" />
                                {savingSys ? "Saving..." : "Save Changes"}
                            </button>
                        </div>
                    </div>
                    <p className="text-xs text-gray-400 mb-5">
                        Tune resilience, caching, memory, rate limits, and other runtime parameters. Changes take effect immediately.
                    </p>

                    <div className="space-y-6">
                        {sortedGroups.map(group => (
                            <div key={group}>
                                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 uppercase tracking-wider">
                                    {group}
                                </h3>
                                <div className="space-y-3">
                                    {settingsByGroup[group].map(([key, schema]) => {
                                        const currentValue = key in sysEdits ? sysEdits[key] : schema.value;
                                        const isEdited = key in sysEdits;

                                        return (
                                            <div key={key} className="flex items-center gap-4 py-2">
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <label className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                                            {schema.label}
                                                        </label>
                                                        {schema.is_overridden && !isEdited && (
                                                            <span className="text-[10px] px-1.5 py-0.5 bg-blue-100 text-blue-600 rounded-full font-medium">
                                                                customized
                                                            </span>
                                                        )}
                                                        {isEdited && (
                                                            <span className="text-[10px] px-1.5 py-0.5 bg-amber-100 text-amber-600 rounded-full font-medium">
                                                                unsaved
                                                            </span>
                                                        )}
                                                    </div>
                                                    <p className="text-xs text-gray-400 mt-0.5">{schema.description}</p>
                                                </div>
                                                <div className="w-40 flex-shrink-0">
                                                    {schema.type === "int" || schema.type === "float" ? (
                                                        <input
                                                            type="number"
                                                            value={currentValue ?? ""}
                                                            onChange={e => handleSysChange(key, schema.type === "int" ? parseInt(e.target.value) : parseFloat(e.target.value))}
                                                            min={schema.min}
                                                            max={schema.max}
                                                            step={schema.type === "float" ? 0.1 : 1}
                                                            className="w-full px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-surface-dark2 focus:outline-none focus:ring-2 focus:ring-stone-900 text-right font-mono"
                                                        />
                                                    ) : (
                                                        <input
                                                            type="text"
                                                            value={currentValue ?? ""}
                                                            onChange={e => handleSysChange(key, e.target.value)}
                                                            className="w-full px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-surface-dark2 focus:outline-none focus:ring-2 focus:ring-stone-900 font-mono"
                                                        />
                                                    )}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
            {/* Environment Variables */}
            <div className="glass-card p-6">
                <div className="flex items-center justify-between mb-2">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Database className="w-5 h-5 text-indigo-500" />
                        Environment Variables
                    </h2>
                    {pendingEnvEdits > 0 && (
                        <button
                            onClick={handleSaveAllEnvVars}
                            disabled={savingAllEnv}
                            className="btn-primary text-xs flex items-center gap-1.5 disabled:opacity-50"
                        >
                            <Save className="w-3.5 h-3.5" />
                            {savingAllEnv ? "Saving..." : `Save ${pendingEnvEdits} change${pendingEnvEdits > 1 ? "s" : ""}`}
                        </button>
                    )}
                </div>
                <p className="text-xs text-gray-400 mb-5">
                    Secrets are encrypted (AES-256) before storage and never returned as plaintext.
                    Values set here override the <code className="px-1 py-0.5 bg-surface-2 dark:bg-surface-dark3 rounded text-stone-600">.env</code> file at runtime.
                </p>

                <div className="space-y-8">
                    {sortedEnvGroups.map(group => (
                        <div key={group}>
                            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 uppercase tracking-wider border-b border-gray-100 dark:border-gray-800 pb-1.5">
                                {group}
                            </h3>
                            <div className="space-y-3">
                                {envByGroup[group].map(envVar => {
                                    const editVal = envEdits[envVar.key];
                                    const isEditing = editVal !== undefined;
                                    const isRevealed = envRevealed[envVar.key];
                                    const isSaving = savingEnv[envVar.key];
                                    const justSaved = savedEnv[envVar.key];

                                    return (
                                        <div key={envVar.key} className="grid grid-cols-[1fr_auto] gap-3 items-start py-2">
                                            {/* Label + description */}
                                            <div className="min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <label className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                                        {envVar.label}
                                                    </label>
                                                    {/* Source badge */}
                                                    {envVar.source === "db" && (
                                                        <span className="text-[10px] px-1.5 py-0.5 bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300 rounded-full font-medium">DB</span>
                                                    )}
                                                    {envVar.source === "env" && (
                                                        <span className="text-[10px] px-1.5 py-0.5 bg-stone-100 text-stone-500 rounded-full font-medium">.env</span>
                                                    )}
                                                    {envVar.is_secret && (
                                                        <span className="text-[10px] px-1.5 py-0.5 bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 rounded-full font-medium">🔒 secret</span>
                                                    )}
                                                    {isEditing && (
                                                        <span className="text-[10px] px-1.5 py-0.5 bg-amber-100 text-amber-600 rounded-full font-medium">unsaved</span>
                                                    )}
                                                    {justSaved && (
                                                        <span className="text-[10px] px-1.5 py-0.5 bg-green-100 text-green-700 rounded-full font-medium flex items-center gap-0.5">
                                                            <CheckCircle2 className="w-2.5 h-2.5" /> saved
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-gray-400 mt-0.5">{envVar.description}</p>
                                                <code className="text-[10px] text-gray-300 dark:text-gray-600 font-mono">{envVar.key}</code>
                                            </div>

                                            {/* Input + actions */}
                                            <div className="flex items-center gap-1.5 flex-shrink-0">
                                                <div className="relative">
                                                    <input
                                                        type={envVar.is_secret && !isRevealed ? "password" : "text"}
                                                        value={isEditing ? editVal : (envVar.is_secret ? envVar.masked_value : envVar.masked_value)}
                                                        onChange={e => handleEnvEdit(envVar.key, e.target.value)}
                                                        placeholder={envVar.is_set ? (envVar.is_secret ? "Enter new value to update" : "") : envVar.placeholder}
                                                        className="w-60 px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-sm bg-white dark:bg-surface-dark2 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono pr-8"
                                                        readOnly={!isEditing && envVar.is_secret && envVar.is_set}
                                                        onClick={() => {
                                                            // Click on a set secret field starts editing
                                                            if (envVar.is_secret && envVar.is_set && !isEditing) {
                                                                handleEnvEdit(envVar.key, "");
                                                            }
                                                        }}
                                                    />
                                                    {envVar.is_secret && (
                                                        <button
                                                            type="button"
                                                            onClick={() => setEnvRevealed(prev => ({ ...prev, [envVar.key]: !isRevealed }))}
                                                            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                                                            title={isRevealed ? "Hide" : "Show masked value"}
                                                        >
                                                            {isRevealed ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                                                        </button>
                                                    )}
                                                </div>
                                                {/* Save button — only when editing */}
                                                {isEditing && editVal !== "" && (
                                                    <button
                                                        onClick={() => handleSaveEnvVar(envVar.key)}
                                                        disabled={isSaving}
                                                        className="p-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
                                                        title="Save"
                                                    >
                                                        {isSaving ? (
                                                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                                        ) : (
                                                            <Save className="w-3.5 h-3.5" />
                                                        )}
                                                    </button>
                                                )}
                                                {/* Clear button — only when a DB value is stored */}
                                                {envVar.source === "db" && !isEditing && (
                                                    <button
                                                        onClick={() => handleClearEnvVar(envVar.key)}
                                                        className="p-1.5 rounded-lg border border-gray-200 text-gray-400 hover:text-red-500 hover:border-red-200"
                                                        title="Clear stored value (revert to .env)"
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" />
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
