"use client";

import type { ComposedAgentNode } from "@/lib/api";

interface Props {
    node: ComposedAgentNode;
    onChange: (next: ComposedAgentNode) => void;
}

// Inspector for the currently-selected node. Input/Output nodes mainly hold
// their guardrail rails (edited from the top-level rails), so this is most
// useful for LLM nodes.
export default function NodeInspector({ node, onChange }: Props) {
    if (node.kind === "llm") {
        return (
            <div className="p-4 space-y-3">
                <div className="text-xs uppercase tracking-wider text-gray-500 font-semibold">
                    LLM node · {node.id}
                </div>
                <Field label="Label">
                    <input
                        type="text"
                        value={node.ui?.label || ""}
                        onChange={(e) =>
                            onChange({ ...node, ui: { ...node.ui, label: e.target.value } })
                        }
                        className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                    />
                </Field>
                <Field label="System prompt">
                    <textarea
                        value={node.system_prompt || ""}
                        onChange={(e) => onChange({ ...node, system_prompt: e.target.value })}
                        rows={6}
                        className="w-full px-2 py-1 text-sm border border-gray-300 rounded font-mono"
                    />
                </Field>
                <div className="grid grid-cols-2 gap-2">
                    <Field label="Provider">
                        <input
                            type="text"
                            value={node.llm_provider || ""}
                            onChange={(e) =>
                                onChange({ ...node, llm_provider: e.target.value || null })
                            }
                            placeholder="openai"
                            className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                        />
                    </Field>
                    <Field label="Model">
                        <input
                            type="text"
                            value={node.llm_model || ""}
                            onChange={(e) =>
                                onChange({ ...node, llm_model: e.target.value || null })
                            }
                            placeholder="gpt-4o-mini"
                            className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                        />
                    </Field>
                </div>
                <div className="grid grid-cols-2 gap-2">
                    <Field label="Temperature">
                        <input
                            type="number"
                            step="0.1"
                            min="0"
                            max="2"
                            value={node.temperature ?? 0.7}
                            onChange={(e) =>
                                onChange({ ...node, temperature: parseFloat(e.target.value) })
                            }
                            className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                        />
                    </Field>
                    <Field label="Max tokens">
                        <input
                            type="number"
                            value={node.max_tokens ?? 2048}
                            onChange={(e) =>
                                onChange({ ...node, max_tokens: parseInt(e.target.value, 10) })
                            }
                            className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                        />
                    </Field>
                </div>
                <div className="text-xs text-gray-500 mt-3 pt-3 border-t border-gray-100">
                    Per-node guardrails (pre: {node.pre_guardrails?.length || 0}, post:{" "}
                    {node.post_guardrails?.length || 0}) — edit via the input/output rails for now.
                </div>
            </div>
        );
    }

    if (node.kind === "input" || node.kind === "output") {
        return (
            <div className="p-4 space-y-3">
                <div className="text-xs uppercase tracking-wider text-gray-500 font-semibold">
                    {node.kind} node · {node.id}
                </div>
                <div className="text-sm text-gray-500">
                    Guardrails for this node are configured in the{" "}
                    {node.kind === "input" ? "top" : "bottom"} rail.
                </div>
            </div>
        );
    }

    return null;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div>
            <label className="block text-xs text-gray-500 mb-1">{label}</label>
            {children}
        </div>
    );
}
