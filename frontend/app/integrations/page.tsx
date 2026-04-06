"use client";

import { useState, useEffect, useCallback } from "react";
import {
    Plus, Trash2, CheckCircle, AlertCircle, Loader2, X, Eye, EyeOff,
    RefreshCw, Settings, Link2, Unlink, Search, Puzzle,
} from "lucide-react";
import { integrationsApi, extensionsApi, Integration, IntegrationType, API_BASE } from "@/lib/api";

// ─── Integration type icon mapping ───────────────────────────────────────────

const TYPE_COLORS: Record<string, string> = {
    notion: "bg-gray-900 text-white",
    linear: "bg-purple-600 text-white",
    jira: "bg-blue-600 text-white",
    slack: "bg-green-600 text-white",
    gitlab: "bg-orange-600 text-white",
    github: "bg-stone-800 text-white",
};

const TYPE_ICONS: Record<string, string> = {
    notion: "N",
    linear: "L",
    jira: "J",
    slack: "S",
    gitlab: "GL",
    github: "GH",
};

// ─── Connect / Edit Modal ─────────────────────────────────────────────────────

interface ConnectModalProps {
    typeKey: string;
    typeMeta: IntegrationType;
    existing: Integration | null;
    onClose: () => void;
    onSaved: () => void;
}

function ConnectModal({ typeKey, typeMeta, existing, onClose, onSaved }: ConnectModalProps) {
    const [name, setName] = useState(existing?.name ?? typeMeta.name);
    const [agentId, setAgentId] = useState(existing?.agent_id ?? "");
    const [creds, setCreds] = useState<Record<string, string>>({});
    const [config, setConfig] = useState<Record<string, string>>(existing?.extra_config ?? {});
    const [shown, setShown] = useState<Record<string, boolean>>({});
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    function toggleShow(key: string) {
        setShown(p => ({ ...p, [key]: !p[key] }));
    }

    async function handleSave() {
        setSaving(true);
        setError(null);
        try {
            const payload = {
                type: typeKey,
                name,
                agent_id: agentId || null,
                credentials: creds,
                extra_config: config,
                is_active: true,
            };
            if (existing) {
                await integrationsApi.update(existing.id, {
                    name,
                    agent_id: agentId || null,
                    credentials: Object.keys(creds).length > 0 ? creds : undefined,
                    extra_config: config,
                });
            } else {
                await integrationsApi.create(payload);
            }
            onSaved();
            onClose();
        } catch (e: any) {
            setError(e.message ?? "Save failed");
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-stone-200">
                    <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold ${TYPE_COLORS[typeKey] ?? "bg-stone-700 text-white"}`}>
                            {TYPE_ICONS[typeKey] ?? typeKey[0].toUpperCase()}
                        </div>
                        <div>
                            <h2 className="text-lg font-bold text-stone-900">
                                {existing ? "Edit" : "Connect"} {typeMeta.name}
                            </h2>
                            <p className="text-xs text-stone-500">{typeMeta.description}</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-stone-100 text-stone-400">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {typeMeta.oauth && !existing && (
                    <div className="p-6 border-b border-stone-100 bg-stone-50">
                        <p className="text-sm text-stone-600 mb-4">
                            This integration uses OAuth for secure authentication. You&apos;ll be redirected to Google to authorize Sutra.
                        </p>
                        <a
                            href={`${API_BASE}/api/auth/google/login?agent_id=${agentId}&service=${typeKey === "google_calendar" ? "calendar" : "drive"}`}
                            className="flex items-center justify-center gap-2 w-full py-3 bg-white border border-stone-300 rounded-xl text-stone-700 font-semibold hover:bg-stone-50 transition-colors shadow-sm"
                        >
                            <img src="https://www.gstatic.com/images/branding/product/1x/gsuite_512dp.png" className="w-5 h-5" alt="Google" />
                            Connect with Google
                        </a>
                    </div>
                )}

                <div className="flex-1 overflow-y-auto p-6 space-y-5">
                    {error && (
                        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg flex items-center gap-2">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" />
                            {error}
                        </div>
                    )}

                    {/* Display name */}
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">Display Name</label>
                        <input
                            value={name}
                            onChange={e => setName(e.target.value)}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-600"
                            placeholder="e.g. My Notion Workspace"
                        />
                    </div>

                    {/* Agent scope */}
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">
                            Agent Scope <span className="text-stone-400 font-normal">(leave blank for system-wide)</span>
                        </label>
                        <input
                            value={agentId}
                            onChange={e => setAgentId(e.target.value)}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-600 font-mono"
                            placeholder="Agent UUID"
                        />
                    </div>

                    {/* Credential fields */}
                    {typeMeta.credential_fields.length > 0 && (
                        <div>
                            <p className="text-sm font-semibold text-stone-700 mb-3">
                                Credentials
                                {existing?.has_credentials && (
                                    <span className="ml-2 text-xs font-normal text-green-600">✓ stored — enter new values to update</span>
                                )}
                            </p>
                            <div className="space-y-3">
                                {typeMeta.credential_fields.map(field => (
                                    <div key={field.key}>
                                        <label className="block text-xs font-medium text-stone-600 mb-1">{field.label}</label>
                                        <div className="relative">
                                            <input
                                                type={field.secret && !shown[field.key] ? "password" : "text"}
                                                value={creds[field.key] ?? ""}
                                                onChange={e => setCreds(p => ({ ...p, [field.key]: e.target.value }))}
                                                placeholder={existing?.has_credentials ? "••••••••" : field.placeholder}
                                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-600 pr-9"
                                            />
                                            {field.secret && (
                                                <button
                                                    type="button"
                                                    onClick={() => toggleShow(field.key)}
                                                    className="absolute right-2 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-600"
                                                >
                                                    {shown[field.key] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Config fields */}
                    {typeMeta.config_fields.length > 0 && (
                        <div>
                            <p className="text-sm font-semibold text-stone-700 mb-3">Configuration</p>
                            <div className="space-y-3">
                                {typeMeta.config_fields.map(field => (
                                    <div key={field.key}>
                                        <label className="block text-xs font-medium text-stone-600 mb-1">{field.label}</label>
                                        <input
                                            value={config[field.key] ?? ""}
                                            onChange={e => setConfig(p => ({ ...p, [field.key]: e.target.value }))}
                                            placeholder={field.placeholder}
                                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-stone-600"
                                        />
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Tool IDs info */}
                    {typeMeta.tool_ids.length > 0 && (
                        <div className="bg-stone-100 border border-stone-300 rounded-lg p-3">
                            <p className="text-xs font-semibold text-stone-700 mb-1">Enabled Tools</p>
                            <div className="flex flex-wrap gap-1">
                                {typeMeta.tool_ids.map(tid => (
                                    <span key={tid} className="text-[10px] bg-stone-200 text-stone-700 px-2 py-0.5 rounded-full font-mono">
                                        {tid}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                <div className="flex items-center justify-end gap-3 p-6 border-t border-stone-200">
                    <button onClick={onClose} className="px-4 py-2 text-sm text-stone-600 hover:text-stone-900">
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={saving || !name.trim()}
                        className="flex items-center gap-2 px-5 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50"
                    >
                        {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                        {existing ? "Save Changes" : "Connect"}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Integration card ─────────────────────────────────────────────────────────

interface IntegrationCardProps {
    integration: Integration;
    typeMeta: IntegrationType;
    onEdit: () => void;
    onDelete: () => void;
    onTest: () => void;
    testing: boolean;
    testResult: { ok: boolean; detail: string } | null;
}

function IntegrationCard({ integration, typeMeta, onEdit, onDelete, onTest, testing, testResult }: IntegrationCardProps) {
    return (
        <div className="bg-white border border-stone-200 rounded-xl p-5 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold flex-shrink-0 ${TYPE_COLORS[integration.type] ?? "bg-stone-700 text-white"}`}>
                        {TYPE_ICONS[integration.type] ?? integration.type[0].toUpperCase()}
                    </div>
                    <div>
                        <h3 className="font-semibold text-stone-900 text-sm">{integration.name}</h3>
                        <p className="text-xs text-stone-500">{typeMeta.name}</p>
                    </div>
                </div>
                <div className="flex items-center gap-1">
                    {integration.is_active ? (
                        <span className="text-[10px] bg-green-50 text-green-700 border border-green-200 px-2 py-0.5 rounded-full font-medium">Active</span>
                    ) : (
                        <span className="text-[10px] bg-stone-100 text-stone-500 border border-stone-200 px-2 py-0.5 rounded-full font-medium">Inactive</span>
                    )}
                </div>
            </div>

            {/* Scope */}
            <div className="flex items-center gap-1 mb-3">
                {integration.agent_id ? (
                    <span className="text-xs text-stone-500 flex items-center gap-1">
                        <Link2 className="w-3 h-3" /> Agent-specific
                    </span>
                ) : (
                    <span className="text-xs text-stone-400 flex items-center gap-1">
                        <Settings className="w-3 h-3" /> System-wide
                    </span>
                )}
                {integration.has_credentials && (
                    <span className="ml-2 text-xs text-green-600 flex items-center gap-0.5">
                        <CheckCircle className="w-3 h-3" /> Credentials stored
                    </span>
                )}
            </div>

            {/* Test result */}
            {testResult && (
                <div className={`text-xs px-3 py-2 rounded-lg mb-3 flex items-start gap-2 ${testResult.ok ? "bg-green-50 border border-green-200 text-green-700" : "bg-red-50 border border-red-200 text-red-700"}`}>
                    {testResult.ok ? <CheckCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" /> : <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />}
                    {testResult.detail}
                </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2 pt-2 border-t border-stone-100">
                <button
                    onClick={onTest}
                    disabled={testing || !integration.has_credentials}
                    className="flex items-center gap-1 text-xs text-stone-600 hover:text-stone-700 disabled:opacity-40"
                >
                    {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                    Test
                </button>
                <button onClick={onEdit} className="flex items-center gap-1 text-xs text-stone-600 hover:text-stone-700">
                    <Settings className="w-3.5 h-3.5" /> Edit
                </button>
                <button onClick={onDelete} className="flex items-center gap-1 text-xs text-stone-400 hover:text-red-600 ml-auto">
                    <Trash2 className="w-3.5 h-3.5" /> Remove
                </button>
            </div>
        </div>
    );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function IntegrationsPage() {
    const [types, setTypes] = useState<Record<string, IntegrationType>>({});
    const [integrations, setIntegrations] = useState<Integration[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [filterType, setFilterType] = useState("all");
    const [modal, setModal] = useState<{ typeKey: string; existing: Integration | null } | null>(null);
    const [testing, setTesting] = useState<Record<string, boolean>>({});
    const [testResults, setTestResults] = useState<Record<string, { ok: boolean; detail: string }>>({});

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [t, i] = await Promise.all([integrationsApi.getTypes(), integrationsApi.list()]);
            setTypes(t);
            setIntegrations(i);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    async function handleDelete(id: string) {
        if (!confirm("Remove this integration?")) return;
        await integrationsApi.delete(id);
        setIntegrations(prev => prev.filter(i => i.id !== id));
    }

    async function handleTest(id: string) {
        setTesting(p => ({ ...p, [id]: true }));
        try {
            const result = await integrationsApi.test(id);
            setTestResults(p => ({ ...p, [id]: result }));
        } catch (e: any) {
            setTestResults(p => ({ ...p, [id]: { ok: false, detail: e.message ?? "Test failed" } }));
        } finally {
            setTesting(p => ({ ...p, [id]: false }));
        }
    }

    const [refreshing, setRefreshing] = useState(false);

    async function handleRefreshExtensions() {
        setRefreshing(true);
        try {
            await extensionsApi.refresh();
            await load();
        } finally {
            setRefreshing(false);
        }
    }

    const typeKeys = Object.keys(types);
    const builtInKeys = typeKeys.filter(k => !types[k].is_extension);
    const extensionKeys = typeKeys.filter(k => types[k].is_extension);
    const filteredIntegrations = integrations.filter(i => {
        if (filterType !== "all" && i.type !== filterType) return false;
        if (search && !i.name.toLowerCase().includes(search.toLowerCase()) && !i.type.toLowerCase().includes(search.toLowerCase())) return false;
        return true;
    });

    return (
        <div className="flex-1 flex flex-col min-h-0 overflow-auto bg-[#F8F9FA]">
            {/* Header */}
            <div className="bg-white border-b border-stone-200 px-6 py-4">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-xl font-bold text-stone-900 flex items-center gap-2">
                            <Link2 className="w-5 h-5 text-stone-700" />
                            Integrations
                        </h1>
                        <p className="text-sm text-stone-500 mt-0.5">
                            Connect services and extensions to your agents
                        </p>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
                            <input
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                                placeholder="Search integrations..."
                                className="pl-9 pr-4 py-2 border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 w-56"
                            />
                        </div>
                    </div>
                </div>
            </div>

            <div className="flex-1 p-6 space-y-8">
                {/* Built-in integration types */}
                <section>
                    <h2 className="text-sm font-semibold text-stone-700 mb-4 uppercase tracking-wider">Built-in Integrations</h2>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                        {builtInKeys.map(typeKey => {
                            const meta = types[typeKey];
                            const count = integrations.filter(i => i.type === typeKey).length;
                            return (
                                <button
                                    key={typeKey}
                                    onClick={() => setModal({ typeKey, existing: null })}
                                    className="bg-white border border-stone-200 rounded-xl p-4 text-center hover:shadow-md hover:border-stone-400 transition-all group"
                                >
                                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold mx-auto mb-2 ${TYPE_COLORS[typeKey] ?? "bg-stone-700 text-white"}`}>
                                        {TYPE_ICONS[typeKey] ?? typeKey[0].toUpperCase()}
                                    </div>
                                    <p className="text-sm font-semibold text-stone-900 group-hover:text-stone-700">{meta.name}</p>
                                    {count > 0 && (
                                        <p className="text-[10px] text-stone-700 font-medium mt-0.5">{count} connected</p>
                                    )}
                                    <p className="text-xs text-stone-400 mt-1 line-clamp-2 hidden group-hover:block">{meta.description}</p>
                                </button>
                            );
                        })}
                    </div>
                </section>

                {/* Extensions */}
                <section>
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider flex items-center gap-2">
                            <Puzzle className="w-4 h-4" />
                            Extensions
                            {extensionKeys.length > 0 && (
                                <span className="text-xs font-normal text-stone-400 normal-case">({extensionKeys.length})</span>
                            )}
                        </h2>
                        <button
                            onClick={handleRefreshExtensions}
                            disabled={refreshing}
                            className="flex items-center gap-1.5 text-xs text-stone-500 hover:text-stone-700 px-3 py-1.5 rounded-lg border border-stone-200 hover:border-stone-400 transition-colors disabled:opacity-50"
                        >
                            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
                            Refresh
                        </button>
                    </div>
                    {extensionKeys.length === 0 ? (
                        <div className="bg-white border border-dashed border-stone-300 rounded-xl p-6 text-center">
                            <Puzzle className="w-8 h-8 text-stone-300 mx-auto mb-2" />
                            <p className="text-sm text-stone-500 font-medium">No extensions installed</p>
                            <p className="text-xs text-stone-400 mt-1">
                                Drop a Python tool file into <code className="bg-stone-100 px-1.5 py-0.5 rounded text-[10px]">backend/app/tools/extensions/</code> and click Refresh
                            </p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                            {extensionKeys.map(typeKey => {
                                const meta = types[typeKey];
                                const count = integrations.filter(i => i.type === typeKey).length;
                                return (
                                    <button
                                        key={typeKey}
                                        onClick={() => setModal({ typeKey, existing: null })}
                                        className="bg-white border border-indigo-100 rounded-xl p-4 text-center hover:shadow-md hover:border-indigo-300 transition-all group"
                                    >
                                        <div className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold mx-auto mb-2 bg-indigo-600 text-white">
                                            {TYPE_ICONS[typeKey] ?? typeKey[0].toUpperCase()}
                                        </div>
                                        <p className="text-sm font-semibold text-stone-900 group-hover:text-indigo-700">{meta.name}</p>
                                        {meta.version && (
                                            <p className="text-[10px] text-stone-400 font-mono">v{meta.version}</p>
                                        )}
                                        {count > 0 && (
                                            <p className="text-[10px] text-indigo-700 font-medium mt-0.5">{count} connected</p>
                                        )}
                                        <p className="text-xs text-stone-400 mt-1 line-clamp-2 hidden group-hover:block">{meta.description}</p>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </section>

                {/* Connected integrations */}
                <section>
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wider">
                            Connected ({filteredIntegrations.length})
                        </h2>
                        {/* Type filter tabs */}
                        <div className="flex gap-1">
                            <button
                                onClick={() => setFilterType("all")}
                                className={`text-xs px-3 py-1 rounded-full font-medium transition-colors ${filterType === "all" ? "bg-stone-700 text-white" : "text-stone-500 hover:bg-stone-100"}`}
                            >
                                All
                            </button>
                            {typeKeys.map(t => (
                                <button
                                    key={t}
                                    onClick={() => setFilterType(t)}
                                    className={`text-xs px-3 py-1 rounded-full font-medium transition-colors ${filterType === t ? "bg-stone-700 text-white" : "text-stone-500 hover:bg-stone-100"}`}
                                >
                                    {types[t]?.name ?? t}
                                </button>
                            ))}
                        </div>
                    </div>

                    {loading ? (
                        <div className="flex items-center justify-center py-16">
                            <Loader2 className="w-6 h-6 animate-spin text-stone-400" />
                        </div>
                    ) : filteredIntegrations.length === 0 ? (
                        <div className="text-center py-16 bg-white border border-dashed border-stone-300 rounded-xl">
                            <Unlink className="w-10 h-10 text-stone-300 mx-auto mb-3" />
                            <p className="text-stone-500 font-medium">No integrations connected</p>
                            <p className="text-stone-400 text-sm mt-1">Click a service above to connect it</p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {filteredIntegrations.map(integration => {
                                const meta = types[integration.type];
                                if (!meta) return null;
                                return (
                                    <IntegrationCard
                                        key={integration.id}
                                        integration={integration}
                                        typeMeta={meta}
                                        onEdit={() => setModal({ typeKey: integration.type, existing: integration })}
                                        onDelete={() => handleDelete(integration.id)}
                                        onTest={() => handleTest(integration.id)}
                                        testing={testing[integration.id] ?? false}
                                        testResult={testResults[integration.id] ?? null}
                                    />
                                );
                            })}
                        </div>
                    )}
                </section>
            </div>

            {/* Modal */}
            {modal && types[modal.typeKey] && (
                <ConnectModal
                    typeKey={modal.typeKey}
                    typeMeta={types[modal.typeKey]}
                    existing={modal.existing}
                    onClose={() => setModal(null)}
                    onSaved={load}
                />
            )}
        </div>
    );
}
