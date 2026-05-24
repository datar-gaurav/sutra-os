"use client";

import { useState } from "react";
import { Play, Loader2 } from "lucide-react";
import {
    composedAgentsApi,
    type GuardrailAttachment,
    type GuardrailDescriptor,
    type GuardrailRunResult,
} from "@/lib/api";

interface Props {
    descriptor: GuardrailDescriptor;
    attachment: GuardrailAttachment;
    stage: "input" | "output";
    onChange: (attachment: GuardrailAttachment) => void;
    onRemove: () => void;
}

// Renders a per-type config form. Each built-in has a tiny bespoke form
// since the user-facing controls differ; a generic JSONSchema renderer is
// a Phase 2 enhancement.
export default function GuardrailConfigForm({
    descriptor,
    attachment,
    stage,
    onChange,
    onRemove,
}: Props) {
    const cfg = attachment.config || {};

    function setCfg(patch: Record<string, any>) {
        onChange({ ...attachment, config: { ...cfg, ...patch } });
    }

    return (
        <div className="border border-gray-200 rounded-lg p-4 bg-white">
            <div className="flex items-start justify-between mb-3">
                <div>
                    <div className="font-semibold text-gray-900">{descriptor.name}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{descriptor.description}</div>
                </div>
                <button
                    onClick={onRemove}
                    className="text-xs text-red-600 hover:text-red-700"
                >
                    Remove
                </button>
            </div>

            <div className="mb-3">
                <label className="block text-xs text-gray-500 mb-1">ID (for trace)</label>
                <input
                    type="text"
                    value={attachment.id}
                    onChange={(e) => onChange({ ...attachment, id: e.target.value })}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                />
            </div>

            {descriptor.id === "pii_redactor" && (
                <PIIRedactorForm cfg={cfg} setCfg={setCfg} />
            )}
            {descriptor.id === "schema_validator" && (
                <SchemaValidatorForm cfg={cfg} setCfg={setCfg} />
            )}
            {descriptor.id === "prompt_judge" && (
                <PromptJudgeForm cfg={cfg} setCfg={setCfg} stage={stage} />
            )}
            {descriptor.id === "injection_detector" && (
                <InjectionDetectorForm cfg={cfg} setCfg={setCfg} />
            )}

            <TestPanel descriptor={descriptor} attachment={attachment} stage={stage} />
        </div>
    );
}

// ─── Per-guardrail forms ───────────────────────────────────────────────────

function PIIRedactorForm({ cfg, setCfg }: any) {
    const entities = cfg.entities || ["email", "phone", "ssn", "credit_card"];
    const action = cfg.action || "redact";
    return (
        <div className="space-y-2">
            <div>
                <label className="block text-xs text-gray-500 mb-1">Entities to detect</label>
                <div className="flex flex-wrap gap-2">
                    {["email", "phone", "ssn", "credit_card"].map((ent) => (
                        <label key={ent} className="flex items-center gap-1 text-sm">
                            <input
                                type="checkbox"
                                checked={entities.includes(ent)}
                                onChange={(e) => {
                                    const next = e.target.checked
                                        ? [...entities, ent]
                                        : entities.filter((x: string) => x !== ent);
                                    setCfg({ entities: next });
                                }}
                            />
                            {ent}
                        </label>
                    ))}
                </div>
            </div>
            <div>
                <label className="block text-xs text-gray-500 mb-1">On match</label>
                <select
                    value={action}
                    onChange={(e) => setCfg({ action: e.target.value })}
                    className="text-sm border border-gray-300 rounded px-2 py-1"
                >
                    <option value="redact">redact</option>
                    <option value="reject">reject</option>
                    <option value="warn">warn</option>
                </select>
            </div>
        </div>
    );
}

function SchemaValidatorForm({ cfg, setCfg }: any) {
    const schemaText = JSON.stringify(cfg.schema || { type: "object" }, null, 2);
    const [text, setText] = useState(schemaText);
    return (
        <div className="space-y-2">
            <div>
                <label className="block text-xs text-gray-500 mb-1">JSON Schema</label>
                <textarea
                    value={text}
                    onChange={(e) => {
                        setText(e.target.value);
                        try {
                            setCfg({ schema: JSON.parse(e.target.value) });
                        } catch {
                            /* keep typing — invalid JSON ignored until parseable */
                        }
                    }}
                    rows={8}
                    className="w-full px-2 py-1 text-xs font-mono border border-gray-300 rounded"
                />
            </div>
            <div>
                <label className="block text-xs text-gray-500 mb-1">On violation</label>
                <select
                    value={cfg.action || "reject"}
                    onChange={(e) => setCfg({ action: e.target.value })}
                    className="text-sm border border-gray-300 rounded px-2 py-1"
                >
                    <option value="reject">reject</option>
                    <option value="warn">warn</option>
                </select>
            </div>
        </div>
    );
}

function PromptJudgeForm({ cfg, setCfg, stage }: any) {
    return (
        <div className="space-y-2">
            <div>
                <label className="block text-xs text-gray-500 mb-1">Rubric</label>
                <textarea
                    value={cfg.rubric || ""}
                    onChange={(e) => setCfg({ rubric: e.target.value })}
                    rows={4}
                    placeholder="Describe what the text MUST do (or must not do) to pass…"
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                />
            </div>
            <div className="grid grid-cols-2 gap-2">
                <div>
                    <label className="block text-xs text-gray-500 mb-1">Judge provider</label>
                    <input
                        type="text"
                        value={cfg.judge_provider || "openai"}
                        onChange={(e) => setCfg({ judge_provider: e.target.value })}
                        className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                    />
                </div>
                <div>
                    <label className="block text-xs text-gray-500 mb-1">Judge model</label>
                    <input
                        type="text"
                        value={cfg.judge_model || "gpt-4o-mini"}
                        onChange={(e) => setCfg({ judge_model: e.target.value })}
                        className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                    />
                </div>
            </div>
            <div>
                <label className="block text-xs text-gray-500 mb-1">On fail</label>
                <select
                    value={cfg.action || "reject"}
                    onChange={(e) => setCfg({ action: e.target.value })}
                    className="text-sm border border-gray-300 rounded px-2 py-1"
                >
                    <option value="reject">reject</option>
                    <option value="warn">warn</option>
                </select>
            </div>
        </div>
    );
}

function InjectionDetectorForm({ cfg, setCfg }: any) {
    return (
        <div className="space-y-2">
            <div className="text-xs text-gray-500 italic">
                No rubric needed — uses a built-in rubric tuned for jailbreak/injection patterns.
            </div>
            <div className="grid grid-cols-2 gap-2">
                <div>
                    <label className="block text-xs text-gray-500 mb-1">Judge provider</label>
                    <input
                        type="text"
                        value={cfg.judge_provider || "openai"}
                        onChange={(e) => setCfg({ judge_provider: e.target.value })}
                        className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                    />
                </div>
                <div>
                    <label className="block text-xs text-gray-500 mb-1">Judge model</label>
                    <input
                        type="text"
                        value={cfg.judge_model || "gpt-4o-mini"}
                        onChange={(e) => setCfg({ judge_model: e.target.value })}
                        className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                    />
                </div>
            </div>
            <div>
                <label className="block text-xs text-gray-500 mb-1">Min confidence</label>
                <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={cfg.min_confidence ?? 0.6}
                    onChange={(e) => setCfg({ min_confidence: parseFloat(e.target.value) })}
                    className="w-24 px-2 py-1 text-sm border border-gray-300 rounded"
                />
            </div>
        </div>
    );
}

// ─── Test panel ────────────────────────────────────────────────────────────

function TestPanel({
    descriptor,
    attachment,
    stage,
}: {
    descriptor: GuardrailDescriptor;
    attachment: GuardrailAttachment;
    stage: "input" | "output";
}) {
    const [input, setInput] = useState("");
    const [result, setResult] = useState<GuardrailRunResult | null>(null);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState<string | null>(null);

    async function run() {
        setBusy(true);
        setErr(null);
        setResult(null);
        try {
            const res = await composedAgentsApi.testGuardrail({
                type: descriptor.id,
                config: attachment.config,
                input,
                stage,
            });
            setResult(res);
        } catch (e: any) {
            setErr(e?.message || "Test failed");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="mt-4 pt-4 border-t border-gray-100">
            <div className="text-xs font-semibold text-gray-700 mb-2">Test</div>
            <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                rows={2}
                placeholder="Type input text to test this guardrail against…"
                className="w-full px-2 py-1 text-sm border border-gray-300 rounded mb-2"
            />
            <button
                onClick={run}
                disabled={busy || !input.trim()}
                className="flex items-center gap-1 text-xs px-3 py-1 bg-gray-900 text-white rounded disabled:opacity-40"
            >
                {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                Run test
            </button>
            {err && <div className="mt-2 text-xs text-red-600">{err}</div>}
            {result && (
                <div className="mt-2 text-xs space-y-1">
                    <div>
                        <span className="font-semibold">Verdict:</span>{" "}
                        <span
                            className={
                                result.action === "reject"
                                    ? "text-red-600"
                                    : result.action === "warn"
                                    ? "text-amber-600"
                                    : result.action === "mutate"
                                    ? "text-blue-600"
                                    : "text-emerald-600"
                            }
                        >
                            {result.action.toUpperCase()}
                        </span>
                        {result.score !== null && (
                            <span className="text-gray-500"> (confidence {result.score.toFixed(2)})</span>
                        )}
                    </div>
                    <div>
                        <span className="font-semibold">Reason:</span>{" "}
                        <span className="text-gray-700">{result.reason}</span>
                    </div>
                    {result.mutated_text && (
                        <div>
                            <span className="font-semibold">Mutated:</span>{" "}
                            <span className="text-gray-700 font-mono">{result.mutated_text}</span>
                        </div>
                    )}
                    <div className="text-gray-500">Latency: {result.latency_ms} ms</div>
                </div>
            )}
        </div>
    );
}
