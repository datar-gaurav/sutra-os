"use client";

import { useEffect, useState } from "react";
import { Play, Loader2, BookmarkPlus, Plus, X, RefreshCw } from "lucide-react";
import {
    composedAgentsApi,
    type ComposedAgent,
    type GuardrailAttachment,
    type GuardrailDescriptor,
    type GuardrailRunResult,
} from "@/lib/api";

interface Props {
    descriptor: GuardrailDescriptor;
    attachment: GuardrailAttachment;
    stage: "input" | "output";
    descriptors?: GuardrailDescriptor[];     // needed by GuardrailGroup for child picker
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
    descriptors,
    onChange,
    onRemove,
}: Props) {
    const cfg = attachment.config || {};
    const [saveBusy, setSaveBusy] = useState(false);
    const [saveMsg, setSaveMsg] = useState<string | null>(null);

    function setCfg(patch: Record<string, any>) {
        onChange({ ...attachment, config: { ...cfg, ...patch } });
    }

    async function saveToLibrary() {
        const name = prompt("Name for this saved guardrail?");
        if (!name) return;
        setSaveBusy(true);
        setSaveMsg(null);
        try {
            const sg = await composedAgentsApi.createSaved({
                name,
                type: descriptor.id,
                config: attachment.config,
            });
            // Tag the current attachment as sourced from the library.
            onChange({ ...attachment, source_id: sg.id, source_version: sg.version });
            setSaveMsg(`Saved as "${name}".`);
            setTimeout(() => setSaveMsg(null), 2000);
        } catch (e: any) {
            setSaveMsg(`Save failed: ${e?.message || e}`);
        } finally {
            setSaveBusy(false);
        }
    }

    return (
        <div className="border border-gray-200 rounded-lg p-4 bg-white">
            <div className="flex items-start justify-between mb-3">
                <div>
                    <div className="font-semibold text-gray-900">{descriptor.name}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{descriptor.description}</div>
                    {attachment.source_id && (
                        <div className="text-xs text-amber-700 mt-1">
                            Loaded from library · v{attachment.source_version}
                        </div>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={saveToLibrary}
                        disabled={saveBusy}
                        className="flex items-center gap-1 text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
                        title="Save this configuration to the library for reuse"
                    >
                        <BookmarkPlus className="w-3 h-3" />
                        Save to library
                    </button>
                    <button
                        onClick={onRemove}
                        className="text-xs text-red-600 hover:text-red-700"
                    >
                        Remove
                    </button>
                </div>
            </div>
            {saveMsg && <div className="text-xs text-emerald-700 mb-2">{saveMsg}</div>}

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
            {descriptor.id === "group" && (
                <GroupForm
                    cfg={cfg}
                    setCfg={setCfg}
                    stage={stage}
                    descriptors={descriptors || []}
                />
            )}
            {descriptor.id === "sub_agent" && (
                <SubAgentForm
                    attachment={attachment}
                    onChange={onChange}
                />
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

function GroupForm({
    cfg,
    setCfg,
    stage,
    descriptors,
}: {
    cfg: any;
    setCfg: (patch: Record<string, any>) => void;
    stage: "input" | "output";
    descriptors: GuardrailDescriptor[];
}) {
    const mode = cfg.mode || "ALL";
    const children: GuardrailAttachment[] = cfg.children || [];
    const [pickerOpen, setPickerOpen] = useState(false);
    const [editingIdx, setEditingIdx] = useState<number | null>(null);

    // Eligible child types — exclude groups from nesting for now (keeps the
    // UX simple; the backend supports nested groups when authored manually).
    const eligible = descriptors.filter(
        (d) => d.id !== "group" && (d.kind === stage || d.kind === "both")
    );

    function setChildren(next: GuardrailAttachment[]) {
        setCfg({ children: next });
    }

    function addChild(d: GuardrailDescriptor) {
        const id = `${d.id}_child_${children.length + 1}`;
        const att: GuardrailAttachment = {
            id,
            type: d.id,
            config: {},
        };
        setChildren([...children, att]);
        setPickerOpen(false);
        setEditingIdx(children.length);
    }

    function updateChild(i: number, att: GuardrailAttachment) {
        const next = [...children];
        next[i] = att;
        setChildren(next);
    }

    function removeChild(i: number) {
        setChildren(children.filter((_, idx) => idx !== i));
        if (editingIdx === i) setEditingIdx(null);
    }

    const editing = editingIdx !== null ? children[editingIdx] : null;
    const editingDescriptor = editing
        ? descriptors.find((d) => d.id === editing.type)
        : null;

    return (
        <div className="space-y-3">
            <div>
                <label className="block text-xs text-gray-500 mb-1">Mode</label>
                <div className="flex gap-1">
                    {(["ALL", "ANY", "SEQUENCE"] as const).map((m) => (
                        <button
                            key={m}
                            onClick={() => setCfg({ mode: m })}
                            className={`text-xs px-2.5 py-1 rounded border ${
                                mode === m
                                    ? "bg-amber-100 border-amber-400 text-amber-800"
                                    : "bg-white border-gray-300 text-gray-700 hover:border-amber-400"
                            }`}
                        >
                            {m}
                        </button>
                    ))}
                </div>
                <div className="text-xs text-gray-500 mt-1 italic">
                    {mode === "ALL" && "Every child must pass. First reject is fatal; mutations chain."}
                    {mode === "ANY" && "Group passes if any child passes. Mutations are not applied."}
                    {mode === "SEQUENCE" && "Ordered evaluation. Same semantics as ALL."}
                </div>
            </div>
            <div>
                <div className="flex items-center justify-between mb-1">
                    <label className="block text-xs text-gray-500">Children</label>
                    <button
                        onClick={() => setPickerOpen(true)}
                        className="flex items-center gap-1 text-xs px-2 py-0.5 bg-gray-900 text-white rounded hover:bg-black"
                    >
                        <Plus className="w-3 h-3" /> Add child
                    </button>
                </div>
                {children.length === 0 ? (
                    <div className="text-xs text-gray-400 italic py-2">No children yet.</div>
                ) : (
                    <div className="space-y-1">
                        {children.map((c, i) => {
                            const d = descriptors.find((x) => x.id === c.type);
                            return (
                                <div
                                    key={i}
                                    className={`flex items-center justify-between text-xs p-2 rounded border ${
                                        editingIdx === i
                                            ? "bg-amber-50 border-amber-300"
                                            : "bg-gray-50 border-gray-200"
                                    }`}
                                >
                                    <button
                                        onClick={() => setEditingIdx(editingIdx === i ? null : i)}
                                        className="text-left flex-1"
                                    >
                                        <span className="font-medium">{d?.name || c.type}</span>
                                        <span className="text-gray-500"> · {c.id}</span>
                                    </button>
                                    <button
                                        onClick={() => removeChild(i)}
                                        className="text-gray-400 hover:text-red-600 p-0.5"
                                    >
                                        <X className="w-3 h-3" />
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                )}
                {editing && editingDescriptor && editingIdx !== null && (
                    <div className="mt-2 pl-3 border-l-2 border-amber-300">
                        <GuardrailConfigForm
                            descriptor={editingDescriptor}
                            attachment={editing}
                            stage={stage}
                            descriptors={descriptors}
                            onChange={(att) => updateChild(editingIdx, att)}
                            onRemove={() => removeChild(editingIdx)}
                        />
                    </div>
                )}
            </div>
            {pickerOpen && (
                <div
                    className="fixed inset-0 bg-black/40 flex items-center justify-center z-[60]"
                    onClick={() => setPickerOpen(false)}
                >
                    <div
                        className="bg-white rounded-xl shadow-2xl p-5 w-[420px] max-h-[70vh] overflow-y-auto"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center justify-between mb-3">
                            <div className="font-semibold">Add child guardrail</div>
                            <button onClick={() => setPickerOpen(false)} className="text-gray-400">
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                        <div className="space-y-2">
                            {eligible.map((d) => (
                                <button
                                    key={d.id}
                                    onClick={() => addChild(d)}
                                    className="block w-full text-left p-2.5 border border-gray-200 rounded hover:border-amber-400 hover:bg-amber-50"
                                >
                                    <div className="font-medium text-sm">{d.name}</div>
                                    <div className="text-xs text-gray-500">{d.description}</div>
                                </button>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}


function SubAgentForm({
    attachment,
    onChange,
}: {
    attachment: GuardrailAttachment;
    onChange: (a: GuardrailAttachment) => void;
}) {
    const cfg = attachment.config || {};
    const [agents, setAgents] = useState<ComposedAgent[]>([]);
    const [loading, setLoading] = useState(true);
    const [resnapBusy, setResnapBusy] = useState(false);

    useEffect(() => {
        composedAgentsApi
            .list()
            .then(setAgents)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, []);

    const sourceId = cfg.source_agent_id || null;
    const source = agents.find((a) => a.id === sourceId);
    const driftDetected =
        source && cfg.source_version != null && source.version !== cfg.source_version;

    function pickSource(agent: ComposedAgent) {
        onChange({
            ...attachment,
            config: {
                ...cfg,
                graph_spec: agent.graph_spec,
                source_agent_id: agent.id,
                source_version: agent.version,
            },
        });
    }

    async function resnap() {
        if (!sourceId) return;
        setResnapBusy(true);
        try {
            const fresh = await composedAgentsApi.get(sourceId);
            onChange({
                ...attachment,
                config: {
                    ...cfg,
                    graph_spec: fresh.graph_spec,
                    source_agent_id: fresh.id,
                    source_version: fresh.version,
                },
            });
        } catch (e) {
            console.error(e);
        } finally {
            setResnapBusy(false);
        }
    }

    return (
        <div className="space-y-3">
            <div>
                <label className="block text-xs text-gray-500 mb-1">
                    Source composed agent
                </label>
                {loading ? (
                    <div className="text-xs text-gray-500">Loading…</div>
                ) : (
                    <select
                        value={sourceId || ""}
                        onChange={(e) => {
                            const ag = agents.find((a) => a.id === e.target.value);
                            if (ag) pickSource(ag);
                        }}
                        className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                    >
                        <option value="">— Choose an agent to snapshot —</option>
                        {agents.map((a) => (
                            <option key={a.id} value={a.id}>
                                {a.name} (v{a.version})
                            </option>
                        ))}
                    </select>
                )}
                {source && (
                    <div className="flex items-center gap-2 mt-1 text-xs">
                        <span className="text-gray-500">
                            Snapshot: v{cfg.source_version} of "{source.name}"
                        </span>
                        {driftDetected && (
                            <button
                                onClick={resnap}
                                disabled={resnapBusy}
                                className="flex items-center gap-1 px-2 py-0.5 bg-amber-100 text-amber-800 rounded border border-amber-300 hover:bg-amber-200 disabled:opacity-40"
                            >
                                {resnapBusy ? (
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                ) : (
                                    <RefreshCw className="w-3 h-3" />
                                )}
                                Source is now v{source.version} — re-snapshot
                            </button>
                        )}
                    </div>
                )}
            </div>
            <div className="grid grid-cols-2 gap-2">
                <div>
                    <label className="block text-xs text-gray-500 mb-1">Stage</label>
                    <select
                        value={cfg.stage || "output"}
                        onChange={(e) =>
                            onChange({
                                ...attachment,
                                config: { ...cfg, stage: e.target.value },
                            })
                        }
                        className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                    >
                        <option value="input">input</option>
                        <option value="output">output</option>
                    </select>
                </div>
                <div>
                    <label className="block text-xs text-gray-500 mb-1">On fail</label>
                    <select
                        value={cfg.action || "reject"}
                        onChange={(e) =>
                            onChange({
                                ...attachment,
                                config: { ...cfg, action: e.target.value },
                            })
                        }
                        className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                    >
                        <option value="reject">reject</option>
                        <option value="warn">warn</option>
                    </select>
                </div>
            </div>
            <div className="text-xs text-gray-500 italic">
                The source agent's final assistant message must be JSON of shape{" "}
                <code>{`{verdict: "PASS"|"FAIL", reason, confidence}`}</code>.
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
