"use client";

import { useState } from "react";
import { Plus, Shield, X } from "lucide-react";
import GuardrailConfigForm from "./GuardrailConfigForm";
import type { GuardrailAttachment, GuardrailDescriptor } from "@/lib/api";

interface Props {
    stage: "input" | "output";
    attachments: GuardrailAttachment[];
    descriptors: GuardrailDescriptor[];
    onChange: (next: GuardrailAttachment[]) => void;
}

// Picker + rail of currently-attached guardrails. Used at top (input) and
// bottom (output) of the canvas.
export default function GuardrailRail({ stage, attachments, descriptors, onChange }: Props) {
    const [pickerOpen, setPickerOpen] = useState(false);
    const [editingId, setEditingId] = useState<string | null>(null);

    // Only show guardrails whose kind matches the stage (or "both").
    const eligible = descriptors.filter(
        (d) => d.kind === stage || d.kind === "both"
    );

    function addGuardrail(d: GuardrailDescriptor) {
        const id = `${d.id}_${attachments.length + 1}`;
        const next: GuardrailAttachment = {
            id,
            type: d.id,
            config: defaultConfigFor(d),
        };
        onChange([...attachments, next]);
        setPickerOpen(false);
        setEditingId(id);
    }

    function updateAttachment(idx: number, att: GuardrailAttachment) {
        const next = [...attachments];
        next[idx] = att;
        onChange(next);
    }

    function removeAttachment(idx: number) {
        const next = attachments.filter((_, i) => i !== idx);
        onChange(next);
    }

    const editing = editingId
        ? attachments.findIndex((a) => a.id === editingId)
        : -1;
    const editingAttachment = editing >= 0 ? attachments[editing] : null;
    const editingDescriptor = editingAttachment
        ? descriptors.find((d) => d.id === editingAttachment.type)
        : null;

    return (
        <div
            className={`flex items-center gap-2 px-3 py-2 border-b border-gray-200 bg-gray-50 ${
                stage === "output" ? "border-t border-b-0" : ""
            }`}
        >
            <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 uppercase tracking-wide">
                <Shield className="w-3.5 h-3.5" />
                {stage} guardrails
            </div>
            <div className="flex items-center gap-1.5 flex-1 overflow-x-auto">
                {attachments.length === 0 && (
                    <div className="text-xs text-gray-400 italic">none</div>
                )}
                {attachments.map((a, i) => {
                    const d = descriptors.find((x) => x.id === a.type);
                    return (
                        <div key={a.id} className="flex items-center">
                            <button
                                onClick={() => setEditingId(a.id)}
                                className={`text-xs px-2.5 py-1 rounded-full border ${
                                    editingId === a.id
                                        ? "bg-amber-100 border-amber-400 text-amber-800"
                                        : "bg-white border-gray-300 hover:border-amber-400 text-gray-700"
                                }`}
                            >
                                {d?.name || a.type} · {a.id}
                            </button>
                            <button
                                onClick={() => removeAttachment(i)}
                                className="ml-0.5 text-gray-400 hover:text-red-600 p-0.5"
                                title="Remove"
                            >
                                <X className="w-3 h-3" />
                            </button>
                        </div>
                    );
                })}
            </div>
            <button
                onClick={() => setPickerOpen(true)}
                className="flex items-center gap-1 text-xs px-2.5 py-1 bg-amber-600 text-white rounded hover:bg-amber-700"
            >
                <Plus className="w-3 h-3" /> Add
            </button>

            {pickerOpen && (
                <PickerModal
                    eligible={eligible}
                    onPick={addGuardrail}
                    onClose={() => setPickerOpen(false)}
                />
            )}

            {editingAttachment && editingDescriptor && (
                <EditorModal
                    descriptor={editingDescriptor}
                    attachment={editingAttachment}
                    stage={stage}
                    onChange={(att) => updateAttachment(editing, att)}
                    onClose={() => setEditingId(null)}
                    onRemove={() => {
                        removeAttachment(editing);
                        setEditingId(null);
                    }}
                />
            )}
        </div>
    );
}

function PickerModal({
    eligible,
    onPick,
    onClose,
}: {
    eligible: GuardrailDescriptor[];
    onPick: (d: GuardrailDescriptor) => void;
    onClose: () => void;
}) {
    return (
        <div
            className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
            onClick={onClose}
        >
            <div
                className="bg-white rounded-xl shadow-2xl p-6 w-[480px] max-h-[80vh] overflow-y-auto"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between mb-4">
                    <div className="font-semibold text-lg">Add a guardrail</div>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <div className="space-y-2">
                    {eligible.length === 0 && (
                        <div className="text-sm text-gray-500">
                            No guardrails available for this stage.
                        </div>
                    )}
                    {eligible.map((d) => (
                        <button
                            key={d.id}
                            onClick={() => onPick(d)}
                            className="block w-full text-left p-3 border border-gray-200 rounded-lg hover:border-amber-400 hover:bg-amber-50"
                        >
                            <div className="font-medium">{d.name}</div>
                            <div className="text-xs text-gray-500 mt-1">{d.description}</div>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}

function EditorModal({
    descriptor,
    attachment,
    stage,
    onChange,
    onClose,
    onRemove,
}: {
    descriptor: GuardrailDescriptor;
    attachment: GuardrailAttachment;
    stage: "input" | "output";
    onChange: (a: GuardrailAttachment) => void;
    onClose: () => void;
    onRemove: () => void;
}) {
    return (
        <div
            className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
            onClick={onClose}
        >
            <div
                className="bg-white rounded-xl shadow-2xl w-[560px] max-h-[85vh] overflow-y-auto"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between px-5 py-3 border-b">
                    <div className="font-semibold">Configure guardrail</div>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <div className="p-5">
                    <GuardrailConfigForm
                        descriptor={descriptor}
                        attachment={attachment}
                        stage={stage}
                        onChange={onChange}
                        onRemove={onRemove}
                    />
                </div>
            </div>
        </div>
    );
}

// ─── Helpers ───────────────────────────────────────────────────────────────


function defaultConfigFor(d: GuardrailDescriptor): Record<string, any> {
    // Tiny per-type defaults so the first edit experience isn't empty.
    if (d.id === "pii_redactor") {
        return { entities: ["email", "phone", "ssn", "credit_card"], action: "redact" };
    }
    if (d.id === "schema_validator") {
        return {
            schema: { type: "object", properties: {}, required: [] },
            action: "reject",
        };
    }
    if (d.id === "prompt_judge") {
        return {
            rubric: "",
            judge_provider: "openai",
            judge_model: "gpt-4o-mini",
            stage: d.kind === "input" ? "input" : "output",
            action: "reject",
        };
    }
    if (d.id === "injection_detector") {
        return {
            judge_provider: "openai",
            judge_model: "gpt-4o-mini",
            min_confidence: 0.6,
            action: "reject",
        };
    }
    return {};
}
