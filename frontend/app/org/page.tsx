"use client";

import { useEffect, useState, useCallback } from "react";
import {
    Users, Crown, Briefcase, Code2, Megaphone, DollarSign,
    ShieldCheck, BarChart3, HeartHandshake, Search, Plus,
    ChevronDown, ChevronRight, Loader2, X, Edit3, Trash2,
    Bot, GitMerge, AlertCircle, Check, Pencil, RefreshCw, type LucideIcon,
} from "lucide-react";
import {
    agentsApi, rolesApi, teamsApi, orgApi,
    type Agent, type AgentRole, type RoleTemplate, type Team, type OrgChartNode,
} from "@/lib/api";

// ─── Icon map ────────────────────────────────────────────────────────────────
const ICON_MAP: Record<string, LucideIcon> = {
    Crown, Briefcase, Code2, Megaphone, DollarSign,
    ShieldCheck, BarChart3, HeartHandshake, Search, Users, Bot,
};

function RoleIcon({ icon, className }: { icon: string | null | undefined; className?: string }) {
    const Icon: LucideIcon = (icon && ICON_MAP[icon]) ? ICON_MAP[icon] : Bot;
    return <Icon className={className} />;
}

// ─── Status dot ──────────────────────────────────────────────────────────────
function StatusDot({ status }: { status: string }) {
    const color = status === "running" ? "bg-green-400" : status === "error" ? "bg-red-400" : "bg-stone-300";
    return <span className={`w-2 h-2 rounded-full inline-block ${color}`} />;
}

// ─── Org Chart Node Card ──────────────────────────────────────────────────────
function OrgNode({
    node,
    children,
    depth = 0,
}: {
    node: OrgChartNode;
    children?: React.ReactNode;
    depth?: number;
}) {
    const [expanded, setExpanded] = useState(depth < 2);
    const hasChildren = !!children;

    return (
        <div className="flex flex-col items-center">
            {/* Card */}
            <div
                className="relative bg-white border-2 rounded-2xl shadow-sm hover:shadow-md transition-all duration-200 px-4 py-3 min-w-[180px] max-w-[220px] cursor-default"
                style={{ borderColor: node.role_color || "#e2e8f0" }}
            >
                {/* Role badge */}
                {node.role_name && (
                    <div
                        className="absolute -top-3 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider text-white whitespace-nowrap"
                        style={{ backgroundColor: node.role_color || "#64748b" }}
                    >
                        <span className="flex items-center gap-1">
                            <RoleIcon icon={node.role_icon} className="w-2.5 h-2.5" />
                            {node.role_name}
                        </span>
                    </div>
                )}
                <div className="flex items-center gap-2 mt-1">
                    <StatusDot status={node.status} />
                    <span className="font-semibold text-stone-800 text-sm truncate">{node.name}</span>
                </div>
                {node.skills && node.skills.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                        {node.skills.slice(0, 3).map(s => (
                            <span key={s} className="bg-stone-100 text-stone-500 text-[9px] px-1.5 py-0.5 rounded-full">
                                {s}
                            </span>
                        ))}
                        {node.skills.length > 3 && (
                            <span className="text-[9px] text-stone-400">+{node.skills.length - 3}</span>
                        )}
                    </div>
                )}
                {/* Expand/collapse button */}
                {hasChildren && (
                    <button
                        onClick={() => setExpanded(!expanded)}
                        className="absolute -bottom-3 left-1/2 -translate-x-1/2 bg-white border border-stone-200 rounded-full w-6 h-6 flex items-center justify-center text-stone-400 hover:text-stone-700 shadow-sm"
                    >
                        {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                    </button>
                )}
            </div>

            {/* Children */}
            {hasChildren && expanded && (
                <div className="mt-6 relative">
                    {/* Vertical line from parent */}
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-0.5 h-4 bg-stone-200" />
                    <div className="flex gap-6 items-start pt-4">
                        {children}
                    </div>
                </div>
            )}
        </div>
    );
}

// ─── Recursive tree builder ───────────────────────────────────────────────────
function buildTree(
    nodes: OrgChartNode[],
    parentId: string | null,
    depth = 0
): React.ReactNode {
    const children = nodes.filter(n => n.reports_to_agent_id === parentId);
    if (children.length === 0) return null;
    return (
        <>
            {children.map(node => (
                <OrgNode key={node.id} node={node} depth={depth}>
                    {buildTree(nodes, node.id, depth + 1)}
                </OrgNode>
            ))}
        </>
    );
}

// ─── Role Modal (create / edit) ───────────────────────────────────────────────
const ROLE_TOOL_GROUPS: Record<string, string[]> = {
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
};

const ROLE_ICON_OPTIONS = ["Crown", "Briefcase", "Code2", "Megaphone", "DollarSign", "Users", "ShieldCheck", "BarChart3", "HeartHandshake", "Search", "Bot"];

function RoleModal({
    role,
    onClose,
    onSave,
}: {
    role?: AgentRole | null;
    onClose: () => void;
    onSave: (data: Partial<AgentRole>) => Promise<void>;
}) {
    const [name, setName] = useState(role?.name || "");
    const [description, setDescription] = useState(role?.description || "");
    const [prompt, setPrompt] = useState(role?.system_prompt_template || "");
    const [selectedTools, setSelectedTools] = useState<string[]>(role?.default_tools || []);
    const [reportsTo, setReportsTo] = useState(role?.reports_to_role || "");
    const [color, setColor] = useState(role?.color || "#6366f1");
    const [icon, setIcon] = useState(role?.icon || "Bot");
    const [canCreateAgents, setCanCreateAgents] = useState<boolean>((role?.permissions as any)?.can_create_agents ?? false);
    const [canApprove, setCanApprove] = useState<boolean>((role?.permissions as any)?.can_approve ?? false);
    const [budgetLimit, setBudgetLimit] = useState<string>(String((role?.permissions as any)?.budget_limit ?? ""));
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    function toggleTool(t: string) {
        setSelectedTools(prev => prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t]);
    }

    async function handleSave() {
        if (!name.trim()) return;
        setSaving(true);
        setError("");
        try {
            await onSave({
                name: name.trim(),
                description: description.trim() || undefined,
                system_prompt_template: prompt,
                default_tools: selectedTools,
                reports_to_role: reportsTo || undefined,
                color,
                icon,
                permissions: {
                    can_create_agents: canCreateAgents,
                    can_approve: canApprove,
                    budget_limit: budgetLimit ? Number(budgetLimit) : null,
                },
            });
        } catch (err: any) {
            setError(err.message || "Failed to save role");
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] flex flex-col">
                <div className="p-5 border-b border-stone-100 flex items-center justify-between flex-shrink-0">
                    <h2 className="text-lg font-semibold text-stone-900">{role ? "Edit Role" : "New Role"}</h2>
                    <button onClick={onClose} className="p-1.5 hover:bg-stone-100 rounded-lg"><X className="w-4 h-4" /></button>
                </div>

                <div className="flex-1 overflow-y-auto p-5 space-y-4">
                    {/* Name + color + icon */}
                    <div className="flex gap-3">
                        <div className="flex-1">
                            <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Name *</label>
                            <input
                                value={name}
                                onChange={e => setName(e.target.value)}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                placeholder="e.g. Software Engineer"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Color</label>
                            <input type="color" value={color} onChange={e => setColor(e.target.value)} className="h-9 w-12 rounded-lg border border-stone-200 cursor-pointer" />
                        </div>
                    </div>

                    {/* Description */}
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Description</label>
                        <input
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            placeholder="What does this role do?"
                        />
                    </div>

                    {/* Icon */}
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Icon</label>
                        <div className="flex flex-wrap gap-2">
                            {ROLE_ICON_OPTIONS.map(ic => {
                                const Icon = ICON_MAP[ic] || Bot;
                                return (
                                    <button
                                        key={ic}
                                        type="button"
                                        onClick={() => setIcon(ic)}
                                        className={`p-2 rounded-lg border transition-colors ${icon === ic ? "border-stone-600 bg-stone-100" : "border-stone-200 hover:bg-stone-50"}`}
                                        style={icon === ic ? { color } : {}}
                                    >
                                        <Icon className="w-4 h-4" />
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Reports to */}
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Reports To</label>
                        <input
                            value={reportsTo}
                            onChange={e => setReportsTo(e.target.value)}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            placeholder="e.g. CEO (leave blank for top-level)"
                        />
                    </div>

                    {/* System prompt */}
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">System Prompt</label>
                        <textarea
                            value={prompt}
                            onChange={e => setPrompt(e.target.value)}
                            rows={8}
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-stone-600 resize-y"
                            placeholder="You are a..."
                        />
                    </div>

                    {/* Tools */}
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-2 uppercase tracking-wide">Default Tools ({selectedTools.length})</label>
                        <div className="space-y-2 border border-stone-200 rounded-lg p-3 max-h-48 overflow-y-auto">
                            {Object.entries(ROLE_TOOL_GROUPS).map(([group, tools]) => (
                                <div key={group}>
                                    <p className="text-[10px] font-semibold text-stone-400 uppercase tracking-wide mb-1">{group}</p>
                                    <div className="flex flex-wrap gap-1.5">
                                        {tools.map(t => (
                                            <button
                                                key={t} type="button" onClick={() => toggleTool(t)}
                                                className={`px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${selectedTools.includes(t) ? "bg-stone-700 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"}`}
                                            >{t}</button>
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Permissions */}
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-2 uppercase tracking-wide">Permissions</label>
                        <div className="space-y-2 p-3 border border-stone-200 rounded-lg">
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" checked={canCreateAgents} onChange={e => setCanCreateAgents(e.target.checked)} className="rounded" />
                                <span className="text-sm text-stone-700">Can create agents</span>
                            </label>
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input type="checkbox" checked={canApprove} onChange={e => setCanApprove(e.target.checked)} className="rounded" />
                                <span className="text-sm text-stone-700">Can approve requests</span>
                            </label>
                            <div className="flex items-center gap-2">
                                <span className="text-sm text-stone-700">Budget limit ($)</span>
                                <input
                                    type="number" value={budgetLimit} onChange={e => setBudgetLimit(e.target.value)}
                                    className="w-28 border border-stone-200 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                    placeholder="Unlimited"
                                />
                            </div>
                        </div>
                    </div>
                </div>

                <div className="p-5 border-t border-stone-100 flex-shrink-0">
                    {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
                    <div className="flex gap-3">
                        <button onClick={onClose} className="flex-1 py-2 border border-stone-200 rounded-lg text-sm text-stone-600 hover:bg-stone-50">Cancel</button>
                        <button
                            onClick={handleSave}
                            disabled={!name.trim() || saving}
                            className="flex-1 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50 flex items-center justify-center gap-2"
                        >
                            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                            {role ? "Save Changes" : "Create Role"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─── Role Template Card ───────────────────────────────────────────────────────
function TemplateCard({ tpl, onUse }: { tpl: RoleTemplate; onUse: (t: RoleTemplate) => void }) {
    return (
        <div
            className="bg-white border-2 rounded-xl p-4 hover:shadow-md transition-all cursor-pointer group"
            style={{ borderColor: tpl.color || "#e2e8f0" }}
            onClick={() => onUse(tpl)}
        >
            <div className="flex items-center gap-3 mb-2">
                <div
                    className="w-9 h-9 rounded-xl flex items-center justify-center text-white"
                    style={{ backgroundColor: tpl.color || "#64748b" }}
                >
                    <RoleIcon icon={tpl.icon} className="w-5 h-5" />
                </div>
                <div>
                    <h3 className="font-semibold text-stone-800 text-sm">{tpl.name}</h3>
                    {tpl.reports_to_role && (
                        <p className="text-[10px] text-stone-400">Reports to: {tpl.reports_to_role}</p>
                    )}
                </div>
            </div>
            <p className="text-xs text-stone-500 line-clamp-2">{tpl.description}</p>
            <div className="mt-3 flex flex-wrap gap-1">
                {tpl.default_tools.slice(0, 3).map(t => (
                    <span key={t} className="bg-stone-100 text-stone-500 text-[9px] px-1.5 py-0.5 rounded">
                        {t}
                    </span>
                ))}
                {tpl.default_tools.length > 3 && (
                    <span className="text-[9px] text-stone-400">+{tpl.default_tools.length - 3}</span>
                )}
            </div>
            <div className="mt-3 text-xs text-stone-700 font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                Save as role →
            </div>
        </div>
    );
}

// ─── Assign Role Modal ────────────────────────────────────────────────────────
function AssignRoleModal({
    agents,
    roles,
    onClose,
    onSave,
}: {
    agents: Agent[];
    roles: AgentRole[];
    onClose: () => void;
    onSave: (agentId: string, roleId: string, options: { apply_prompt: boolean; apply_tools: boolean; reports_to_agent_id: string | null; skills: string[] }) => Promise<void>;
}) {
    const [agentId, setAgentId] = useState("");
    const [roleId, setRoleId] = useState("");
    const [applyPrompt, setApplyPrompt] = useState(true);
    const [applyTools, setApplyTools] = useState(true);
    const [reportsTo, setReportsTo] = useState("");
    const [skillsInput, setSkillsInput] = useState("");
    const [saving, setSaving] = useState(false);

    async function handleSave() {
        if (!agentId || !roleId) return;
        setSaving(true);
        try {
            await onSave(agentId, roleId, {
                apply_prompt: applyPrompt,
                apply_tools: applyTools,
                reports_to_agent_id: reportsTo || null,
                skills: skillsInput.split(",").map(s => s.trim()).filter(Boolean),
            });
            onClose();
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
                <div className="flex items-center justify-between mb-5">
                    <h2 className="text-lg font-semibold text-stone-900">Assign Role to Agent</h2>
                    <button onClick={onClose} className="p-1.5 hover:bg-stone-100 rounded-lg"><X className="w-4 h-4" /></button>
                </div>

                <div className="space-y-4">
                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Agent</label>
                        <select
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={agentId}
                            onChange={e => setAgentId(e.target.value)}
                        >
                            <option value="">Select agent...</option>
                            {agents.map(a => (
                                <option key={a.id} value={a.id}>{a.name}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Role</label>
                        <select
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={roleId}
                            onChange={e => setRoleId(e.target.value)}
                        >
                            <option value="">Select role...</option>
                            {roles.map(r => (
                                <option key={r.id} value={r.id}>{r.name}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Reports To</label>
                        <select
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={reportsTo}
                            onChange={e => setReportsTo(e.target.value)}
                        >
                            <option value="">None (top-level)</option>
                            {agents.filter(a => a.id !== agentId).map(a => (
                                <option key={a.id} value={a.id}>{a.name}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Skills (comma-separated)</label>
                        <input
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            placeholder="Python, React, Data Analysis..."
                            value={skillsInput}
                            onChange={e => setSkillsInput(e.target.value)}
                        />
                    </div>

                    <div className="space-y-2">
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={applyPrompt} onChange={e => setApplyPrompt(e.target.checked)} className="rounded" />
                            <span className="text-sm text-stone-700">Apply role system prompt to agent</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={applyTools} onChange={e => setApplyTools(e.target.checked)} className="rounded" />
                            <span className="text-sm text-stone-700">Apply role default tools to agent</span>
                        </label>
                    </div>
                </div>

                <div className="flex gap-3 mt-6">
                    <button
                        onClick={onClose}
                        className="flex-1 py-2 border border-stone-200 rounded-lg text-sm text-stone-600 hover:bg-stone-50"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={!agentId || !roleId || saving}
                        className="flex-1 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                        Assign Role
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Team Modal ───────────────────────────────────────────────────────────────
function TeamModal({
    team,
    agents,
    onClose,
    onSave,
}: {
    team?: Team | null;
    agents: Agent[];
    onClose: () => void;
    onSave: (data: Partial<Team>) => Promise<void>;
}) {
    const [name, setName] = useState(team?.name || "");
    const [description, setDescription] = useState(team?.description || "");
    const [sharedContext, setSharedContext] = useState(team?.shared_context || "");
    const [leadId, setLeadId] = useState(team?.lead_agent_id || "");
    const [memberIds, setMemberIds] = useState<string[]>(team?.member_agent_ids || []);
    const [color, setColor] = useState(team?.color || "#6366f1");
    const [saving, setSaving] = useState(false);

    function toggleMember(id: string) {
        setMemberIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
    }

    async function handleSave() {
        if (!name) return;
        setSaving(true);
        try {
            await onSave({ name, description: description || undefined, shared_context: sharedContext || undefined, lead_agent_id: leadId || undefined, member_agent_ids: memberIds, color });
            onClose();
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between mb-5">
                    <h2 className="text-lg font-semibold text-stone-900">{team ? "Edit Team" : "Create Team"}</h2>
                    <button onClick={onClose} className="p-1.5 hover:bg-stone-100 rounded-lg"><X className="w-4 h-4" /></button>
                </div>
                <div className="space-y-4">
                    <div className="flex gap-3">
                        <div className="flex-1">
                            <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Team Name *</label>
                            <input
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={name}
                                onChange={e => setName(e.target.value)}
                                placeholder="Engineering Team"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Color</label>
                            <input
                                type="color"
                                className="h-9 w-12 rounded-lg border border-stone-200 cursor-pointer"
                                value={color}
                                onChange={e => setColor(e.target.value)}
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Description</label>
                        <input
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            placeholder="What does this team do?"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Team Lead</label>
                        <select
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={leadId}
                            onChange={e => setLeadId(e.target.value)}
                        >
                            <option value="">None</option>
                            {agents.map(a => (
                                <option key={a.id} value={a.id}>{a.name}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1.5 uppercase tracking-wide">Members</label>
                        <div className="border border-stone-200 rounded-xl max-h-40 overflow-y-auto divide-y divide-stone-50">
                            {agents.map(a => (
                                <label key={a.id} className="flex items-center gap-3 px-3 py-2 hover:bg-stone-50 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={memberIds.includes(a.id)}
                                        onChange={() => toggleMember(a.id)}
                                        className="rounded"
                                    />
                                    <span className="text-sm text-stone-700">{a.name}</span>
                                    <StatusDot status={a.status} />
                                </label>
                            ))}
                        </div>
                        <p className="text-xs text-stone-400 mt-1">{memberIds.length} member{memberIds.length !== 1 ? "s" : ""} selected</p>
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-stone-500 mb-1 uppercase tracking-wide">Shared Context</label>
                        <textarea
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 resize-none h-20 font-mono"
                            placeholder="Context injected into all team members' prompts..."
                            value={sharedContext}
                            onChange={e => setSharedContext(e.target.value)}
                        />
                    </div>
                </div>

                <div className="flex gap-3 mt-6">
                    <button onClick={onClose} className="flex-1 py-2 border border-stone-200 rounded-lg text-sm text-stone-600 hover:bg-stone-50">Cancel</button>
                    <button
                        onClick={handleSave}
                        disabled={!name || saving}
                        className="flex-1 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                        {team ? "Save Changes" : "Create Team"}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

type Tab = "org-chart" | "roles" | "teams";

export default function OrgPage() {
    const [tab, setTab] = useState<Tab>("org-chart");
    const [agents, setAgents] = useState<Agent[]>([]);
    const [roles, setRoles] = useState<AgentRole[]>([]);
    const [templates, setTemplates] = useState<RoleTemplate[]>([]);
    const [teams, setTeams] = useState<Team[]>([]);
    const [orgNodes, setOrgNodes] = useState<OrgChartNode[]>([]);
    const [loading, setLoading] = useState(true);

    const [showAssignRole, setShowAssignRole] = useState(false);
    const [teamModal, setTeamModal] = useState<{ open: boolean; team?: Team | null }>({ open: false });
    const [roleModal, setRoleModal] = useState<{ open: boolean; role?: AgentRole | null }>({ open: false });
    const [reseeding, setReseeding] = useState(false);

    async function loadAll() {
        setLoading(true);
        try {
            const [a, r, t, tmpl, o] = await Promise.all([
                agentsApi.list(),
                rolesApi.list(),
                teamsApi.list(),
                rolesApi.templates(),
                orgApi.chart(),
            ]);
            setAgents(a);
            setRoles(r);
            setTeams(t);
            setTemplates(tmpl);
            setOrgNodes(o);
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => { loadAll(); }, []);

    async function handleSaveTemplate(tpl: RoleTemplate) {
        const existing = roles.find(r => r.name === tpl.name);
        if (existing) {
            // Open edit modal pre-filled with template data
            setRoleModal({ open: true, role: { ...existing, ...tpl, id: existing.id } as AgentRole });
            return;
        }
        await rolesApi.create(tpl);
        await loadAll();
    }

    async function handleSaveRole(data: Partial<AgentRole>) {
        if (roleModal.role?.id) {
            await rolesApi.update(roleModal.role.id, data);
        } else {
            await rolesApi.create(data);
        }
        setRoleModal({ open: false });
        await loadAll();
    }

    async function handleDeleteRole(id: string) {
        if (!confirm("Delete this role?")) return;
        await rolesApi.delete(id);
        setRoles(prev => prev.filter(r => r.id !== id));
    }

    async function handleReseedRoles() {
        if (!confirm("Update all saved roles that match a built-in template with the latest prompts and tools?")) return;
        setReseeding(true);
        try {
            const result = await rolesApi.reseed();
            await loadAll();
            alert(`Updated ${result.updated.length} role(s): ${result.updated.join(", ") || "none"}`);
        } finally {
            setReseeding(false);
        }
    }

    async function handleDeleteTeam(id: string) {
        if (!confirm("Delete this team?")) return;
        await teamsApi.delete(id);
        setTeams(prev => prev.filter(t => t.id !== id));
    }

    async function handleAssignRole(
        agentId: string,
        roleId: string,
        options: { apply_prompt: boolean; apply_tools: boolean; reports_to_agent_id: string | null; skills: string[] }
    ) {
        await orgApi.applyRole(agentId, { role_id: roleId, ...options });
        await loadAll();
    }

    async function handleSaveTeam(data: Partial<Team>) {
        if (teamModal.team) {
            await teamsApi.update(teamModal.team.id, data);
        } else {
            await teamsApi.create(data);
        }
        await loadAll();
    }

    // Build org chart tree — agents without a reports_to are roots
    const rootNodes = orgNodes.filter(n => !n.reports_to_agent_id);
    const hasOrgData = orgNodes.some(n => n.role_id || n.reports_to_agent_id);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <Loader2 className="w-6 h-6 animate-spin text-stone-600" />
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-6 py-4 border-b border-stone-200 bg-white flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-semibold text-stone-900 flex items-center gap-2">
                        <GitMerge className="w-5 h-5 text-stone-600" />
                        Organization
                    </h1>
                    <p className="text-sm text-stone-500">Roles, teams, and reporting structure for your agents</p>
                </div>
                <div className="flex gap-2">
                    {tab === "org-chart" && (
                        <button
                            onClick={() => setShowAssignRole(true)}
                            className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700"
                        >
                            <Plus className="w-4 h-4" /> Assign Role
                        </button>
                    )}
                    {tab === "roles" && (
                        <div className="flex gap-2">
                            <button
                                onClick={handleReseedRoles}
                                disabled={reseeding}
                                title="Update saved roles with latest prompts"
                                className="flex items-center gap-2 px-3 py-2 border border-stone-200 text-stone-600 rounded-lg text-sm font-medium hover:bg-stone-50 disabled:opacity-50"
                            >
                                <RefreshCw className={`w-4 h-4 ${reseeding ? "animate-spin" : ""}`} />
                                Reseed
                            </button>
                            <button
                                onClick={() => setRoleModal({ open: true, role: null })}
                                className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700"
                            >
                                <Plus className="w-4 h-4" /> New Role
                            </button>
                        </div>
                    )}
                    {tab === "teams" && (
                        <button
                            onClick={() => setTeamModal({ open: true, team: null })}
                            className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700"
                        >
                            <Plus className="w-4 h-4" /> New Team
                        </button>
                    )}
                </div>
            </div>

            {/* Tabs */}
            <div className="border-b border-stone-200 bg-white px-6">
                <div className="flex gap-6">
                    {(["org-chart", "roles", "teams"] as Tab[]).map(t => (
                        <button
                            key={t}
                            onClick={() => setTab(t)}
                            className={`py-3 text-sm font-medium border-b-2 transition-colors capitalize ${tab === t ? "border-stone-600 text-stone-700" : "border-transparent text-stone-500 hover:text-stone-700"}`}
                        >
                            {t === "org-chart" ? "Org Chart" : t.charAt(0).toUpperCase() + t.slice(1)}
                        </button>
                    ))}
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">

                {/* ─── Org Chart Tab ──────────────────────────────────────────────── */}
                {tab === "org-chart" && (
                    <div>
                        {!hasOrgData ? (
                            <div className="flex flex-col items-center justify-center py-20 text-stone-400">
                                <GitMerge className="w-14 h-14 mb-3 opacity-20" />
                                <p className="text-sm font-medium">No org structure yet</p>
                                <p className="text-xs mt-1">Assign roles to agents and set reporting lines to build your org chart</p>
                                <button
                                    onClick={() => setShowAssignRole(true)}
                                    className="mt-4 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700"
                                >
                                    Assign First Role
                                </button>
                            </div>
                        ) : (
                            <div className="overflow-x-auto pb-8">
                                {/* Legend */}
                                <div className="flex flex-wrap gap-3 mb-8">
                                    {roles.map(r => (
                                        <div key={r.id} className="flex items-center gap-1.5 text-xs text-stone-500">
                                            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: r.color || "#64748b" }} />
                                            {r.name}
                                        </div>
                                    ))}
                                </div>

                                {/* Tree */}
                                <div className="flex gap-10 justify-center">
                                    {rootNodes.length > 0 ? (
                                        rootNodes.map(node => (
                                            <OrgNode key={node.id} node={node} depth={0}>
                                                {buildTree(orgNodes, node.id, 1)}
                                            </OrgNode>
                                        ))
                                    ) : (
                                        // Show all nodes flat if no hierarchy set
                                        <div className="flex flex-wrap gap-4 justify-center">
                                            {orgNodes.map(node => (
                                                <OrgNode key={node.id} node={node} depth={0} />
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Unassigned agents */}
                        {(() => {
                            const unassigned = agents.filter(a => !orgNodes.find(n => n.id === a.id && n.role_id));
                            if (unassigned.length === 0) return null;
                            return (
                                <div className="mt-8 pt-6 border-t border-stone-200">
                                    <h3 className="text-sm font-semibold text-stone-500 mb-3 flex items-center gap-2">
                                        <AlertCircle className="w-4 h-4" />
                                        Agents without a role ({unassigned.length})
                                    </h3>
                                    <div className="flex flex-wrap gap-2">
                                        {unassigned.map(a => (
                                            <div key={a.id} className="flex items-center gap-2 bg-stone-100 text-stone-600 px-3 py-1.5 rounded-xl text-xs">
                                                <StatusDot status={a.status} />
                                                {a.name}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            );
                        })()}
                    </div>
                )}

                {/* ─── Roles Tab ─────────────────────────────────────────────────── */}
                {tab === "roles" && (
                    <div className="space-y-8 max-w-5xl">
                        {/* Saved roles */}
                        {roles.length > 0 && (
                            <div>
                                <h2 className="text-sm font-semibold text-stone-700 mb-3">Your Roles ({roles.length})</h2>
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {roles.map(role => {
                                        const agentsWithRole = agents.filter(a => (a as any).role_id === role.id);
                                        return (
                                            <div
                                                key={role.id}
                                                className="bg-white border-2 rounded-xl p-4 relative"
                                                style={{ borderColor: role.color || "#e2e8f0" }}
                                            >
                                                <div className="flex items-start justify-between mb-2">
                                                    <div className="flex items-center gap-2">
                                                        <div
                                                            className="w-8 h-8 rounded-lg flex items-center justify-center text-white"
                                                            style={{ backgroundColor: role.color || "#64748b" }}
                                                        >
                                                            <RoleIcon icon={role.icon} className="w-4 h-4" />
                                                        </div>
                                                        <div>
                                                            <h3 className="font-semibold text-stone-800 text-sm">{role.name}</h3>
                                                            {role.reports_to_role && (
                                                                <p className="text-[10px] text-stone-400">→ {role.reports_to_role}</p>
                                                            )}
                                                        </div>
                                                    </div>
                                                    <div className="flex gap-1">
                                                        <button
                                                            onClick={() => setRoleModal({ open: true, role })}
                                                            className="p-1 text-stone-300 hover:text-stone-600 rounded"
                                                            title="Edit role"
                                                        >
                                                            <Pencil className="w-3.5 h-3.5" />
                                                        </button>
                                                        <button
                                                            onClick={() => handleDeleteRole(role.id)}
                                                            className="p-1 text-stone-300 hover:text-red-400 rounded"
                                                        >
                                                            <Trash2 className="w-3.5 h-3.5" />
                                                        </button>
                                                    </div>
                                                </div>
                                                <p className="text-xs text-stone-500 line-clamp-2 mb-3">{role.description}</p>
                                                {agentsWithRole.length > 0 && (
                                                    <div className="text-xs text-stone-400">
                                                        {agentsWithRole.length} agent{agentsWithRole.length !== 1 ? "s" : ""}: {agentsWithRole.map(a => a.name).join(", ")}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {/* Templates */}
                        <div>
                            <h2 className="text-sm font-semibold text-stone-700 mb-1">Role Templates</h2>
                            <p className="text-xs text-stone-400 mb-4">Click to save a template as a reusable role in your organization</p>
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                                {templates.map(tpl => (
                                    <TemplateCard
                                        key={tpl.name}
                                        tpl={tpl}
                                        onUse={handleSaveTemplate}
                                    />
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {/* ─── Teams Tab ─────────────────────────────────────────────────── */}
                {tab === "teams" && (
                    <div className="max-w-4xl space-y-4">
                        {teams.length === 0 ? (
                            <div className="flex flex-col items-center justify-center py-20 text-stone-400">
                                <Users className="w-14 h-14 mb-3 opacity-20" />
                                <p className="text-sm font-medium">No teams yet</p>
                                <p className="text-xs mt-1">Group agents into teams with a shared mission and context</p>
                                <button
                                    onClick={() => setTeamModal({ open: true, team: null })}
                                    className="mt-4 px-4 py-2 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700"
                                >
                                    Create First Team
                                </button>
                            </div>
                        ) : (
                            teams.map(team => {
                                const members = agents.filter(a => team.member_agent_ids.includes(a.id));
                                const lead = agents.find(a => a.id === team.lead_agent_id);
                                return (
                                    <div key={team.id} className="bg-white border-l-4 rounded-xl shadow-sm p-5" style={{ borderLeftColor: team.color || "#6366f1" }}>
                                        <div className="flex items-start justify-between">
                                            <div>
                                                <h3 className="font-semibold text-stone-900">{team.name}</h3>
                                                {team.description && <p className="text-sm text-stone-500 mt-0.5">{team.description}</p>}
                                                {lead && (
                                                    <p className="text-xs text-stone-400 mt-1">Lead: <span className="font-medium text-stone-600">{lead.name}</span></p>
                                                )}
                                            </div>
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={() => setTeamModal({ open: true, team })}
                                                    className="p-1.5 text-stone-400 hover:text-stone-600 hover:bg-stone-100 rounded-lg"
                                                >
                                                    <Edit3 className="w-4 h-4" />
                                                </button>
                                                <button
                                                    onClick={() => handleDeleteTeam(team.id)}
                                                    className="p-1.5 text-stone-400 hover:text-red-500 hover:bg-red-50 rounded-lg"
                                                >
                                                    <Trash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>

                                        {members.length > 0 && (
                                            <div className="mt-3 flex flex-wrap gap-2">
                                                {members.map(m => (
                                                    <div key={m.id} className="flex items-center gap-1.5 bg-stone-100 rounded-full px-3 py-1 text-xs text-stone-600">
                                                        <StatusDot status={m.status} />
                                                        {m.name}
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {team.shared_context && (
                                            <div className="mt-3 bg-stone-50 rounded-lg px-3 py-2">
                                                <p className="text-[10px] text-stone-400 uppercase font-semibold tracking-wide mb-1">Shared Context</p>
                                                <p className="text-xs text-stone-600 font-mono line-clamp-2">{team.shared_context}</p>
                                            </div>
                                        )}
                                    </div>
                                );
                            })
                        )}
                    </div>
                )}
            </div>

            {/* Modals */}
            {roleModal.open && (
                <RoleModal
                    role={roleModal.role}
                    onClose={() => setRoleModal({ open: false })}
                    onSave={handleSaveRole}
                />
            )}
            {showAssignRole && (
                <AssignRoleModal
                    agents={agents}
                    roles={roles}
                    onClose={() => setShowAssignRole(false)}
                    onSave={handleAssignRole}
                />
            )}
            {teamModal.open && (
                <TeamModal
                    team={teamModal.team}
                    agents={agents}
                    onClose={() => setTeamModal({ open: false })}
                    onSave={handleSaveTeam}
                />
            )}
        </div>
    );
}
