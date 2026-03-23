"use client";

import { useState, useEffect } from "react";
import {
    Blocks,
    Plus,
    Play,
    Square,
    Trash2,
    Terminal,
    Globe,
    Radio,
    Wrench,
    FileText,
    MessageSquareText,
    ChevronDown,
    ChevronRight,
    Loader2,
    Save,
    X,
    ArrowLeft,
    Tag,
    Settings2,
    ExternalLink,
    Copy,
    Check,
} from "lucide-react";
import { mcpServersApi, type MCPServer } from "@/lib/api";

const TRANSPORT_OPTIONS = [
    { value: "stdio", label: "Stdio (Local Process)", icon: Terminal, description: "Run a local command/process" },
    { value: "sse", label: "SSE (Server-Sent Events)", icon: Radio, description: "Connect to a remote SSE server" },
    { value: "streamable_http", label: "Streamable HTTP", icon: Globe, description: "Connect via HTTP streaming" },
];

const PRESET_SERVERS = [
    {
        name: "Filesystem",
        description: "Read, write, and manage files on the local filesystem",
        command: "npx -y @modelcontextprotocol/server-filesystem /tmp",
        transport_type: "stdio",
        icon: "📁",
        tags: ["files", "filesystem"],
    },
    {
        name: "GitHub",
        description: "Interact with GitHub repos, issues, PRs, and more",
        command: "npx -y @modelcontextprotocol/server-github",
        transport_type: "stdio",
        icon: "🐙",
        tags: ["github", "git", "code"],
        env_hint: "GITHUB_PERSONAL_ACCESS_TOKEN",
    },
    {
        name: "PostgreSQL",
        description: "Query and manage PostgreSQL databases",
        command: "npx -y @modelcontextprotocol/server-postgres postgresql://localhost/mydb",
        transport_type: "stdio",
        icon: "🐘",
        tags: ["database", "sql"],
    },
    {
        name: "Brave Search",
        description: "Search the web using Brave Search API",
        command: "npx -y @modelcontextprotocol/server-brave-search",
        transport_type: "stdio",
        icon: "🔍",
        tags: ["search", "web"],
        env_hint: "BRAVE_API_KEY",
    },
    {
        name: "Puppeteer",
        description: "Browser automation and web scraping",
        command: "npx -y @modelcontextprotocol/server-puppeteer",
        transport_type: "stdio",
        icon: "🌐",
        tags: ["browser", "scraping"],
    },
    {
        name: "Slack",
        description: "Interact with Slack workspaces, channels, and messages",
        command: "npx -y @modelcontextprotocol/server-slack",
        transport_type: "stdio",
        icon: "💬",
        tags: ["slack", "messaging"],
        env_hint: "SLACK_BOT_TOKEN",
    },
    {
        name: "Google Maps",
        description: "Geocoding, directions, and place search via Google Maps API",
        command: "npx -y @modelcontextprotocol/server-google-maps",
        transport_type: "stdio",
        icon: "🗺️",
        tags: ["maps", "location"],
        env_hint: "GOOGLE_MAPS_API_KEY",
    },
    {
        name: "Memory (Knowledge Graph)",
        description: "Persistent memory using a local knowledge graph",
        command: "npx -y @modelcontextprotocol/server-memory",
        transport_type: "stdio",
        icon: "🧠",
        tags: ["memory", "knowledge"],
    },
    {
        name: "Gmail",
        description: "Send, read, search, and manage Gmail emails with OAuth2 auto-authentication",
        command: "npx -y @gongrzhe/server-gmail-autoauth-mcp",
        transport_type: "stdio",
        icon: "📧",
        tags: ["gmail", "email", "google"],
        env_hint: "GOOGLE_CLIENT_ID,GOOGLE_CLIENT_SECRET",
    },
    {
        name: "Google Spreadsheets",
        description: "Read, write, and manage Google Sheets spreadsheets",
        command: "npx -y @gongrzhe/server-google-sheets-mcp",
        transport_type: "stdio",
        icon: "📊",
        tags: ["sheets", "spreadsheets", "google"],
        env_hint: "GOOGLE_CLIENT_ID,GOOGLE_CLIENT_SECRET",
    },
];

export default function MCPServersPage() {
    const [servers, setServers] = useState<MCPServer[]>([]);
    const [loading, setLoading] = useState(true);
    const [showAddForm, setShowAddForm] = useState(false);
    const [showPresets, setShowPresets] = useState(false);
    const [expandedServer, setExpandedServer] = useState<string | null>(null);
    const [actionLoading, setActionLoading] = useState<string | null>(null);
    const [copiedId, setCopiedId] = useState<string | null>(null);

    // Form state
    const [formName, setFormName] = useState("");
    const [formDescription, setFormDescription] = useState("");
    const [formTransport, setFormTransport] = useState("stdio");
    const [formCommand, setFormCommand] = useState("");
    const [formUrl, setFormUrl] = useState("");
    const [formIcon, setFormIcon] = useState("🔌");
    const [formTags, setFormTags] = useState("");
    const [formEnvVars, setFormEnvVars] = useState<{ key: string; value: string }[]>([]);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        loadServers();
    }, []);

    async function loadServers() {
        try {
            const list = await mcpServersApi.list();
            setServers(list);
        } catch (err) {
            console.error("Failed to load MCP servers:", err);
        } finally {
            setLoading(false);
        }
    }

    function resetForm() {
        setFormName("");
        setFormDescription("");
        setFormTransport("stdio");
        setFormCommand("");
        setFormUrl("");
        setFormIcon("🔌");
        setFormTags("");
        setFormEnvVars([]);
    }

    function loadPreset(preset: typeof PRESET_SERVERS[0]) {
        setFormName(preset.name);
        setFormDescription(preset.description);
        setFormTransport(preset.transport_type);
        setFormCommand(preset.command);
        setFormIcon(preset.icon);
        setFormTags(preset.tags.join(", "));
        if (preset.env_hint) {
            const hints = preset.env_hint.split(",").map(h => h.trim());
            setFormEnvVars(hints.map(key => ({ key, value: "" })));
        } else {
            setFormEnvVars([]);
        }
        setShowPresets(false);
        setShowAddForm(true);
    }

    async function handleCreate(e: React.FormEvent) {
        e.preventDefault();
        if (!formName.trim()) return;

        setSaving(true);
        try {
            const envObj: Record<string, string> = {};
            formEnvVars.forEach(ev => {
                if (ev.key.trim()) envObj[ev.key.trim()] = ev.value;
            });

            await mcpServersApi.create({
                name: formName.trim(),
                description: formDescription.trim() || undefined,
                transport_type: formTransport as any,
                command: formTransport === "stdio" ? formCommand.trim() || undefined : undefined,
                url: formTransport !== "stdio" ? formUrl.trim() || undefined : undefined,
                icon: formIcon || undefined,
                tags: formTags.split(",").map(t => t.trim()).filter(Boolean),
                env_vars: Object.keys(envObj).length > 0 ? envObj : undefined,
            });

            resetForm();
            setShowAddForm(false);
            await loadServers();
        } catch (err) {
            console.error("Failed to create MCP server:", err);
            alert("Failed to create MCP server");
        } finally {
            setSaving(false);
        }
    }

    async function handleStart(id: string) {
        setActionLoading(id);
        try {
            await mcpServersApi.start(id);
            await loadServers();
        } catch (err) {
            console.error("Failed to start server:", err);
        } finally {
            setActionLoading(null);
        }
    }

    async function handleStop(id: string) {
        setActionLoading(id);
        try {
            await mcpServersApi.stop(id);
            await loadServers();
        } catch (err) {
            console.error("Failed to stop server:", err);
        } finally {
            setActionLoading(null);
        }
    }

    async function handleDelete(id: string) {
        if (!confirm("Are you sure you want to delete this MCP server?")) return;
        try {
            await mcpServersApi.delete(id);
            await loadServers();
        } catch (err) {
            console.error("Failed to delete server:", err);
        }
    }

    function copyCommand(command: string, id: string) {
        navigator.clipboard.writeText(command);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
    }

    const runningCount = servers.filter(s => s.status === "running").length;
    const totalToolsCount = servers.reduce((sum, s) => sum + (s.tools?.length || 0), 0);

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-stone-900 flex items-center gap-2.5">
                        <div className="p-2 bg-gradient-to-br from-violet-500 to-purple-600 rounded-xl shadow-lg shadow-violet-200">
                            <Blocks className="w-5 h-5 text-white" />
                        </div>
                        MCP Servers
                    </h1>
                    <p className="text-sm text-stone-500 mt-1.5">
                        Plug in Model Context Protocol servers to extend agent capabilities
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <button
                        onClick={() => { setShowPresets(!showPresets); setShowAddForm(false); }}
                        className="btn-secondary flex items-center gap-2 text-sm"
                    >
                        <Blocks className="w-4 h-4" />
                        Browse Presets
                    </button>
                    <button
                        onClick={() => { setShowAddForm(!showAddForm); setShowPresets(false); resetForm(); }}
                        className="btn-primary flex items-center gap-2"
                    >
                        <Plus className="w-4 h-4" />
                        <span className="hidden sm:inline">Add Server</span>
                        <span className="sm:hidden">Add</span>
                    </button>
                </div>
            </div>

            {/* Stats Row */}
            <div className="grid grid-cols-3 gap-4">
                <div className="bg-white border border-stone-200 rounded-xl p-4 shadow-sm">
                    <div className="text-2xl font-bold text-stone-900">{servers.length}</div>
                    <div className="text-xs text-stone-500 uppercase tracking-wider font-medium mt-1">Total Servers</div>
                </div>
                <div className="bg-white border border-stone-200 rounded-xl p-4 shadow-sm">
                    <div className="text-2xl font-bold text-emerald-600">{runningCount}</div>
                    <div className="text-xs text-stone-500 uppercase tracking-wider font-medium mt-1">Running</div>
                </div>
                <div className="bg-white border border-stone-200 rounded-xl p-4 shadow-sm">
                    <div className="text-2xl font-bold text-violet-600">{totalToolsCount}</div>
                    <div className="text-xs text-stone-500 uppercase tracking-wider font-medium mt-1">Available Tools</div>
                </div>
            </div>

            {/* Preset Browser */}
            {showPresets && (
                <div className="bg-white border border-stone-200 rounded-xl p-6 shadow-sm animate-slide-up">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-sm font-bold text-stone-700 uppercase tracking-wider">Quick Add — Official MCP Servers</h2>
                        <button onClick={() => setShowPresets(false)} className="text-stone-400 hover:text-stone-600">
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                        {PRESET_SERVERS.map((preset) => (
                            <button
                                key={preset.name}
                                onClick={() => loadPreset(preset)}
                                className="text-left p-4 rounded-xl border border-stone-200 hover:border-violet-300 hover:bg-violet-50/50 transition-all group"
                            >
                                <div className="flex items-center gap-2 mb-2">
                                    <span className="text-xl">{preset.icon}</span>
                                    <span className="font-semibold text-sm text-stone-900 group-hover:text-violet-700 transition-colors">{preset.name}</span>
                                </div>
                                <p className="text-xs text-stone-500 line-clamp-2">{preset.description}</p>
                                <div className="flex flex-wrap gap-1 mt-2">
                                    {preset.tags.map(tag => (
                                        <span key={tag} className="px-1.5 py-0.5 rounded-md bg-stone-100 text-stone-500 text-[10px] uppercase tracking-wider font-medium">{tag}</span>
                                    ))}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Add Server Form */}
            {showAddForm && (
                <form onSubmit={handleCreate} className="bg-white border border-violet-200 rounded-xl p-6 shadow-sm shadow-violet-100 space-y-5 animate-slide-up">
                    <div className="flex items-center justify-between">
                        <h2 className="text-sm font-bold text-stone-700 uppercase tracking-wider flex items-center gap-2">
                            <Settings2 className="w-4 h-4 text-violet-500" />
                            Configure MCP Server
                        </h2>
                        <button type="button" onClick={() => { setShowAddForm(false); resetForm(); }} className="text-stone-400 hover:text-stone-600">
                            <X className="w-4 h-4" />
                        </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1.5">Server Name *</label>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={formIcon}
                                    onChange={(e) => setFormIcon(e.target.value)}
                                    className="w-12 text-center bg-stone-50 border border-stone-200 rounded-lg px-2 py-2 text-lg focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500"
                                    maxLength={2}
                                />
                                <input
                                    type="text"
                                    value={formName}
                                    onChange={(e) => setFormName(e.target.value)}
                                    placeholder="e.g. Filesystem Server"
                                    required
                                    className="flex-1 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all text-sm"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1.5">Tags</label>
                            <div className="flex gap-2 items-center">
                                <Tag className="w-4 h-4 text-stone-400 flex-shrink-0" />
                                <input
                                    type="text"
                                    value={formTags}
                                    onChange={(e) => setFormTags(e.target.value)}
                                    placeholder="e.g. files, filesystem"
                                    className="flex-1 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all text-sm"
                                />
                            </div>
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1.5">Description</label>
                        <input
                            type="text"
                            value={formDescription}
                            onChange={(e) => setFormDescription(e.target.value)}
                            placeholder="Brief description of what this server does..."
                            className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all text-sm"
                        />
                    </div>

                    {/* Transport Type */}
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-2">Transport Type *</label>
                        <div className="grid grid-cols-3 gap-3">
                            {TRANSPORT_OPTIONS.map(opt => (
                                <button
                                    key={opt.value}
                                    type="button"
                                    onClick={() => setFormTransport(opt.value)}
                                    className={`p-3 rounded-xl border text-left transition-all ${formTransport === opt.value
                                        ? "border-violet-400 bg-violet-50 ring-1 ring-violet-200"
                                        : "border-stone-200 hover:border-stone-300 bg-white"
                                        }`}
                                >
                                    <opt.icon className={`w-4 h-4 mb-1.5 ${formTransport === opt.value ? "text-violet-600" : "text-stone-400"}`} />
                                    <div className={`text-xs font-semibold ${formTransport === opt.value ? "text-violet-700" : "text-stone-700"}`}>{opt.label}</div>
                                    <div className="text-[10px] text-stone-400 mt-0.5">{opt.description}</div>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Connection Config */}
                    {formTransport === "stdio" ? (
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1.5">Command *</label>
                            <div className="flex items-center gap-2">
                                <Terminal className="w-4 h-4 text-stone-400 flex-shrink-0" />
                                <input
                                    type="text"
                                    value={formCommand}
                                    onChange={(e) => setFormCommand(e.target.value)}
                                    placeholder="npx -y @modelcontextprotocol/server-filesystem /tmp"
                                    required
                                    className="flex-1 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all text-sm font-mono"
                                />
                            </div>
                        </div>
                    ) : (
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1.5">Server URL *</label>
                            <div className="flex items-center gap-2">
                                <Globe className="w-4 h-4 text-stone-400 flex-shrink-0" />
                                <input
                                    type="url"
                                    value={formUrl}
                                    onChange={(e) => setFormUrl(e.target.value)}
                                    placeholder="http://localhost:3001/sse"
                                    required
                                    className="flex-1 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500 transition-all text-sm font-mono"
                                />
                            </div>
                        </div>
                    )}

                    {/* Environment Variables */}
                    <div>
                        <div className="flex items-center justify-between mb-2">
                            <label className="text-xs font-medium text-stone-600">Environment Variables</label>
                            <button
                                type="button"
                                onClick={() => setFormEnvVars([...formEnvVars, { key: "", value: "" }])}
                                className="text-xs text-violet-600 hover:text-violet-700 font-medium flex items-center gap-1"
                            >
                                <Plus className="w-3 h-3" /> Add Variable
                            </button>
                        </div>
                        {formEnvVars.length > 0 ? (
                            <div className="space-y-2">
                                {formEnvVars.map((ev, idx) => (
                                    <div key={idx} className="flex gap-2">
                                        <input
                                            type="text"
                                            value={ev.key}
                                            onChange={(e) => {
                                                const updated = [...formEnvVars];
                                                updated[idx].key = e.target.value;
                                                setFormEnvVars(updated);
                                            }}
                                            placeholder="KEY"
                                            className="w-48 bg-stone-50 border border-stone-200 rounded-lg px-3 py-1.5 text-sm font-mono text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500"
                                        />
                                        <input
                                            type="password"
                                            value={ev.value}
                                            onChange={(e) => {
                                                const updated = [...formEnvVars];
                                                updated[idx].value = e.target.value;
                                                setFormEnvVars(updated);
                                            }}
                                            placeholder="value"
                                            className="flex-1 bg-stone-50 border border-stone-200 rounded-lg px-3 py-1.5 text-sm font-mono text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/10 focus:border-violet-500"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setFormEnvVars(formEnvVars.filter((_, i) => i !== idx))}
                                            className="text-stone-400 hover:text-red-500 p-1"
                                        >
                                            <X className="w-4 h-4" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="text-xs text-stone-400">No environment variables configured.</p>
                        )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center justify-end gap-3 pt-2 border-t border-stone-100">
                        <button
                            type="button"
                            onClick={() => { setShowAddForm(false); resetForm(); }}
                            className="px-4 py-2 rounded-lg border border-stone-200 text-stone-500 hover:bg-stone-50 transition-colors font-medium text-sm"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={saving}
                            className="flex items-center gap-2 px-6 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-lg font-semibold shadow-lg shadow-violet-200 transition-all active:scale-[0.98] disabled:opacity-60 text-sm"
                        >
                            {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                            {saving ? "Creating..." : "Create Server"}
                        </button>
                    </div>
                </form>
            )}

            {/* Server List */}
            {loading ? (
                <div className="text-center py-16 text-stone-400">
                    <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
                    Loading MCP servers...
                </div>
            ) : servers.length === 0 && !showAddForm ? (
                <div className="text-center py-20 bg-white border border-stone-200 rounded-xl shadow-sm">
                    <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-violet-400 to-purple-600 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-violet-200">
                        <Blocks className="w-10 h-10 text-white" />
                    </div>
                    <h3 className="text-xl font-semibold text-stone-900 mb-2">No MCP Servers</h3>
                    <p className="text-stone-500 mb-6 max-w-md mx-auto">
                        Add MCP servers to extend your agents with file access, database queries, web search, and more.
                    </p>
                    <div className="flex items-center justify-center gap-3">
                        <button
                            onClick={() => setShowPresets(true)}
                            className="btn-secondary flex items-center gap-2"
                        >
                            <Blocks className="w-4 h-4" />
                            Browse Presets
                        </button>
                        <button
                            onClick={() => { setShowAddForm(true); resetForm(); }}
                            className="btn-primary flex items-center gap-2"
                        >
                            <Plus className="w-4 h-4" />
                            Add Custom Server
                        </button>
                    </div>
                </div>
            ) : (
                <div className="space-y-3">
                    {servers.map((server) => {
                        const isExpanded = expandedServer === server.id;
                        const transportOpt = TRANSPORT_OPTIONS.find(t => t.value === server.transport_type);
                        const TransportIcon = transportOpt?.icon || Terminal;

                        return (
                            <div key={server.id} className="bg-white border border-stone-200 rounded-xl shadow-sm overflow-hidden transition-all hover:shadow-md">
                                {/* Main Row */}
                                <div className="p-5 flex items-center gap-4">
                                    {/* Icon */}
                                    <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-violet-100 to-purple-100 border border-violet-200/50 flex items-center justify-center text-xl flex-shrink-0">
                                        {server.icon || "🔌"}
                                    </div>

                                    {/* Info */}
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <h3 className="font-semibold text-stone-900 truncate">{server.name}</h3>
                                            <div className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${server.status === "running"
                                                ? "bg-emerald-50 text-emerald-600 border border-emerald-200"
                                                : server.status === "error"
                                                    ? "bg-red-50 text-red-600 border border-red-200"
                                                    : "bg-stone-100 text-stone-500 border border-stone-200"
                                                }`}>
                                                <div className={`w-1.5 h-1.5 rounded-full ${server.status === "running" ? "bg-emerald-500 animate-pulse" : server.status === "error" ? "bg-red-500" : "bg-stone-400"
                                                    }`} />
                                                {server.status}
                                            </div>
                                        </div>
                                        {server.description && (
                                            <p className="text-xs text-stone-500 truncate mt-0.5">{server.description}</p>
                                        )}
                                        <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-violet-50 text-violet-600 text-[10px] font-bold uppercase tracking-wider border border-violet-100">
                                                <TransportIcon className="w-3 h-3" />
                                                {server.transport_type}
                                            </span>
                                            {(server.tools?.length || 0) > 0 && (
                                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 text-blue-600 text-[10px] font-bold">
                                                    <Wrench className="w-3 h-3" />
                                                    {server.tools?.length} tools
                                                </span>
                                            )}
                                            {(server.resources?.length || 0) > 0 && (
                                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 text-amber-600 text-[10px] font-bold">
                                                    <FileText className="w-3 h-3" />
                                                    {server.resources?.length} resources
                                                </span>
                                            )}
                                            {server.tags?.map(tag => (
                                                <span key={tag} className="px-1.5 py-0.5 rounded bg-stone-100 text-stone-500 text-[10px] uppercase tracking-wider font-medium">{tag}</span>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Actions */}
                                    <div className="flex items-center gap-2 flex-shrink-0">
                                        {server.status === "running" ? (
                                            <button
                                                onClick={() => handleStop(server.id)}
                                                disabled={actionLoading === server.id}
                                                className="btn-secondary flex items-center gap-1.5 py-1.5 px-3 text-xs"
                                            >
                                                {actionLoading === server.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Square className="w-3.5 h-3.5" />}
                                                Stop
                                            </button>
                                        ) : (
                                            <button
                                                onClick={() => handleStart(server.id)}
                                                disabled={actionLoading === server.id}
                                                className="btn-primary flex items-center gap-1.5 py-1.5 px-3 text-xs"
                                            >
                                                {actionLoading === server.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                                                Start
                                            </button>
                                        )}
                                        <button
                                            onClick={() => setExpandedServer(isExpanded ? null : server.id)}
                                            className="btn-icon p-1.5"
                                        >
                                            {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                                        </button>
                                        <button
                                            onClick={() => handleDelete(server.id)}
                                            className="btn-icon p-1.5 text-stone-400 hover:text-red-500"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>

                                {/* Expanded Details */}
                                {isExpanded && (
                                    <div className="border-t border-stone-100 bg-stone-50/50 p-5 space-y-4 animate-fade-in">
                                        {/* Connection Details */}
                                        <div>
                                            <h4 className="text-[10px] font-bold text-stone-500 uppercase tracking-widest mb-2">Connection</h4>
                                            {server.command && (
                                                <div className="flex items-center gap-2 bg-stone-900 text-stone-100 rounded-lg px-4 py-2.5 font-mono text-xs">
                                                    <Terminal className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                                                    <code className="flex-1 truncate">{server.command}</code>
                                                    <button
                                                        onClick={() => copyCommand(server.command!, server.id)}
                                                        className="text-stone-400 hover:text-white transition-colors flex-shrink-0"
                                                    >
                                                        {copiedId === server.id ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                                                    </button>
                                                </div>
                                            )}
                                            {server.url && (
                                                <div className="flex items-center gap-2 bg-stone-900 text-stone-100 rounded-lg px-4 py-2.5 font-mono text-xs">
                                                    <Globe className="w-4 h-4 text-blue-400 flex-shrink-0" />
                                                    <code className="flex-1 truncate">{server.url}</code>
                                                    <a href={server.url} target="_blank" className="text-stone-400 hover:text-white transition-colors">
                                                        <ExternalLink className="w-4 h-4" />
                                                    </a>
                                                </div>
                                            )}
                                        </div>

                                        {/* Environment Variables */}
                                        {server.env_vars && Object.keys(server.env_vars).length > 0 && (
                                            <div>
                                                <h4 className="text-[10px] font-bold text-stone-500 uppercase tracking-widest mb-2">Environment Variables</h4>
                                                <div className="flex flex-wrap gap-2">
                                                    {Object.keys(server.env_vars).map(key => (
                                                        <span key={key} className="px-2 py-1 rounded-md bg-white border border-stone-200 text-xs font-mono text-stone-600">
                                                            {key} = •••
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* Capabilities */}
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                            {/* Tools */}
                                            <div>
                                                <h4 className="text-[10px] font-bold text-stone-500 uppercase tracking-widest mb-2 flex items-center gap-1">
                                                    <Wrench className="w-3 h-3" /> Tools ({server.tools?.length || 0})
                                                </h4>
                                                {(server.tools?.length || 0) > 0 ? (
                                                    <div className="space-y-1">
                                                        {server.tools?.map((tool: any, i: number) => (
                                                            <div key={i} className="px-2.5 py-1.5 rounded-lg bg-white border border-stone-200 text-xs">
                                                                <div className="font-medium text-stone-800">{tool.name || tool}</div>
                                                                {tool.description && <div className="text-stone-400 text-[10px] truncate">{tool.description}</div>}
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <p className="text-xs text-stone-400 italic">No tools discovered yet. Start the server to discover tools.</p>
                                                )}
                                            </div>

                                            {/* Resources */}
                                            <div>
                                                <h4 className="text-[10px] font-bold text-stone-500 uppercase tracking-widest mb-2 flex items-center gap-1">
                                                    <FileText className="w-3 h-3" /> Resources ({server.resources?.length || 0})
                                                </h4>
                                                {(server.resources?.length || 0) > 0 ? (
                                                    <div className="space-y-1">
                                                        {server.resources?.map((res: any, i: number) => (
                                                            <div key={i} className="px-2.5 py-1.5 rounded-lg bg-white border border-stone-200 text-xs">
                                                                <div className="font-medium text-stone-800">{res.name || res}</div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <p className="text-xs text-stone-400 italic">No resources available.</p>
                                                )}
                                            </div>

                                            {/* Prompts */}
                                            <div>
                                                <h4 className="text-[10px] font-bold text-stone-500 uppercase tracking-widest mb-2 flex items-center gap-1">
                                                    <MessageSquareText className="w-3 h-3" /> Prompts ({server.prompts?.length || 0})
                                                </h4>
                                                {(server.prompts?.length || 0) > 0 ? (
                                                    <div className="space-y-1">
                                                        {server.prompts?.map((prompt: any, i: number) => (
                                                            <div key={i} className="px-2.5 py-1.5 rounded-lg bg-white border border-stone-200 text-xs">
                                                                <div className="font-medium text-stone-800">{prompt.name || prompt}</div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <p className="text-xs text-stone-400 italic">No prompts available.</p>
                                                )}
                                            </div>
                                        </div>

                                        {/* Server ID */}
                                        <div className="pt-2 border-t border-stone-200">
                                            <span className="text-[10px] text-stone-400 font-mono">ID: {server.id}</span>
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
