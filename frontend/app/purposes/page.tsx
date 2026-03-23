"use client";

import { useState, useEffect, useCallback } from "react";
import {
    Layers,
    Plus,
    Trash2,
    Edit2,
    X,
    Loader2,
    AlertCircle,
    Star,
} from "lucide-react";
import { purposesApi, llmsApi, type LLMPurpose, type PurposeStatusResponse } from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

interface SlotForm {
    provider: string;
    model: string;
}

interface PurposeForm {
    name: string;
    description: string;
    is_default: boolean;
    slots: (SlotForm | null)[];
}

const emptySlot = (): SlotForm => ({ provider: "", model: "" });

const emptyForm = (): PurposeForm => ({
    name: "",
    description: "",
    is_default: false,
    slots: [emptySlot(), null, null, null, null],
});

function formFromPurpose(p: LLMPurpose): PurposeForm {
    const slots: (SlotForm | null)[] = [];
    for (let i = 1; i <= 5; i++) {
        const s = (p as any)[`priority_${i}`];
        slots.push(s ? { provider: s.provider, model: s.model } : null);
    }
    return {
        name: p.name,
        description: p.description ?? "",
        is_default: p.is_default,
        slots,
    };
}

function formToPayload(form: PurposeForm): Record<string, unknown> {
    const data: Record<string, unknown> = {
        name: form.name,
        description: form.description || null,
        is_default: form.is_default,
    };
    for (let i = 0; i < 5; i++) {
        const s = form.slots[i];
        data[`priority_${i + 1}`] =
            s && s.provider.trim() && s.model.trim()
                ? { provider: s.provider.trim(), model: s.model.trim() }
                : null;
    }
    return data;
}

// ─── Status dot ──────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: "green" | "yellow" | "red" | null }) {
    const colors = {
        green: "bg-green-500",
        yellow: "bg-yellow-400",
        red: "bg-red-500",
    };
    const labels = {
        green: "P1 active",
        yellow: "Fallen back",
        red: "Exhausted",
    };
    if (!status) return null;
    return (
        <span className="inline-flex items-center gap-1.5 text-xs text-gray-500">
            <span className={`w-2 h-2 rounded-full ${colors[status]} inline-block`} />
            {labels[status]}
        </span>
    );
}

// ─── Slot badge ──────────────────────────────────────────────────────────────

function SlotBadge({
    priority,
    slot,
}: {
    priority: number;
    slot: { provider: string; model: string } | null;
}) {
    if (!slot) return null;
    return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-stone-100 text-stone-700 border border-stone-200">
            P{priority}: {slot.provider}/{slot.model}
        </span>
    );
}

// ─── Provider / Model helpers ────────────────────────────────────────────────

const PROVIDERS = [
    { value: "openai", label: "OpenAI" },
    { value: "groq", label: "Groq" },
    { value: "google", label: "Google" },
    { value: "openrouter", label: "OpenRouter" },
    { value: "anthropic", label: "Anthropic" },
    { value: "ollama", label: "Ollama" },
    { value: "perplexity", label: "Perplexity" },
    { value: "clod", label: "Clod.io" },
];

async function fetchModelsForProvider(provider: string): Promise<string[]> {
    switch (provider) {
        case "groq":
            return (await llmsApi.groqModels()).map(m => m.id);
        case "openrouter":
            return (await llmsApi.openRouterModels()).map(m => m.id);
        case "google":
            return (await llmsApi.googleModels()).map(m => m.id);
        case "ollama":
            return (await llmsApi.ollamaModels()).map(m => m.name);
        case "perplexity":
            return (await llmsApi.perplexityModels()).map(m => m.id);
        case "clod":
            return (await llmsApi.clodModels()).map(m => m.id);
        default:
            return [];
    }
}

// ─── Slot Row ────────────────────────────────────────────────────────────────

function SlotRow({
    idx,
    slot,
    onSlotChange,
}: {
    idx: number;
    slot: SlotForm | null;
    onSlotChange: (idx: number, updates: Partial<SlotForm>) => void;
}) {
    const [models, setModels] = useState<string[]>([]);
    const [loadingModels, setLoadingModels] = useState(false);
    const [search, setSearch] = useState("");
    const provider = slot?.provider ?? "";
    const model = slot?.model ?? "";

    useEffect(() => {
        if (!provider) {
            setModels([]);
            return;
        }
        let cancelled = false;
        setLoadingModels(true);
        setModels([]);
        fetchModelsForProvider(provider)
            .then(m => { if (!cancelled) setModels(m); })
            .catch(() => { if (!cancelled) setModels([]); })
            .finally(() => { if (!cancelled) setLoadingModels(false); });
        return () => { cancelled = true; };
    }, [provider]);

    return (
        <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-400 w-6 shrink-0">
                P{idx + 1}
            </span>
            <select
                value={provider}
                onChange={(e) => {
                    onSlotChange(idx, { provider: e.target.value, model: "" });
                    setSearch("");
                }}
                className="flex-1 px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-400 bg-white"
            >
                <option value="">Provider</option>
                {PROVIDERS.map(p => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                ))}
            </select>
            {models.length > 0 ? (
                <div className="flex-1 relative">
                    <input
                        value={search || model}
                        onChange={(e) => {
                            setSearch(e.target.value);
                            if (!e.target.value) onSlotChange(idx, { model: "" });
                        }}
                        placeholder={loadingModels ? "Loading..." : "Search models..."}
                        className="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-400"
                    />
                    {search && (
                        <div className="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg">
                            {models
                                .filter(m => m.toLowerCase().includes(search.toLowerCase()))
                                .slice(0, 20)
                                .map(m => (
                                    <button
                                        key={m}
                                        type="button"
                                        onClick={() => {
                                            onSlotChange(idx, { model: m });
                                            setSearch("");
                                        }}
                                        className="w-full text-left px-3 py-1.5 text-xs font-mono hover:bg-gray-50"
                                    >
                                        {m}
                                    </button>
                                ))}
                            {models.filter(m => m.toLowerCase().includes(search.toLowerCase())).length === 0 && (
                                <div className="px-3 py-2 text-xs text-gray-400">No matching models</div>
                            )}
                        </div>
                    )}
                </div>
            ) : (
                <input
                    type="text"
                    value={model}
                    onChange={(e) => onSlotChange(idx, { model: e.target.value })}
                    placeholder={loadingModels ? "Loading..." : provider ? "Type model name" : "Model"}
                    disabled={loadingModels}
                    className="flex-1 px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-400 disabled:bg-gray-50 disabled:text-gray-400"
                />
            )}
        </div>
    );
}

// ─── Modal ───────────────────────────────────────────────────────────────────

interface ModalProps {
    title: string;
    form: PurposeForm;
    onChange: (form: PurposeForm) => void;
    onSave: () => void;
    onCancel: () => void;
    saving: boolean;
    error: string | null;
}

function PurposeModal({ title, form, onChange, onSave, onCancel, saving, error }: ModalProps) {
    const updateSlot = (idx: number, updates: Partial<SlotForm>) => {
        const slots = [...form.slots];
        if (!slots[idx]) slots[idx] = emptySlot();
        slots[idx] = { ...slots[idx]!, ...updates };
        onChange({ ...form, slots });
    };

    return (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
                <div className="flex items-center justify-between p-5 border-b border-gray-100">
                    <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
                    <button onClick={onCancel} className="text-gray-400 hover:text-gray-600">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-5 space-y-4">
                    {error && (
                        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 text-red-700 text-sm">
                            <AlertCircle className="w-4 h-4 shrink-0" />
                            {error}
                        </div>
                    )}

                    {/* Name */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            Name <span className="text-red-400">*</span>
                        </label>
                        <input
                            type="text"
                            value={form.name}
                            onChange={(e) => onChange({ ...form, name: e.target.value })}
                            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-400"
                            placeholder="e.g. Fast Chat"
                        />
                    </div>

                    {/* Description */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                        <textarea
                            value={form.description}
                            onChange={(e) => onChange({ ...form, description: e.target.value })}
                            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-stone-400 resize-none"
                            rows={2}
                            placeholder="What this purpose is used for..."
                        />
                    </div>

                    {/* Is Default */}
                    <label className="flex items-center gap-2 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={form.is_default}
                            onChange={(e) => onChange({ ...form, is_default: e.target.checked })}
                            className="rounded border-gray-300"
                        />
                        <span className="text-sm text-gray-700">Default purpose</span>
                    </label>

                    {/* Priority slots */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Priority Slots</label>
                        <div className="space-y-3">
                            {[0, 1, 2, 3, 4].map((idx) => (
                                <SlotRow
                                    key={idx}
                                    idx={idx}
                                    slot={form.slots[idx]}
                                    onSlotChange={updateSlot}
                                />
                            ))}
                        </div>
                    </div>
                </div>

                <div className="flex items-center justify-end gap-2 p-5 border-t border-gray-100">
                    <button
                        onClick={onCancel}
                        className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 rounded-lg hover:bg-gray-50"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={onSave}
                        disabled={saving || !form.name.trim()}
                        className="px-4 py-2 text-sm font-medium text-white bg-stone-800 rounded-lg hover:bg-stone-700 disabled:opacity-50 flex items-center gap-2"
                    >
                        {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                        Save
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Main page ───────────────────────────────────────────────────────────────

export default function PurposesPage() {
    const [purposes, setPurposes] = useState<LLMPurpose[]>([]);
    const [statuses, setStatuses] = useState<Record<string, PurposeStatusResponse>>({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Modal state
    const [modalOpen, setModalOpen] = useState(false);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [form, setForm] = useState<PurposeForm>(emptyForm());
    const [modalError, setModalError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            setDeleteError(null);
            const list = await purposesApi.list();
            setPurposes(list);

            // Fetch statuses in parallel
            const statusResults = await Promise.allSettled(
                list.map((p) => purposesApi.status(p.id))
            );
            const statusMap: Record<string, PurposeStatusResponse> = {};
            statusResults.forEach((r, i) => {
                if (r.status === "fulfilled") statusMap[list[i].id] = r.value;
            });
            setStatuses(statusMap);
        } catch (e: any) {
            setError(e.message || "Failed to load purposes");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const openCreate = () => {
        setEditingId(null);
        setForm(emptyForm());
        setModalError(null);
        setModalOpen(true);
    };

    const openEdit = (p: LLMPurpose) => {
        setEditingId(p.id);
        setForm(formFromPurpose(p));
        setModalError(null);
        setModalOpen(true);
    };

    const handleSave = async () => {
        if (!form.name.trim()) {
            setModalError("Name is required.");
            return;
        }
        try {
            setSaving(true);
            setModalError(null);
            const payload = formToPayload(form);
            if (editingId) {
                await purposesApi.update(editingId, payload as any);
            } else {
                await purposesApi.create(payload as any);
            }
            setModalOpen(false);
            await load();
        } catch (e: any) {
            setModalError(e.message || "Failed to save purpose");
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (id: string) => {
        if (!confirm("Delete this purpose?")) return;
        try {
            setDeleteError(null);
            await purposesApi.delete(id);
            await load();
        } catch (e: any) {
            setDeleteError(e.message || "Cannot delete: purpose may be in use by agents.");
        }
    };

    return (
        <div className="p-6 max-w-6xl mx-auto space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-stone-100">
                        <Layers className="w-5 h-5 text-stone-600" />
                    </div>
                    <div>
                        <h1 className="text-xl font-semibold text-gray-900">LLM Purposes</h1>
                        <p className="text-sm text-gray-500">
                            Manage purpose-based LLM routing with fallback priorities
                        </p>
                    </div>
                </div>
                <button
                    onClick={openCreate}
                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-stone-800 rounded-lg hover:bg-stone-700"
                >
                    <Plus className="w-4 h-4" />
                    New Purpose
                </button>
            </div>

            {/* Errors */}
            {error && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 text-red-700 text-sm">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    {error}
                </div>
            )}
            {deleteError && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 text-red-700 text-sm">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    {deleteError}
                </div>
            )}

            {/* Loading */}
            {loading && (
                <div className="flex items-center justify-center py-20 text-gray-400">
                    <Loader2 className="w-6 h-6 animate-spin" />
                </div>
            )}

            {/* Empty state */}
            {!loading && purposes.length === 0 && !error && (
                <div className="text-center py-20 text-gray-400">
                    <Layers className="w-10 h-10 mx-auto mb-3 opacity-40" />
                    <p className="text-sm">No purposes configured yet.</p>
                    <button
                        onClick={openCreate}
                        className="mt-3 text-sm text-stone-600 hover:text-stone-800 underline"
                    >
                        Create your first purpose
                    </button>
                </div>
            )}

            {/* Purpose cards */}
            {!loading && purposes.length > 0 && (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {purposes.map((p) => {
                        const st = statuses[p.id];
                        return (
                            <div
                                key={p.id}
                                className="glass-card p-5 rounded-xl border border-gray-100 space-y-3"
                            >
                                {/* Title row */}
                                <div className="flex items-start justify-between">
                                    <div className="flex items-center gap-2 min-w-0">
                                        <h3 className="text-sm font-semibold text-gray-900 truncate">
                                            {p.name}
                                        </h3>
                                        {p.is_default && (
                                            <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500 shrink-0" />
                                        )}
                                    </div>
                                    <div className="flex items-center gap-1 shrink-0 ml-2">
                                        <button
                                            onClick={() => openEdit(p)}
                                            className="p-1.5 rounded-md text-gray-400 hover:text-stone-700 hover:bg-gray-50"
                                            title="Edit"
                                        >
                                            <Edit2 className="w-3.5 h-3.5" />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(p.id)}
                                            className="p-1.5 rounded-md text-gray-400 hover:text-red-600 hover:bg-red-50"
                                            title="Delete"
                                        >
                                            <Trash2 className="w-3.5 h-3.5" />
                                        </button>
                                    </div>
                                </div>

                                {/* Description */}
                                {p.description && (
                                    <p className="text-xs text-gray-500 line-clamp-2">
                                        {p.description}
                                    </p>
                                )}

                                {/* Status indicator */}
                                <StatusDot status={st?.overall_status ?? null} />

                                {/* Slot badges */}
                                <div className="flex flex-wrap gap-1.5">
                                    {[1, 2, 3, 4, 5].map((n) => (
                                        <SlotBadge
                                            key={n}
                                            priority={n}
                                            slot={(p as any)[`priority_${n}`]}
                                        />
                                    ))}
                                    {![1, 2, 3, 4, 5].some(
                                        (n) => (p as any)[`priority_${n}`]
                                    ) && (
                                        <span className="text-xs text-gray-400 italic">
                                            No slots configured
                                        </span>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Modal */}
            {modalOpen && (
                <PurposeModal
                    title={editingId ? "Edit Purpose" : "Create Purpose"}
                    form={form}
                    onChange={setForm}
                    onSave={handleSave}
                    onCancel={() => setModalOpen(false)}
                    saving={saving}
                    error={modalError}
                />
            )}
        </div>
    );
}
