"use client";

import { useState, useEffect, useCallback } from "react";
import {
    Bot, Plus, Search, Zap, Crown, Briefcase, Code2, Megaphone,
    DollarSign, Users, ShieldCheck, BarChart3, HeartHandshake,
    BookOpen, Star, ChevronDown, ChevronUp, Trash2, Copy, X,
    CheckCircle, AlertCircle, Package, Sparkles, Pencil, RefreshCw,
    LayoutGrid, List,
} from "lucide-react";
import { agentTemplatesApi, agentsApi, AgentTemplate, Agent } from "@/lib/api";

// All valid tool IDs grouped by category
const TOOL_GROUPS: Record<string, string[]> = {
    "Tasks": ["create_task", "list_tasks", "update_task", "get_task"],
    "Collaboration": ["start_discussion", "ask_agent", "control_agent", "request_approval"],
    "Memory": ["save_memory", "search_memory"],
    "Agent Factory": ["create_agent_from_template", "list_agent_templates", "archive_agent"],
    "Files": ["read_file", "write_file", "list_directory", "search_files"],
    "Shell": ["run_shell_command", "get_system_info", "list_processes"],
    "GitHub": ["create_github_issue", "create_github_pr", "commit_and_push"],
    "Knowledge Base": ["search_knowledge_base", "ingest_url_to_kb"],
    "Web": ["scrape_webpage"],
    "Data": ["analyze_data", "append_to_google_sheet"],
    "Email": ["send_email", "read_emails"],
    "Webhooks": ["call_webhook"],
};

// Map icon name string → Lucide component
const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
    Crown, Briefcase, Code2, Megaphone, DollarSign, Users, ShieldCheck,
    BarChart3, HeartHandshake, Search, Bot, BookOpen,
};

const CATEGORY_LABELS: Record<string, string> = {
    all: "All",
    leadership: "Leadership",
    management: "Management",
    engineering: "Engineering",
    marketing: "Marketing",
    finance: "Finance",
    research: "Research",
    operations: "Operations",
    security: "Security",
    data: "Data",
    general: "General",
    custom: "Custom",
};

function TemplateIcon({ icon, color, size = "md" }: { icon: string | null; color: string | null; size?: "sm" | "md" | "lg" }) {
    const Icon = (icon && ICON_MAP[icon]) ? ICON_MAP[icon] : Bot;
    const sizeClass = size === "sm" ? "w-8 h-8" : size === "lg" ? "w-14 h-14" : "w-10 h-10";
    const iconSize = size === "sm" ? "w-4 h-4" : size === "lg" ? "w-7 h-7" : "w-5 h-5";
    return (
        <div
            className={`${sizeClass} rounded-xl flex items-center justify-center flex-shrink-0`}
            style={{ backgroundColor: (color || "#6366f1") + "20", border: `1px solid ${color || "#6366f1"}40` }}
        >
            <Icon className={iconSize} style={{ color: color || "#6366f1" }} />
        </div>
    );
}

interface InstantiateModalProps {
    template: AgentTemplate;
    onClose: () => void;
    onSuccess: (agent: Agent) => void;
}

function InstantiateModal({ template, onClose, onSuccess }: InstantiateModalProps) {
    const [name, setName] = useState(`${template.name} ${new Date().toLocaleDateString("en", { month: "short", day: "numeric" })}`);
    const [customInstructions, setCustomInstructions] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (!name.trim()) return;
        setLoading(true);
        setError("");
        try {
            const agent = await agentTemplatesApi.instantiate(template.id, {
                name: name.trim(),
                custom_instructions: customInstructions.trim() || undefined,
            });
            onSuccess(agent);
        } catch (err: any) {
            setError(err.message || "Failed to create agent");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
                <div className="p-6 border-b border-stone-100">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <TemplateIcon icon={template.icon} color={template.color} size="sm" />
                            <div>
                                <h2 className="text-lg font-semibold text-stone-900">Create from Template</h2>
                                <p className="text-sm text-stone-500">{template.name}</p>
                            </div>
                        </div>
                        <button onClick={onClose} className="p-2 hover:bg-stone-100 rounded-lg text-stone-400">
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                </div>
                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">Agent Name *</label>
                        <input
                            type="text"
                            value={name}
                            onChange={e => setName(e.target.value)}
                            required
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            placeholder="e.g. Marketing Bot"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">
                            Custom Instructions <span className="text-stone-400">(optional)</span>
                        </label>
                        <textarea
                            value={customInstructions}
                            onChange={e => setCustomInstructions(e.target.value)}
                            rows={3}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 resize-none"
                            placeholder="Additional instructions to append to the template's system prompt..."
                        />
                    </div>
                    <div className="bg-stone-50 rounded-lg p-3 text-xs text-stone-500 space-y-1">
                        <p><strong>Provider:</strong> {template.default_llm_provider} / {template.default_llm_model}</p>
                        <p><strong>Tools:</strong> {template.default_tools.length > 0 ? template.default_tools.join(", ") : "None"}</p>
                    </div>
                    {error && (
                        <div className="flex items-center gap-2 text-red-600 text-sm bg-red-50 rounded-lg p-3">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" />
                            {error}
                        </div>
                    )}
                    <div className="flex gap-3 pt-2">
                        <button type="button" onClick={onClose} className="flex-1 px-4 py-2 border border-stone-200 rounded-lg text-sm text-stone-700 hover:bg-stone-50">
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={loading || !name.trim()}
                            className="flex-1 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50"
                        >
                            {loading ? "Creating..." : "Create Agent"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

interface CreateTemplateModalProps {
    agents: Agent[];
    onClose: () => void;
    onSuccess: (tpl: AgentTemplate) => void;
}

function CreateTemplateModal({ agents, onClose, onSuccess }: CreateTemplateModalProps) {
    const [mode, setMode] = useState<"from-agent" | "custom">("from-agent");
    const [selectedAgentId, setSelectedAgentId] = useState("");
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [category, setCategory] = useState("custom");
    const [tags, setTags] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        if (!name.trim()) return;
        setLoading(true);
        setError("");
        try {
            let tpl: AgentTemplate;
            if (mode === "from-agent" && selectedAgentId) {
                tpl = await agentTemplatesApi.fromAgent(selectedAgentId, {
                    name: name.trim(),
                    description: description.trim() || undefined,
                    category,
                    tags: tags.split(",").map(t => t.trim()).filter(Boolean),
                });
            } else {
                tpl = await agentTemplatesApi.create({
                    name: name.trim(),
                    description: description.trim() || undefined,
                    category,
                    tags: tags.split(",").map(t => t.trim()).filter(Boolean),
                    system_prompt: "You are a helpful AI assistant.",
                    default_tools: [],
                    default_llm_provider: "ollama",
                    default_llm_model: "llama3",
                    temperature: 0.7,
                });
            }
            onSuccess(tpl);
        } catch (err: any) {
            setError(err.message || "Failed to create template");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
                <div className="p-6 border-b border-stone-100 flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-stone-900">Create Template</h2>
                    <button onClick={onClose} className="p-2 hover:bg-stone-100 rounded-lg text-stone-400"><X className="w-5 h-5" /></button>
                </div>
                <div className="px-6 pt-4 flex gap-2">
                    {(["from-agent", "custom"] as const).map(m => (
                        <button
                            key={m}
                            onClick={() => setMode(m)}
                            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${mode === m ? "bg-stone-700 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"}`}
                        >
                            {m === "from-agent" ? "From Existing Agent" : "Custom Template"}
                        </button>
                    ))}
                </div>
                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    {mode === "from-agent" && (
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">Source Agent *</label>
                            <select
                                value={selectedAgentId}
                                onChange={e => setSelectedAgentId(e.target.value)}
                                required={mode === "from-agent"}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            >
                                <option value="">Select an agent...</option>
                                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                            </select>
                        </div>
                    )}
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">Template Name *</label>
                        <input
                            type="text"
                            value={name}
                            onChange={e => setName(e.target.value)}
                            required
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            placeholder="My Custom Template"
                        />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-stone-700 mb-1">Description</label>
                        <textarea
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            rows={2}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 resize-none"
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">Category</label>
                            <select
                                value={category}
                                onChange={e => setCategory(e.target.value)}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            >
                                {Object.entries(CATEGORY_LABELS).filter(([k]) => k !== "all").map(([k, v]) => (
                                    <option key={k} value={k}>{v}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">Tags (comma-sep)</label>
                            <input
                                type="text"
                                value={tags}
                                onChange={e => setTags(e.target.value)}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                placeholder="ai, automation"
                            />
                        </div>
                    </div>
                    {error && (
                        <div className="flex items-center gap-2 text-red-600 text-sm bg-red-50 rounded-lg p-3">
                            <AlertCircle className="w-4 h-4 flex-shrink-0" />{error}
                        </div>
                    )}
                    <div className="flex gap-3 pt-2">
                        <button type="button" onClick={onClose} className="flex-1 px-4 py-2 border border-stone-200 rounded-lg text-sm text-stone-700 hover:bg-stone-50">Cancel</button>
                        <button type="submit" disabled={loading || !name.trim()} className="flex-1 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50">
                            {loading ? "Saving..." : "Save Template"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

interface EditTemplateModalProps {
    template: AgentTemplate;
    onClose: () => void;
    onSuccess: (tpl: AgentTemplate) => void;
}

function EditTemplateModal({ template, onClose, onSuccess }: EditTemplateModalProps) {
    const [systemPrompt, setSystemPrompt] = useState(template.system_prompt);
    const [provider, setProvider] = useState(template.default_llm_provider);
    const [model, setModel] = useState(template.default_llm_model);
    const [temperature, setTemperature] = useState(template.temperature);
    const [selectedTools, setSelectedTools] = useState<string[]>(template.default_tools);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    function toggleTool(toolId: string) {
        setSelectedTools(prev =>
            prev.includes(toolId) ? prev.filter(t => t !== toolId) : [...prev, toolId]
        );
    }

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setLoading(true);
        setError("");
        try {
            const updated = await agentTemplatesApi.update(template.id, {
                name: template.name,
                description: template.description,
                category: template.category,
                system_prompt: systemPrompt,
                default_tools: selectedTools,
                default_llm_provider: provider,
                default_llm_model: model,
                temperature,
                role_name: template.role_name,
                icon: template.icon,
                color: template.color,
                tags: template.tags,
            });
            onSuccess(updated);
        } catch (err: any) {
            setError(err.message || "Failed to update template");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
                <div className="p-6 border-b border-stone-100 flex items-center justify-between flex-shrink-0">
                    <div className="flex items-center gap-3">
                        <TemplateIcon icon={template.icon} color={template.color} size="sm" />
                        <div>
                            <h2 className="text-lg font-semibold text-stone-900">Edit Template</h2>
                            <p className="text-sm text-stone-500">{template.name}</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-stone-100 rounded-lg text-stone-400">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0 overflow-hidden">
                    <div className="flex-1 overflow-y-auto p-6 space-y-5">
                        {/* System Prompt */}
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">System Prompt</label>
                            <textarea
                                value={systemPrompt}
                                onChange={e => setSystemPrompt(e.target.value)}
                                rows={12}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-stone-600 resize-y"
                            />
                        </div>

                        {/* Model */}
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <label className="block text-sm font-medium text-stone-700 mb-1">LLM Provider</label>
                                <input
                                    type="text"
                                    value={provider}
                                    onChange={e => setProvider(e.target.value)}
                                    className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                    placeholder="groq"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-stone-700 mb-1">LLM Model</label>
                                <input
                                    type="text"
                                    value={model}
                                    onChange={e => setModel(e.target.value)}
                                    className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                    placeholder="kimi-k2-instruct"
                                />
                            </div>
                        </div>

                        {/* Temperature */}
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-1">
                                Temperature: <span className="text-stone-700 font-semibold">{temperature.toFixed(2)}</span>
                            </label>
                            <input
                                type="range"
                                min={0} max={1} step={0.05}
                                value={temperature}
                                onChange={e => setTemperature(parseFloat(e.target.value))}
                                className="w-full accent-stone-700"
                            />
                            <div className="flex justify-between text-[10px] text-stone-400 mt-0.5">
                                <span>Precise (0)</span>
                                <span>Creative (1)</span>
                            </div>
                        </div>

                        {/* Tools */}
                        <div>
                            <label className="block text-sm font-medium text-stone-700 mb-2">
                                Tools <span className="text-stone-400 font-normal">({selectedTools.length} selected)</span>
                            </label>
                            <div className="space-y-3 border border-stone-200 rounded-lg p-3 max-h-60 overflow-y-auto">
                                {Object.entries(TOOL_GROUPS).map(([group, tools]) => (
                                    <div key={group}>
                                        <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-1">{group}</p>
                                        <div className="flex flex-wrap gap-1.5">
                                            {tools.map(toolId => (
                                                <button
                                                    key={toolId}
                                                    type="button"
                                                    onClick={() => toggleTool(toolId)}
                                                    className={`px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
                                                        selectedTools.includes(toolId)
                                                            ? "bg-stone-700 text-white"
                                                            : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                                                    }`}
                                                >
                                                    {toolId}
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="p-6 border-t border-stone-100 flex-shrink-0">
                        {error && (
                            <div className="flex items-center gap-2 text-red-600 text-sm bg-red-50 rounded-lg p-3 mb-3">
                                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                                {error}
                            </div>
                        )}
                        <div className="flex gap-3">
                            <button type="button" onClick={onClose} className="flex-1 px-4 py-2 border border-stone-200 rounded-lg text-sm text-stone-700 hover:bg-stone-50">
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={loading}
                                className="flex-1 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50"
                            >
                                {loading ? "Saving..." : "Save Changes"}
                            </button>
                        </div>
                    </div>
                </form>
            </div>
        </div>
    );
}

interface TemplateCardProps {
    template: AgentTemplate;
    onInstantiate: (tpl: AgentTemplate) => void;
    onDelete: (tpl: AgentTemplate) => void;
    onEdit: (tpl: AgentTemplate) => void;
}

function TemplateCard({ template, onInstantiate, onDelete, onEdit }: TemplateCardProps) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="bg-white border border-stone-200 rounded-xl hover:shadow-md transition-shadow overflow-hidden">
            <div className="p-5">
                <div className="flex items-start gap-3">
                    <TemplateIcon icon={template.icon} color={template.color} />
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="font-semibold text-stone-900 text-sm">{template.name}</h3>
                            {template.is_builtin && (
                                <span className="text-[10px] font-medium bg-stone-100 text-stone-700 border border-stone-300 px-1.5 py-0.5 rounded-full">Built-in</span>
                            )}
                        </div>
                        <p className="text-xs text-stone-500 mt-0.5 capitalize">{template.category}</p>
                    </div>
                    <div className="flex items-center gap-1 text-stone-400 text-xs flex-shrink-0">
                        <Zap className="w-3 h-3" />
                        <span>{template.usage_count}</span>
                    </div>
                </div>

                <p className="text-xs text-stone-600 mt-3 line-clamp-2 leading-relaxed">
                    {template.description || "No description provided."}
                </p>

                {template.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                        {template.tags.map(tag => (
                            <span key={tag} className="text-[10px] bg-stone-100 text-stone-500 px-1.5 py-0.5 rounded-full">{tag}</span>
                        ))}
                    </div>
                )}

                {expanded && (
                    <div className="mt-3 pt-3 border-t border-stone-100 space-y-2 text-xs text-stone-600">
                        <div>
                            <span className="font-medium text-stone-700">Model:</span> {template.default_llm_provider}/{template.default_llm_model}
                        </div>
                        {template.default_tools.length > 0 && (
                            <div>
                                <span className="font-medium text-stone-700">Tools:</span>{" "}
                                <span className="text-stone-500">{template.default_tools.join(", ")}</span>
                            </div>
                        )}
                        {template.role_name && (
                            <div>
                                <span className="font-medium text-stone-700">Role:</span> {template.role_name}
                            </div>
                        )}
                    </div>
                )}

                <div className="flex items-center gap-2 mt-4">
                    <button
                        onClick={() => onInstantiate(template)}
                        className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-stone-700 text-white rounded-lg text-xs font-medium hover:bg-stone-700 transition-colors"
                    >
                        <Plus className="w-3.5 h-3.5" />
                        Use Template
                    </button>
                    <button
                        onClick={() => onEdit(template)}
                        title="Edit template"
                        className="px-2 py-1.5 border border-stone-200 rounded-lg text-stone-500 hover:bg-stone-50 text-xs"
                    >
                        <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button
                        onClick={() => setExpanded(!expanded)}
                        className="px-2 py-1.5 border border-stone-200 rounded-lg text-stone-500 hover:bg-stone-50 text-xs"
                    >
                        {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                    {!template.is_builtin && (
                        <button
                            onClick={() => onDelete(template)}
                            className="px-2 py-1.5 border border-red-200 rounded-lg text-red-400 hover:bg-red-50 text-xs"
                        >
                            <Trash2 className="w-3.5 h-3.5" />
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

export default function TemplatesPage() {
    const [templates, setTemplates] = useState<AgentTemplate[]>([]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [categoryFilter, setCategoryFilter] = useState("all");
    const [instantiateTarget, setInstantiateTarget] = useState<AgentTemplate | null>(null);
    const [editTarget, setEditTarget] = useState<AgentTemplate | null>(null);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [successMsg, setSuccessMsg] = useState("");
    const [reseeding, setReseeding] = useState(false);
    const [viewMode, setViewMode] = useState<"grid" | "table">("table");

    const loadTemplates = useCallback(async () => {
        setLoading(true);
        try {
            const [tpls, agentList] = await Promise.all([
                agentTemplatesApi.list(),
                agentsApi.list(),
            ]);
            setTemplates(tpls);
            setAgents(agentList);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadTemplates(); }, [loadTemplates]);

    const filtered = templates.filter(t => {
        const matchesSearch = !search || t.name.toLowerCase().includes(search.toLowerCase()) ||
            (t.description || "").toLowerCase().includes(search.toLowerCase()) ||
            t.tags.some(tag => tag.toLowerCase().includes(search.toLowerCase()));
        const matchesCategory = categoryFilter === "all" || t.category === categoryFilter;
        return matchesSearch && matchesCategory;
    });

    const categories = ["all", ...Array.from(new Set(templates.map(t => t.category))).sort()];

    async function handleDelete(tpl: AgentTemplate) {
        if (!confirm(`Delete template "${tpl.name}"? This cannot be undone.`)) return;
        await agentTemplatesApi.delete(tpl.id);
        setTemplates(prev => prev.filter(t => t.id !== tpl.id));
    }

    function handleInstantiateSuccess(agent: Agent) {
        setInstantiateTarget(null);
        setSuccessMsg(`Agent "${agent.name}" created successfully! Start it from the Agents page.`);
        setTimeout(() => setSuccessMsg(""), 5000);
    }

    function handleCreateSuccess(tpl: AgentTemplate) {
        setShowCreateModal(false);
        setTemplates(prev => [tpl, ...prev]);
        setSuccessMsg(`Template "${tpl.name}" saved!`);
        setTimeout(() => setSuccessMsg(""), 4000);
    }

    function handleEditSuccess(tpl: AgentTemplate) {
        setEditTarget(null);
        setTemplates(prev => prev.map(t => t.id === tpl.id ? tpl : t));
        setSuccessMsg(`Template "${tpl.name}" updated!`);
        setTimeout(() => setSuccessMsg(""), 4000);
    }

    async function handleReseed() {
        if (!confirm("Reseed all builtin templates? This will overwrite any edits you made to builtin templates with the latest defaults.")) return;
        setReseeding(true);
        try {
            const result = await agentTemplatesApi.reseed();
            await loadTemplates();
            setSuccessMsg(`Reseeded: ${result.updated.length} updated, ${result.created.length} created.`);
            setTimeout(() => setSuccessMsg(""), 5000);
        } catch {
            setSuccessMsg("Reseed failed.");
        } finally {
            setReseeding(false);
        }
    }

    const builtinCount = templates.filter(t => t.is_builtin).length;
    const customCount = templates.filter(t => !t.is_builtin).length;

    return (
        <div className="flex-1 flex flex-col min-h-0 overflow-auto bg-[#F8F9FA]">
            {/* Header */}
            <div className="bg-white border-b border-stone-200 px-6 py-4">
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-xl font-bold text-stone-900 flex items-center gap-2">
                            <Package className="w-5 h-5 text-stone-700" />
                            Agent Templates
                        </h1>
                        <p className="text-sm text-stone-500 mt-0.5">
                            {builtinCount} built-in · {customCount} custom · Spin up agents in seconds
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        {/* View Toggle */}
                        <div className="flex items-center bg-stone-100 rounded-lg p-0.5">
                            <button
                                onClick={() => setViewMode("grid")}
                                className={`p-1.5 rounded-md transition-colors ${viewMode === "grid" ? "bg-white text-stone-800 shadow-sm" : "text-stone-400 hover:text-stone-600"}`}
                                title="Grid View"
                            >
                                <LayoutGrid className="w-4 h-4" />
                            </button>
                            <button
                                onClick={() => setViewMode("table")}
                                className={`p-1.5 rounded-md transition-colors ${viewMode === "table" ? "bg-white text-stone-800 shadow-sm" : "text-stone-400 hover:text-stone-600"}`}
                                title="List View"
                            >
                                <List className="w-4 h-4" />
                            </button>
                        </div>
                        <button
                            onClick={handleReseed}
                            disabled={reseeding}
                            title="Reseed builtin templates with latest prompts and models"
                            className="flex items-center gap-2 px-3 py-2 border border-stone-200 text-stone-600 rounded-xl text-sm font-medium hover:bg-stone-50 transition-colors disabled:opacity-50"
                        >
                            <RefreshCw className={`w-4 h-4 ${reseeding ? "animate-spin" : ""}`} />
                            Reseed
                        </button>
                        <button
                            onClick={() => setShowCreateModal(true)}
                            className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white rounded-xl text-sm font-medium hover:bg-stone-700 transition-colors"
                        >
                            <Plus className="w-4 h-4" />
                            New Template
                        </button>
                    </div>
                </div>

                {/* Search + Category Filter */}
                <div className="flex items-center gap-3 mt-4">
                    <div className="relative flex-1 max-w-xs">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
                        <input
                            type="text"
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            placeholder="Search templates..."
                            className="w-full pl-9 pr-3 py-2 border border-stone-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 bg-stone-50"
                        />
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                        {categories.map(cat => (
                            <button
                                key={cat}
                                onClick={() => setCategoryFilter(cat)}
                                className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${categoryFilter === cat
                                    ? "bg-stone-700 text-white"
                                    : "bg-white border border-stone-200 text-stone-600 hover:bg-stone-50"
                                    }`}
                            >
                                {CATEGORY_LABELS[cat] || cat}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Success Banner */}
            {successMsg && (
                <div className="mx-6 mt-4 flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl px-4 py-3 text-sm text-green-700">
                    <CheckCircle className="w-4 h-4 flex-shrink-0" />
                    {successMsg}
                </div>
            )}

            {/* Content */}
            <div className="flex-1 p-6">
                {loading ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {Array.from({ length: 8 }).map((_, i) => (
                            <div key={i} className="bg-white border border-stone-200 rounded-xl p-5 animate-pulse">
                                <div className="flex gap-3">
                                    <div className="w-10 h-10 bg-stone-200 rounded-xl" />
                                    <div className="flex-1 space-y-2">
                                        <div className="h-4 bg-stone-200 rounded w-2/3" />
                                        <div className="h-3 bg-stone-200 rounded w-1/3" />
                                    </div>
                                </div>
                                <div className="mt-3 space-y-1">
                                    <div className="h-3 bg-stone-200 rounded" />
                                    <div className="h-3 bg-stone-200 rounded w-4/5" />
                                </div>
                            </div>
                        ))}
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-stone-400">
                        <Sparkles className="w-12 h-12 mb-3" />
                        <p className="text-base font-medium">No templates found</p>
                        <p className="text-sm mt-1">
                            {search ? "Try a different search term" : "Create your first custom template"}
                        </p>
                    </div>
                ) : viewMode === "grid" ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {filtered.map(tpl => (
                            <TemplateCard
                                key={tpl.id}
                                template={tpl}
                                onInstantiate={setInstantiateTarget}
                                onDelete={handleDelete}
                                onEdit={setEditTarget}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
                        <table className="w-full text-left text-sm whitespace-nowrap">
                            <thead>
                                <tr className="border-b border-stone-200 text-stone-500">
                                    <th className="px-4 py-3 font-medium">Template</th>
                                    <th className="px-4 py-3 font-medium">Category</th>
                                    <th className="px-4 py-3 font-medium">Model</th>
                                    <th className="px-4 py-3 font-medium">Tools</th>
                                    <th className="px-4 py-3 font-medium text-center">Used</th>
                                    <th className="px-4 py-3 font-medium text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-stone-100">
                                {filtered.map(tpl => (
                                    <tr key={tpl.id} className="hover:bg-stone-50 transition-colors group">
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-3">
                                                <TemplateIcon icon={tpl.icon} color={tpl.color} size="sm" />
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <span className="font-semibold text-stone-900">{tpl.name}</span>
                                                        {tpl.is_builtin && (
                                                            <span className="text-[9px] font-medium bg-stone-100 text-stone-600 border border-stone-200 px-1.5 py-0.5 rounded-full">Built-in</span>
                                                        )}
                                                    </div>
                                                    {tpl.description && (
                                                        <p className="text-[11px] text-stone-500 truncate max-w-[250px]">{tpl.description}</p>
                                                    )}
                                                </div>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className="text-xs text-stone-600 capitalize">{tpl.category}</span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center gap-1.5">
                                                <span className="px-1.5 py-0.5 rounded bg-stone-100 text-stone-700 text-[10px] font-semibold uppercase">{tpl.default_llm_provider}</span>
                                                <span className="text-xs text-stone-500 font-mono truncate max-w-[100px]" title={tpl.default_llm_model}>{tpl.default_llm_model}</span>
                                            </div>
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className="text-xs text-stone-500">{tpl.default_tools.length} tools</span>
                                        </td>
                                        <td className="px-4 py-3 text-center">
                                            <div className="flex items-center justify-center gap-1 text-stone-400 text-xs">
                                                <Zap className="w-3 h-3" />
                                                {tpl.usage_count}
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 text-right">
                                            <div className="flex items-center justify-end gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                                <button
                                                    onClick={() => setInstantiateTarget(tpl)}
                                                    className="px-2.5 py-1 bg-stone-800 text-white rounded-lg text-xs font-medium hover:bg-stone-700 transition-colors flex items-center gap-1"
                                                >
                                                    <Plus className="w-3 h-3" /> Use
                                                </button>
                                                <button
                                                    onClick={() => setEditTarget(tpl)}
                                                    className="p-1.5 border border-stone-200 rounded-lg text-stone-500 hover:bg-stone-50"
                                                    title="Edit"
                                                >
                                                    <Pencil className="w-3.5 h-3.5" />
                                                </button>
                                                {!tpl.is_builtin && (
                                                    <button
                                                        onClick={() => handleDelete(tpl)}
                                                        className="p-1.5 border border-red-200 rounded-lg text-red-400 hover:bg-red-50"
                                                        title="Delete"
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" />
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Modals */}
            {instantiateTarget && (
                <InstantiateModal
                    template={instantiateTarget}
                    onClose={() => setInstantiateTarget(null)}
                    onSuccess={handleInstantiateSuccess}
                />
            )}
            {editTarget && (
                <EditTemplateModal
                    template={editTarget}
                    onClose={() => setEditTarget(null)}
                    onSuccess={handleEditSuccess}
                />
            )}
            {showCreateModal && (
                <CreateTemplateModal
                    agents={agents}
                    onClose={() => setShowCreateModal(false)}
                    onSuccess={handleCreateSuccess}
                />
            )}
        </div>
    );
}
