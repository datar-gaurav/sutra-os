"use client";

import { useState, useEffect } from "react";
import {
    Mail,
    Plus,
    Trash2,
    Edit2,
    Check,
    X,
    ShieldCheck,
    Server,
    Eye,
    EyeOff,
    SendHorizonal,
    Loader2,
    AlertCircle,
    CheckCircle,
} from "lucide-react";
import { emailApi, agentsApi, EmailConfig, EmailWhitelistEntry, Agent } from "@/lib/api";

type Tab = "configs" | "whitelist";

function Badge({ active }: { active: boolean }) {
    return (
        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
            {active ? "Active" : "Inactive"}
        </span>
    );
}

// ─── Config Form ──────────────────────────────────────────────────────────────

interface ConfigFormProps {
    initial?: Partial<EmailConfig & { smtp_password?: string }>;
    agents: Agent[];
    onSave: (data: Record<string, unknown>) => Promise<void>;
    onCancel: () => void;
}

function ConfigForm({ initial, agents, onSave, onCancel }: ConfigFormProps) {
    const [form, setForm] = useState({
        agent_id: initial?.agent_id ?? "",
        label: initial?.label ?? "",
        provider: initial?.provider ?? "SMTP",
        google_email: initial?.google_email ?? "",
        smtp_host: initial?.smtp_host ?? "",
        smtp_port: initial?.smtp_port ?? 587,
        smtp_username: initial?.smtp_username ?? "",
        smtp_password: "",
        smtp_from_email: initial?.smtp_from_email ?? "",
        smtp_from_name: initial?.smtp_from_name ?? "",
        smtp_use_tls: initial?.smtp_use_tls ?? true,
        smtp_use_ssl: initial?.smtp_use_ssl ?? false,
        imap_host: initial?.imap_host ?? "",
        imap_port: initial?.imap_port ?? 993,
        imap_username: initial?.imap_username ?? "",
        imap_password: "",
        imap_use_ssl: initial?.imap_use_ssl ?? true,
        imap_folder: initial?.imap_folder ?? "INBOX",
    });
    const [showSmtpPass, setShowSmtpPass] = useState(false);
    const [showImapPass, setShowImapPass] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    const set = (k: string, v: unknown) => setForm(f => ({ ...f, [k]: v }));

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setSaving(true);
        setError("");
        try {
            const payload: Record<string, unknown> = { ...form };
            payload.agent_id = form.agent_id || null;
            if (!payload.smtp_password) delete payload.smtp_password;
            if (!payload.imap_password) delete payload.imap_password;
            await onSave(payload);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setSaving(false);
        }
    }

    return (
        <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
                <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    {error}
                </div>
            )}

            <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Scope</label>
                    <select
                        value={form.agent_id}
                        onChange={e => set("agent_id", e.target.value)}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                    >
                        <option value="">System Default (all agents)</option>
                        {agents.map(a => (
                            <option key={a.id} value={a.id}>{a.name}</option>
                        ))}
                    </select>
                </div>

                <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Label (optional)</label>
                    <input
                        value={form.label}
                        onChange={e => set("label", e.target.value)}
                        placeholder="e.g. Marketing Gmail"
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                    />
                </div>
                <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">Provider</label>
                    <div className="flex gap-4">
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                            <input type="radio" name="provider" value="SMTP" checked={form.provider === "SMTP"} onChange={() => set("provider", "SMTP")} />
                            SMTP / IMAP
                        </label>
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                            <input type="radio" name="provider" value="GMAIL" checked={form.provider === "GMAIL"} onChange={() => set("provider", "GMAIL")} />
                            Google Workspace / Gmail API
                        </label>
                    </div>
                </div>
            </div>

            {form.provider === "GMAIL" ? (
                <div className="bg-white border border-gray-200 rounded-xl p-6 text-center">
                    <div className="w-12 h-12 bg-red-50 rounded-full flex items-center justify-center mx-auto mb-3">
                        <Mail className="w-6 h-6 text-red-600" />
                    </div>
                    {initial?.google_email ? (
                        <>
                            <p className="text-sm font-medium text-gray-900 mb-1">Connected to Google</p>
                            <p className="text-sm text-gray-500 mb-4">Account: <b>{initial.google_email}</b></p>
                        </>
                    ) : (
                        <p className="text-sm text-gray-500 mb-4">Connect agents directly to your Google Workspace or Gmail account.</p>
                    )}
                    <button
                        type="button"
                        onClick={() => {
                            const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
                            const target = form.agent_id ? `?agent_id=${form.agent_id}` : "";
                            window.location.href = `${baseUrl}/api/auth/google/login${target}`;
                        }}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 font-medium inline-flex items-center gap-2"
                    >
                        {initial?.google_email ? "Reconnect with Google" : "Connect with Google"}
                    </button>
                    {!initial && (
                        <p className="text-xs text-gray-400 mt-4 max-w-sm mx-auto">
                            You will be redirected to Google to authorize Sutra to send and read emails on your behalf. There is no need to click Create below.
                        </p>
                    )}
                </div>
            ) : (
                <>
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider pt-2">SMTP (Outbound)</p>
                    <div className="grid grid-cols-3 gap-3">
                        <div className="col-span-2">
                            <label className="block text-xs font-medium text-gray-600 mb-1">SMTP Host *</label>
                            <input required value={form.smtp_host} onChange={e => set("smtp_host", e.target.value)}
                                placeholder="smtp.gmail.com"
                                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                        </div>
                <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Port *</label>
                    <input required type="number" value={form.smtp_port} onChange={e => set("smtp_port", +e.target.value)}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                </div>
                <div className="col-span-3 grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">SMTP Username *</label>
                        <input required value={form.smtp_username} onChange={e => set("smtp_username", e.target.value)}
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">
                            SMTP Password {initial ? "(leave blank to keep)" : "*"}
                        </label>
                        <div className="relative">
                            <input
                                type={showSmtpPass ? "text" : "password"}
                                required={!initial}
                                value={form.smtp_password}
                                onChange={e => set("smtp_password", e.target.value)}
                                className="w-full border border-gray-200 rounded-lg px-3 py-2 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            />
                            <button type="button" onClick={() => setShowSmtpPass(s => !s)}
                                className="absolute right-2 top-2 text-gray-400 hover:text-gray-600">
                                {showSmtpPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>
                </div>
                <div className="col-span-3 grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">From Email *</label>
                        <input required value={form.smtp_from_email} onChange={e => set("smtp_from_email", e.target.value)}
                            placeholder="agent@yourcompany.com"
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">From Name</label>
                        <input value={form.smtp_from_name} onChange={e => set("smtp_from_name", e.target.value)}
                            placeholder="Sutra Agent"
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                    </div>
                </div>
                <div className="col-span-3 flex gap-6">
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input type="checkbox" checked={form.smtp_use_tls} onChange={e => set("smtp_use_tls", e.target.checked)} className="rounded" />
                        STARTTLS
                    </label>
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input type="checkbox" checked={form.smtp_use_ssl} onChange={e => set("smtp_use_ssl", e.target.checked)} className="rounded" />
                        SSL/TLS (port 465)
                    </label>
                </div>
            </div>

            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider pt-2">IMAP (Inbound — optional)</p>
            <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                    <label className="block text-xs font-medium text-gray-600 mb-1">IMAP Host</label>
                    <input value={form.imap_host} onChange={e => set("imap_host", e.target.value)}
                        placeholder="imap.gmail.com"
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                </div>
                <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Port</label>
                    <input type="number" value={form.imap_port} onChange={e => set("imap_port", +e.target.value)}
                        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                </div>
                <div className="col-span-3 grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">IMAP Username</label>
                        <input value={form.imap_username} onChange={e => set("imap_username", e.target.value)}
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">IMAP Password</label>
                        <div className="relative">
                            <input
                                type={showImapPass ? "text" : "password"}
                                value={form.imap_password}
                                onChange={e => set("imap_password", e.target.value)}
                                className="w-full border border-gray-200 rounded-lg px-3 py-2 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            />
                            <button type="button" onClick={() => setShowImapPass(s => !s)}
                                className="absolute right-2 top-2 text-gray-400 hover:text-gray-600">
                                {showImapPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>
                </div>
                <div className="col-span-3 grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-xs font-medium text-gray-600 mb-1">Default Folder</label>
                        <input value={form.imap_folder} onChange={e => set("imap_folder", e.target.value)}
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600" />
                    </div>
                    <div className="flex items-end pb-1">
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                            <input type="checkbox" checked={form.imap_use_ssl} onChange={e => set("imap_use_ssl", e.target.checked)} className="rounded" />
                            SSL
                        </label>
                    </div>
                </div>
            </div>
            </>
            )}

            <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={onCancel}
                    className="px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">
                    Cancel
                </button>
                {!(form.provider === "GMAIL" && !initial) && (
                    <button type="submit" disabled={saving}
                        className="px-4 py-2 bg-stone-700 text-white rounded-lg text-sm hover:bg-stone-700 disabled:opacity-50 flex items-center gap-2">
                        {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                        {initial ? "Update" : "Create"} Config
                    </button>
                )}
            </div>
        </form>
    );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function EmailPage() {
    const [tab, setTab] = useState<Tab>("configs");
    const [agents, setAgents] = useState<Agent[]>([]);

    // Configs state
    const [configs, setConfigs] = useState<EmailConfig[]>([]);
    const [configsLoading, setConfigsLoading] = useState(false);
    const [showConfigForm, setShowConfigForm] = useState(false);
    const [editingConfig, setEditingConfig] = useState<EmailConfig | null>(null);
    const [testConfigId, setTestConfigId] = useState<string | null>(null);
    const [testTo, setTestTo] = useState("");
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);

    // Whitelist state
    const [whitelist, setWhitelist] = useState<EmailWhitelistEntry[]>([]);
    const [wlLoading, setWlLoading] = useState(false);
    const [wlAgentFilter, setWlAgentFilter] = useState<string>("");
    const [showAddWl, setShowAddWl] = useState(false);
    const [wlForm, setWlForm] = useState({ agent_id: "", email_address: "", label: "", is_active: true });
    const [wlSaving, setWlSaving] = useState(false);
    const [wlError, setWlError] = useState("");

    useEffect(() => {
        agentsApi.list().then(setAgents).catch(() => {});
    }, []);

    // Configs
    useEffect(() => {
        if (tab !== "configs") return;
        setConfigsLoading(true);
        emailApi.listConfigs().then(setConfigs).catch(() => {}).finally(() => setConfigsLoading(false));
    }, [tab]);

    async function handleSaveConfig(data: Record<string, unknown>) {
        if (editingConfig) {
            const updated = await emailApi.updateConfig(editingConfig.id, data as Parameters<typeof emailApi.updateConfig>[1]);
            setConfigs(c => c.map(x => x.id === updated.id ? updated : x));
        } else {
            const created = await emailApi.createConfig(data as Parameters<typeof emailApi.createConfig>[0]);
            setConfigs(c => [...c, created]);
        }
        setShowConfigForm(false);
        setEditingConfig(null);
    }

    async function handleDeleteConfig(id: string) {
        if (!confirm("Delete this email configuration?")) return;
        await emailApi.deleteConfig(id);
        setConfigs(c => c.filter(x => x.id !== id));
    }

    async function handleTest() {
        if (!testConfigId || !testTo) return;
        setTesting(true);
        setTestResult(null);
        try {
            const res = await emailApi.testConfig(testConfigId, testTo);
            setTestResult({ ok: true, msg: res.message });
        } catch (err: unknown) {
            setTestResult({ ok: false, msg: err instanceof Error ? err.message : String(err) });
        } finally {
            setTesting(false);
        }
    }

    // Whitelist
    useEffect(() => {
        if (tab !== "whitelist") return;
        loadWhitelist();
    }, [tab, wlAgentFilter]);

    function loadWhitelist() {
        setWlLoading(true);
        emailApi.listWhitelist(wlAgentFilter || undefined)
            .then(setWhitelist).catch(() => {}).finally(() => setWlLoading(false));
    }

    async function handleAddWhitelist(e: React.FormEvent) {
        e.preventDefault();
        setWlSaving(true);
        setWlError("");
        try {
            const entry = await emailApi.addWhitelist({
                agent_id: wlForm.agent_id || null,
                email_address: wlForm.email_address,
                label: wlForm.label || undefined,
                is_active: wlForm.is_active,
            });
            setWhitelist(w => [...w, entry]);
            setShowAddWl(false);
            setWlForm({ agent_id: "", email_address: "", label: "", is_active: true });
        } catch (err: unknown) {
            setWlError(err instanceof Error ? err.message : String(err));
        } finally {
            setWlSaving(false);
        }
    }

    async function handleToggleActive(entry: EmailWhitelistEntry) {
        const updated = await emailApi.updateWhitelist(entry.id, { ...entry, is_active: !entry.is_active });
        setWhitelist(w => w.map(x => x.id === updated.id ? updated : x));
    }

    async function handleDeleteWhitelist(id: string) {
        if (!confirm("Remove this whitelist entry?")) return;
        await emailApi.deleteWhitelist(id);
        setWhitelist(w => w.filter(x => x.id !== id));
    }

    function agentName(id: string | null) {
        if (!id) return "System (all agents)";
        return agents.find(a => a.id === id)?.name ?? id;
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="border-b border-gray-100 bg-white px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center">
                        <Mail className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                        <h1 className="text-lg font-semibold text-gray-900">Email Management</h1>
                        <p className="text-xs text-gray-500">Configure SMTP/IMAP accounts and control which addresses agents can email</p>
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="border-b border-gray-100 bg-white px-6">
                <div className="flex gap-1">
                    {[
                        { id: "configs", label: "Email Configs", icon: Server },
                        { id: "whitelist", label: "Whitelist", icon: ShieldCheck },
                    ].map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => setTab(id as Tab)}
                            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                                tab === id
                                    ? "border-stone-600 text-stone-700"
                                    : "border-transparent text-gray-500 hover:text-gray-700"
                            }`}
                        >
                            <Icon className="w-4 h-4" />
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-6 bg-gray-50">

                {/* ── CONFIGS TAB ── */}
                {tab === "configs" && (
                    <div className="space-y-4 max-w-4xl">
                        <div className="flex items-center justify-between">
                            <p className="text-sm text-gray-600">
                                One config per agent (or a system default). Agents use their own config if set, otherwise fall back to the default.
                            </p>
                            <button
                                onClick={() => { setEditingConfig(null); setShowConfigForm(true); }}
                                className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white text-sm rounded-lg hover:bg-stone-700"
                            >
                                <Plus className="w-4 h-4" /> Add Config
                            </button>
                        </div>

                        {/* Test panel */}
                        {testConfigId && (
                            <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
                                <div className="flex items-center justify-between">
                                    <p className="text-sm font-medium text-gray-700">Test Email Config</p>
                                    <button onClick={() => { setTestConfigId(null); setTestResult(null); }} className="text-gray-400 hover:text-gray-600">
                                        <X className="w-4 h-4" />
                                    </button>
                                </div>
                                <div className="flex gap-3">
                                    <input
                                        type="email"
                                        placeholder="Send test to..."
                                        value={testTo}
                                        onChange={e => setTestTo(e.target.value)}
                                        className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                    />
                                    <button
                                        onClick={handleTest}
                                        disabled={testing || !testTo}
                                        className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white text-sm rounded-lg hover:bg-stone-700 disabled:opacity-50"
                                    >
                                        {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <SendHorizonal className="w-4 h-4" />}
                                        Send Test
                                    </button>
                                </div>
                                {testResult && (
                                    <div className={`flex items-center gap-2 text-sm p-2 rounded-lg ${testResult.ok ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                                        {testResult.ok ? <CheckCircle className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
                                        {testResult.msg}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Form */}
                        {showConfigForm && (
                            <div className="bg-white border border-gray-200 rounded-xl p-6">
                                <h3 className="text-sm font-semibold text-gray-800 mb-4">
                                    {editingConfig ? "Edit Email Config" : "New Email Config"}
                                </h3>
                                <ConfigForm
                                    initial={editingConfig ?? undefined}
                                    agents={agents}
                                    onSave={handleSaveConfig}
                                    onCancel={() => { setShowConfigForm(false); setEditingConfig(null); }}
                                />
                            </div>
                        )}

                        {/* Configs list */}
                        {configsLoading ? (
                            <div className="flex justify-center py-12 text-gray-400">
                                <Loader2 className="w-6 h-6 animate-spin" />
                            </div>
                        ) : configs.length === 0 ? (
                            <div className="bg-white border border-dashed border-gray-200 rounded-xl p-12 text-center">
                                <Mail className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                                <p className="text-sm text-gray-500">No email configs yet. Add one to let agents send and receive email.</p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {configs.map(cfg => (
                                    <div key={cfg.id} className="bg-white border border-gray-200 rounded-xl p-4">
                                        <div className="flex items-start justify-between gap-4">
                                            <div className="flex-1">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <span className="font-medium text-gray-900 text-sm">
                                                        {cfg.label || (cfg.agent_id ? agentName(cfg.agent_id) : "System Default")}
                                                    </span>
                                                    {!cfg.agent_id && (
                                                        <span className="px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-700 font-medium">Default</span>
                                                    )}
                                                    {cfg.agent_id && (
                                                        <span className="px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700 font-medium">
                                                            {agentName(cfg.agent_id)}
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-xs text-gray-500 mt-2">
                                                    {cfg.provider === "GMAIL" ? (
                                                        <>
                                                            <span><b>Provider:</b> Google Workspace (Gmail API)</span>
                                                            <span><b>Account:</b> {cfg.google_email || "Unknown"}</span>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <span><b>SMTP:</b> {cfg.smtp_host}:{cfg.smtp_port} {cfg.smtp_use_ssl ? "(SSL)" : cfg.smtp_use_tls ? "(STARTTLS)" : ""}</span>
                                                            <span><b>From:</b> {cfg.smtp_from_name ? `${cfg.smtp_from_name} <${cfg.smtp_from_email}>` : cfg.smtp_from_email}</span>
                                                            {cfg.imap_host && (
                                                                <>
                                                                    <span><b>IMAP:</b> {cfg.imap_host}:{cfg.imap_port}</span>
                                                                    <span><b>Folder:</b> {cfg.imap_folder}</span>
                                                                </>
                                                            )}
                                                        </>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2 shrink-0">
                                                <button
                                                    onClick={() => { setTestConfigId(cfg.id); setTestResult(null); }}
                                                    className="p-2 rounded-lg text-gray-400 hover:text-stone-700 hover:bg-stone-100 transition-colors"
                                                    title="Test this config"
                                                >
                                                    <SendHorizonal className="w-4 h-4" />
                                                </button>
                                                <button
                                                    onClick={() => { setEditingConfig(cfg); setShowConfigForm(true); }}
                                                    className="p-2 rounded-lg text-gray-400 hover:text-stone-700 hover:bg-stone-100 transition-colors"
                                                    title="Edit"
                                                >
                                                    <Edit2 className="w-4 h-4" />
                                                </button>
                                                <button
                                                    onClick={() => handleDeleteConfig(cfg.id)}
                                                    className="p-2 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                                                    title="Delete"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ── WHITELIST TAB ── */}
                {tab === "whitelist" && (
                    <div className="space-y-4 max-w-3xl">
                        <div className="flex items-center justify-between gap-4">
                            <div className="flex items-center gap-3">
                                <select
                                    value={wlAgentFilter}
                                    onChange={e => setWlAgentFilter(e.target.value)}
                                    className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                >
                                    <option value="">All agents</option>
                                    <option value="null">Global (no agent)</option>
                                    {agents.map(a => (
                                        <option key={a.id} value={a.id}>{a.name}</option>
                                    ))}
                                </select>
                                <p className="text-sm text-gray-500">
                                    Agents can only send email to addresses listed here.
                                </p>
                            </div>
                            <button
                                onClick={() => setShowAddWl(true)}
                                className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white text-sm rounded-lg hover:bg-stone-700 shrink-0"
                            >
                                <Plus className="w-4 h-4" /> Add Address
                            </button>
                        </div>

                        {/* Add form */}
                        {showAddWl && (
                            <form onSubmit={handleAddWhitelist} className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
                                <p className="text-sm font-semibold text-gray-800">Add Whitelisted Address</p>
                                {wlError && (
                                    <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                                        <AlertCircle className="w-4 h-4" />{wlError}
                                    </div>
                                )}
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-medium text-gray-600 mb-1">Agent Scope</label>
                                        <select
                                            value={wlForm.agent_id}
                                            onChange={e => setWlForm(f => ({ ...f, agent_id: e.target.value }))}
                                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                        >
                                            <option value="">Global (all agents)</option>
                                            {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-gray-600 mb-1">Email Address *</label>
                                        <input
                                            required
                                            type="email"
                                            value={wlForm.email_address}
                                            onChange={e => setWlForm(f => ({ ...f, email_address: e.target.value }))}
                                            placeholder="contact@example.com"
                                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-gray-600 mb-1">Label</label>
                                        <input
                                            value={wlForm.label}
                                            onChange={e => setWlForm(f => ({ ...f, label: e.target.value }))}
                                            placeholder="e.g. CEO, Support Team"
                                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                        />
                                    </div>
                                    <div className="flex items-end pb-1">
                                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                                            <input type="checkbox" checked={wlForm.is_active}
                                                onChange={e => setWlForm(f => ({ ...f, is_active: e.target.checked }))} className="rounded" />
                                            Active
                                        </label>
                                    </div>
                                </div>
                                <div className="flex justify-end gap-3">
                                    <button type="button" onClick={() => { setShowAddWl(false); setWlError(""); }}
                                        className="px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
                                    <button type="submit" disabled={wlSaving}
                                        className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white text-sm rounded-lg hover:bg-stone-700 disabled:opacity-50">
                                        {wlSaving && <Loader2 className="w-4 h-4 animate-spin" />}
                                        Add to Whitelist
                                    </button>
                                </div>
                            </form>
                        )}

                        {wlLoading ? (
                            <div className="flex justify-center py-12 text-gray-400">
                                <Loader2 className="w-6 h-6 animate-spin" />
                            </div>
                        ) : whitelist.length === 0 ? (
                            <div className="bg-white border border-dashed border-gray-200 rounded-xl p-12 text-center">
                                <ShieldCheck className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                                <p className="text-sm text-gray-500">No whitelisted addresses yet.</p>
                                <p className="text-xs text-gray-400 mt-1">Agents cannot send any email until at least one address is whitelisted.</p>
                            </div>
                        ) : (
                            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                                <table className="w-full text-sm">
                                    <thead className="bg-gray-50 border-b border-gray-100">
                                        <tr>
                                            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Email</th>
                                            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Label</th>
                                            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Scope</th>
                                            <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Status</th>
                                            <th className="px-4 py-3"></th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-50">
                                        {whitelist.map(entry => (
                                            <tr key={entry.id} className="hover:bg-gray-50 transition-colors">
                                                <td className="px-4 py-3 font-medium text-gray-800">{entry.email_address}</td>
                                                <td className="px-4 py-3 text-gray-500">{entry.label || "—"}</td>
                                                <td className="px-4 py-3 text-gray-500">
                                                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${entry.agent_id ? "bg-blue-100 text-blue-700" : "bg-purple-100 text-purple-700"}`}>
                                                        {agentName(entry.agent_id)}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3">
                                                    <Badge active={entry.is_active} />
                                                </td>
                                                <td className="px-4 py-3">
                                                    <div className="flex items-center gap-1 justify-end">
                                                        <button
                                                            onClick={() => handleToggleActive(entry)}
                                                            className="p-1.5 rounded text-gray-400 hover:text-stone-700 hover:bg-stone-100 transition-colors"
                                                            title={entry.is_active ? "Deactivate" : "Activate"}
                                                        >
                                                            {entry.is_active ? <X className="w-4 h-4" /> : <Check className="w-4 h-4" />}
                                                        </button>
                                                        <button
                                                            onClick={() => handleDeleteWhitelist(entry.id)}
                                                            className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                                                            title="Remove"
                                                        >
                                                            <Trash2 className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
