"use client";

import { useState, useEffect, useCallback } from "react";
import {
    Sparkles, Plus, X, ChevronUp, ChevronDown, Eye, EyeOff, Pencil,
    Code2, Globe, Mail, BarChart3, FileText, ClipboardList, Database,
    Languages, BookOpen, ShieldCheck, HeartHandshake, KanbanSquare, Upload,
    Github, Search, Bot, AlertCircle, TrendingUp,
} from "lucide-react";
import { skillsApi, Skill, AgentSkill } from "@/lib/api";

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
    Code2, Globe, Mail, BarChart3, FileText, ClipboardList, Database,
    Languages, BookOpen, ShieldCheck, HeartHandshake, KanbanSquare, Upload,
    Github, Search, Sparkles, Bot, TrendingUp,
};

function SkillIcon({ icon, color }: { icon: string | null; color: string | null }) {
    const Icon = (icon && ICON_MAP[icon]) ? ICON_MAP[icon] : Sparkles;
    return (
        <div
            className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ backgroundColor: (color || "#6366f1") + "18", border: `1px solid ${color || "#6366f1"}30` }}
        >
            <Icon className="w-4 h-4" style={{ color: color || "#6366f1" }} />
        </div>
    );
}

// ─── Pick Skill Modal ─────────────────────────────────────────────────────────

function PickSkillModal({
    agentId, existingSkillIds, onClose, onAttached,
}: {
    agentId: string;
    existingSkillIds: string[];
    onClose: () => void;
    onAttached: () => void;
}) {
    const [skills, setSkills] = useState<Skill[]>([]);
    const [search, setSearch] = useState("");
    const [selected, setSelected] = useState<Skill | null>(null);
    const [priority, setPriority] = useState(0);
    const [overrides, setOverrides] = useState<Record<string, string>>({});
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => { skillsApi.list().then(setSkills).catch(() => {}); }, []);

    const available = skills.filter(s =>
        !existingSkillIds.includes(s.id) &&
        (search === "" || s.name.toLowerCase().includes(search.toLowerCase()))
    );

    const schemaProps = selected?.config_schema?.properties as Record<string, any> ?? {};

    const handleAttach = async () => {
        if (!selected) return;
        setSaving(true); setError("");
        try {
            await skillsApi.attachToAgent(agentId, { skill_id: selected.id, priority, config_overrides: overrides });
            onAttached(); onClose();
        } catch (err: any) {
            setError(err.message || "Failed to attach skill");
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-lg max-h-[85vh] flex flex-col border border-gray-200 dark:border-gray-700">
                <div className="p-4 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between flex-shrink-0">
                    <h3 className="font-semibold text-gray-900 dark:text-white text-sm">Attach a Skill</h3>
                    <button onClick={onClose} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-gray-400">
                        <X className="w-4 h-4" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {error && (
                        <div className="flex items-center gap-2 text-red-600 text-xs bg-red-50 dark:bg-red-900/20 rounded-lg p-2.5">
                            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" /> {error}
                        </div>
                    )}

                    {/* Search + list */}
                    <div className="space-y-2">
                        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search skills…"
                            className="w-full border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-stone-600" />
                        <div className="space-y-1 max-h-48 overflow-y-auto">
                            {available.length === 0 && (
                                <p className="text-center text-gray-400 text-xs py-4">No available skills</p>
                            )}
                            {available.map(skill => (
                                <button key={skill.id} onClick={() => { setSelected(skill); setOverrides({}); }}
                                    className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg border text-left transition-colors ${
                                        selected?.id === skill.id
                                            ? "bg-stone-100 dark:bg-stone-900/30 border-stone-400 dark:border-stone-600"
                                            : "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-750"
                                    }`}>
                                    <SkillIcon icon={skill.icon} color={skill.color} />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-1.5">
                                            <span className="text-sm font-medium text-gray-900 dark:text-white">{skill.name}</span>
                                            {skill.source === "builtin" && (
                                                <span className="text-[10px] px-1 py-0.5 rounded bg-stone-100 text-stone-700 border border-stone-300">built-in</span>
                                            )}
                                        </div>
                                        {skill.description && (
                                            <p className="text-xs text-gray-500 truncate">{skill.description}</p>
                                        )}
                                    </div>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Config for selected skill */}
                    {selected && (
                        <div className="border-t border-gray-100 dark:border-gray-700 pt-4 space-y-3">
                            <div>
                                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                                    Priority <span className="text-gray-400 font-normal">(lower = applied first)</span>
                                </label>
                                <input type="number" value={priority} onChange={e => setPriority(Number(e.target.value))}
                                    className="w-full border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-stone-600" />
                            </div>
                            {Object.keys(schemaProps).length > 0 && (
                                <div className="space-y-2">
                                    <p className="text-xs font-medium text-gray-700 dark:text-gray-300">Configuration</p>
                                    {Object.entries(schemaProps).map(([key, prop]: [string, any]) => (
                                        <div key={key}>
                                            <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                                                {prop.description || key}
                                                {prop.default !== undefined && <span className="ml-1 text-gray-400 font-normal">default: {String(prop.default)}</span>}
                                            </label>
                                            {prop.enum ? (
                                                <select value={overrides[key] ?? prop.default ?? ""} onChange={e => setOverrides(o => ({ ...o, [key]: e.target.value }))}
                                                    className="w-full border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-stone-600">
                                                    {prop.enum.map((v: string) => <option key={v} value={v}>{v}</option>)}
                                                </select>
                                            ) : (
                                                <input type={prop.type === "number" ? "number" : "text"} placeholder={String(prop.default ?? "")}
                                                    value={overrides[key] ?? ""} onChange={e => setOverrides(o => ({ ...o, [key]: e.target.value }))}
                                                    className="w-full border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-stone-600" />
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <div className="p-4 border-t border-gray-100 dark:border-gray-700 flex gap-3 flex-shrink-0">
                    <button onClick={onClose} className="flex-1 px-4 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-300 text-sm hover:bg-gray-50 dark:hover:bg-gray-800">
                        Cancel
                    </button>
                    <button onClick={handleAttach} disabled={!selected || saving}
                        className="flex-1 px-4 py-2 bg-stone-700 hover:bg-stone-700 rounded-lg text-white text-sm font-medium disabled:opacity-40 transition-colors">
                        {saving ? "Attaching…" : "Attach Skill"}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Edit Overrides Modal ─────────────────────────────────────────────────────

function EditOverridesModal({
    agentId, row, onClose, onSaved,
}: {
    agentId: string;
    row: AgentSkill;
    onClose: () => void;
    onSaved: () => void;
}) {
    const schemaProps = (row.skill.config_schema?.properties as Record<string, any>) ?? {};
    const [overrides, setOverrides] = useState<Record<string, string>>(() => {
        const initial: Record<string, string> = {};
        for (const [k, v] of Object.entries(row.config_overrides || {})) {
            initial[k] = String(v);
        }
        return initial;
    });
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    const handleSave = async () => {
        setSaving(true); setError("");
        try {
            const cleaned: Record<string, any> = {};
            for (const [k, raw] of Object.entries(overrides)) {
                if (raw === "" || raw === undefined) continue;
                const propType = schemaProps[k]?.type;
                if (propType === "number") {
                    const n = Number(raw);
                    if (Number.isNaN(n)) { setError(`${k} must be a number`); setSaving(false); return; }
                    cleaned[k] = n;
                } else {
                    cleaned[k] = raw;
                }
            }
            await skillsApi.updateAgentSkill(agentId, row.id, { config_overrides: cleaned });
            onSaved(); onClose();
        } catch (err: any) {
            setError(err.message || "Failed to save overrides");
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-lg max-h-[85vh] flex flex-col border border-gray-200 dark:border-gray-700">
                <div className="p-4 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between flex-shrink-0">
                    <h3 className="font-semibold text-gray-900 dark:text-white text-sm flex items-center gap-2">
                        <SkillIcon icon={row.skill.icon} color={row.skill.color} />
                        Edit: {row.skill.name}
                    </h3>
                    <button onClick={onClose} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-gray-400">
                        <X className="w-4 h-4" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {error && (
                        <div className="flex items-center gap-2 text-red-600 text-xs bg-red-50 dark:bg-red-900/20 rounded-lg p-2.5">
                            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" /> {error}
                        </div>
                    )}
                    {Object.keys(schemaProps).length === 0 ? (
                        <p className="text-xs text-gray-500 text-center py-4">This skill has no configurable parameters.</p>
                    ) : (
                        Object.entries(schemaProps).map(([key, prop]: [string, any]) => (
                            <div key={key}>
                                <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                                    {prop.description || key}
                                    {prop.default !== undefined && <span className="ml-1 text-gray-400 font-normal">default: {String(prop.default)}</span>}
                                </label>
                                {prop.enum ? (
                                    <select value={overrides[key] ?? ""} onChange={e => setOverrides(o => ({ ...o, [key]: e.target.value }))}
                                        className="w-full border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-stone-600">
                                        <option value="">(use default)</option>
                                        {prop.enum.map((v: string) => <option key={v} value={v}>{v}</option>)}
                                    </select>
                                ) : (
                                    <input type={prop.type === "number" ? "number" : "text"}
                                        step={prop.type === "number" ? "any" : undefined}
                                        placeholder={prop.default !== undefined ? `default: ${prop.default}` : ""}
                                        value={overrides[key] ?? ""} onChange={e => setOverrides(o => ({ ...o, [key]: e.target.value }))}
                                        className="w-full border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-stone-600" />
                                )}
                            </div>
                        ))
                    )}
                    <p className="text-[11px] text-gray-400 pt-2 border-t border-gray-100 dark:border-gray-700">
                        Leave a field blank to clear the override and fall back to the schema default. Restart the agent for changes to take effect.
                    </p>
                </div>

                <div className="p-4 border-t border-gray-100 dark:border-gray-700 flex gap-3 flex-shrink-0">
                    <button onClick={onClose} className="flex-1 px-4 py-2 border border-gray-200 dark:border-gray-700 rounded-lg text-gray-600 dark:text-gray-300 text-sm hover:bg-gray-50 dark:hover:bg-gray-800">
                        Cancel
                    </button>
                    <button onClick={handleSave} disabled={saving}
                        className="flex-1 px-4 py-2 bg-stone-700 hover:bg-stone-700 rounded-lg text-white text-sm font-medium disabled:opacity-40 transition-colors">
                        {saving ? "Saving…" : "Save"}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function SkillsSection({ agentId }: { agentId: string }) {
    const [agentSkills, setAgentSkills] = useState<AgentSkill[]>([]);
    const [loading, setLoading] = useState(true);
    const [showPicker, setShowPicker] = useState(false);
    const [showPromptPreview, setShowPromptPreview] = useState(false);
    const [editingRow, setEditingRow] = useState<AgentSkill | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const data = await skillsApi.listForAgent(agentId);
            setAgentSkills(data.sort((a, b) => a.priority - b.priority));
        } catch {}
        setLoading(false);
    }, [agentId]);

    useEffect(() => { load(); }, [load]);

    const handleDetach = async (agentSkillId: string, skillName: string) => {
        if (!confirm(`Detach "${skillName}" from this agent?`)) return;
        try { await skillsApi.detachFromAgent(agentId, agentSkillId); load(); } catch {}
    };

    const handlePriorityChange = async (agentSkillId: string, delta: number) => {
        const row = agentSkills.find(s => s.id === agentSkillId);
        if (!row) return;
        try { await skillsApi.updateAgentSkill(agentId, agentSkillId, { priority: row.priority + delta }); load(); } catch {}
    };

    const effectivePromptPreview = agentSkills
        .filter(s => s.is_active)
        .sort((a, b) => a.priority - b.priority)
        .map(s => {
            let frag = s.skill.body ?? "";
            try { Object.entries(s.config_overrides || {}).forEach(([k, v]) => { frag = frag.replaceAll(`{${k}}`, String(v)); }); } catch {}
            return frag;
        }).filter(Boolean).join("\n\n---\n\n");

    return (
        <div className="glass-card p-6 space-y-4">
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-stone-600" /> Skills
                    {agentSkills.length > 0 && (
                        <span className="text-xs px-1.5 py-0.5 rounded-full bg-stone-100 text-stone-700 border border-stone-300 font-medium">
                            {agentSkills.length}
                        </span>
                    )}
                </h2>
                <button type="button" onClick={() => setShowPicker(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-stone-700 text-white rounded-lg text-sm font-medium hover:bg-stone-700 transition-colors">
                    <Plus className="w-3.5 h-3.5" /> Attach Skill
                </button>
            </div>

            {loading ? (
                <p className="text-sm text-gray-400">Loading skills…</p>
            ) : agentSkills.length === 0 ? (
                <div className="text-center py-6 border border-dashed border-gray-200 dark:border-gray-700 rounded-xl">
                    <Sparkles className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                    <p className="text-sm text-gray-500">No skills attached yet</p>
                    <p className="text-xs text-gray-400 mt-1">
                        Skills extend this agent with additional prompt instructions and tools.
                    </p>
                </div>
            ) : (
                <div className="space-y-2">
                    {agentSkills.map((row, idx) => (
                        <div key={row.id}
                            className={`flex items-start gap-3 p-3 rounded-xl border bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700 ${!row.is_active ? "opacity-50" : ""}`}>
                            {/* Priority controls */}
                            <div className="flex flex-col items-center gap-0.5 pt-0.5">
                                <button type="button" onClick={() => handlePriorityChange(row.id, -1)} disabled={idx === 0}
                                    className="text-gray-300 hover:text-gray-600 disabled:opacity-20 disabled:cursor-not-allowed transition-colors">
                                    <ChevronUp className="w-3.5 h-3.5" />
                                </button>
                                <span className="text-[10px] text-gray-400 font-mono">{row.priority}</span>
                                <button type="button" onClick={() => handlePriorityChange(row.id, 1)} disabled={idx === agentSkills.length - 1}
                                    className="text-gray-300 hover:text-gray-600 disabled:opacity-20 disabled:cursor-not-allowed transition-colors">
                                    <ChevronDown className="w-3.5 h-3.5" />
                                </button>
                            </div>

                            <SkillIcon icon={row.skill.icon} color={row.skill.color} />

                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-sm font-medium text-gray-900 dark:text-white">{row.skill.name}</span>
                                    <span className="text-xs text-gray-400 capitalize">{row.skill.category}</span>
                                    {row.skill.source === "builtin" && (
                                        <span className="text-[10px] px-1 py-0.5 rounded-full bg-stone-100 text-stone-700 border border-stone-300">built-in</span>
                                    )}
                                </div>
                                {row.skill.description && (
                                    <p className="text-xs text-gray-500 truncate mt-0.5">{row.skill.description}</p>
                                )}
                                {(row.skill.tools?.length ?? 0) > 0 && (
                                    <div className="flex flex-wrap gap-1 mt-1.5">
                                        {(row.skill.tools ?? []).slice(0, 4).map(t => (
                                            <span key={t} className="text-[10px] bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 px-1.5 py-0.5 rounded font-mono border border-gray-200 dark:border-gray-600">
                                                {t}
                                            </span>
                                        ))}
                                        {(row.skill.tools?.length ?? 0) > 4 && (
                                            <span className="text-[10px] text-gray-400">+{(row.skill.tools?.length ?? 0) - 4}</span>
                                        )}
                                    </div>
                                )}
                                {Object.keys(row.config_overrides || {}).length > 0 && (
                                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                                        {Object.entries(row.config_overrides).map(([k, v]) => (
                                            <span key={k} className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 border border-amber-200 text-amber-700">
                                                {k}: {String(v)}
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>

                            <div className="flex items-center gap-1 mt-0.5 flex-shrink-0">
                                {Object.keys((row.skill.config_schema?.properties as Record<string, any>) ?? {}).length > 0 && (
                                    <button type="button" onClick={() => setEditingRow(row)}
                                        className="text-gray-300 hover:text-stone-600 transition-colors" title="Edit overrides">
                                        <Pencil className="w-3.5 h-3.5" />
                                    </button>
                                )}
                                <button type="button" onClick={() => handleDetach(row.id, row.skill.name)}
                                    className="text-gray-300 hover:text-red-400 transition-colors" title="Detach skill">
                                    <X className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Effective prompt preview */}
            {agentSkills.length > 0 && (
                <div className="border-t border-gray-100 dark:border-gray-700 pt-3">
                    <button type="button" onClick={() => setShowPromptPreview(v => !v)}
                        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 transition-colors">
                        {showPromptPreview ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                        {showPromptPreview ? "Hide" : "Preview"} effective skill prompts
                    </button>
                    {showPromptPreview && (
                        <pre className="mt-2 p-3 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-xs text-gray-600 dark:text-gray-400 font-mono whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
                            {effectivePromptPreview || "(no active skill fragments)"}
                        </pre>
                    )}
                </div>
            )}

            {showPicker && (
                <PickSkillModal
                    agentId={agentId}
                    existingSkillIds={agentSkills.map(s => s.skill_id)}
                    onClose={() => setShowPicker(false)}
                    onAttached={load}
                />
            )}

            {editingRow && (
                <EditOverridesModal
                    agentId={agentId}
                    row={editingRow}
                    onClose={() => setEditingRow(null)}
                    onSaved={load}
                />
            )}
        </div>
    );
}
