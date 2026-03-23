"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
    ArrowLeft, Save, Plus, Settings, Play, Loader2, TerminalSquare, X,
    GitBranch, Layers, ShieldCheck, RefreshCw, Bot, Type, Network,
} from "lucide-react";
import Link from "next/link";
import { Node, Edge } from "@xyflow/react";
import WorkflowCanvas from "../components/WorkflowCanvas";
import { agentsApi, workflowsApi, type Agent, type WorkflowSummary as Workflow } from "@/lib/api";

export default function WorkflowEditPage() {
    const { id } = useParams() as { id: string };
    const router = useRouter();

    const [workflow, setWorkflow] = useState<Workflow | null>(null);
    const [allWorkflows, setAllWorkflows] = useState<Workflow[]>([]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [running, setRunning] = useState(false);
    const [showLogs, setShowLogs] = useState(false);

    const [nodes, setNodes] = useState<Node[]>([]);
    const [edges, setEdges] = useState<Edge[]>([]);
    const [selectedNode, setSelectedNode] = useState<Node | null>(null);

    useEffect(() => {
        async function fetchData() {
            try {
                const [wf, agentsList, workflowsList] = await Promise.all([
                    workflowsApi.get(id),
                    agentsApi.list(),
                    workflowsApi.list(),
                ]);
                setWorkflow(wf);
                setNodes(wf.definition?.nodes || []);
                setEdges(wf.definition?.edges || []);
                setAgents(agentsList);
                setAllWorkflows(workflowsList.filter(w => w.id !== id));
            } catch (err) {
                console.error(err);
                router.push("/workflows");
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [id, router]);

    const handleSave = async () => {
        if (!workflow) return;
        setSaving(true);
        try {
            await workflowsApi.update(id, { ...workflow, definition: { nodes, edges } });
        } catch (err: any) {
            console.error(err);
            const detail = err?.detail || err?.message;
            if (detail?.validation_errors) {
                alert("Workflow validation failed:\n\n" + detail.validation_errors.join("\n"));
            } else if (typeof detail === "string") {
                alert("Save failed: " + detail);
            } else {
                alert("Failed to save workflow.");
            }
        } finally {
            setSaving(false);
        }
    };

    const handleRun = async () => {
        if (!workflow) return;
        await handleSave();
        setRunning(true);
        setShowLogs(true);
        try {
            await workflowsApi.execute(id);
            // Poll for completion since execution runs in background
            const poll = setInterval(async () => {
                try {
                    const latest = await workflowsApi.get(id);
                    setWorkflow(latest);
                    if (latest.last_run_status && latest.last_run_status !== "running") {
                        clearInterval(poll);
                        setRunning(false);
                    }
                } catch {
                    clearInterval(poll);
                    setRunning(false);
                }
            }, 2000);
        } catch (err) {
            console.error(err);
            alert("Error executing workflow.");
            setRunning(false);
        }
    };

    const addNode = (type: string, data: Record<string, any>) => {
        const newNode: Node = {
            id: `${type}-${Date.now()}`,
            type,
            position: { x: 200 + Math.random() * 100, y: 150 + Math.random() * 100 },
            data,
        };
        setNodes((nds) => [...nds, newNode]);
    };

    const handleAddAgent = () => addNode("agent", { label: "Agent", agent_id: "", prompt: "{input}" });
    const handleAddInput = () => addNode("input", { label: "Input", value: "" });
    const handleAddConditional = () => addNode("conditional", { label: "Condition", condition: "", agent_id: "" });
    const handleAddParallel = () => addNode("parallel", { label: "Parallel" });
    const handleAddApprovalGate = () => addNode("approval_gate", { label: "Approval Gate", description: "" });
    const handleAddLoop = () => addNode("loop", { label: "Loop", agent_id: "", prompt: "{input}", max_iterations: 3 });
    const handleAddSubWorkflow = () => addNode("sub_workflow", { label: "Sub-workflow", workflow_id: "", workflow_name: "" });

    const updateSelectedNode = (key: string, value: string) => {
        if (!selectedNode) return;
        setNodes((nds) =>
            nds.map((n) => {
                if (n.id === selectedNode.id) {
                    const updated = { ...n, data: { ...n.data, [key]: value } };
                    setSelectedNode(updated);
                    return updated;
                }
                return n;
            })
        );
    };

    const handleWorkflowSettingChange = (key: keyof Workflow, value: any) => {
        if (!workflow) return;
        setWorkflow({ ...workflow, [key]: value });
    };

    const handleSubWorkflowChange = (wfId: string) => {
        if (!selectedNode) return;
        const wf = allWorkflows.find(w => w.id === wfId);
        setNodes((nds) =>
            nds.map((n) => {
                if (n.id === selectedNode.id) {
                    const updated = {
                        ...n,
                        data: {
                            ...n.data,
                            workflow_id: wfId,
                            workflow_name: wf?.name || "Unknown"
                        }
                    };
                    setSelectedNode(updated);
                    return updated;
                }
                return n;
            })
        );
    }

    if (loading || !workflow) {
        return <div className="flex h-full items-center justify-center text-stone-400">Loading...</div>;
    }

    return (
        <div className="flex flex-col h-[calc(100vh-4rem)] overflow-hidden">
            {/* ─── Top Bar ──────────────────────────────────────────────── */}
            <div className="flex items-center justify-between px-1 py-2 shrink-0">
                {/* Left: back + name */}
                <div className="flex items-center gap-3 min-w-0">
                    <Link href="/workflows" className="p-1.5 text-stone-400 hover:text-stone-600 rounded-lg hover:bg-stone-100 transition-colors">
                        <ArrowLeft size={18} />
                    </Link>
                    <input
                        type="text"
                        value={workflow.name}
                        onChange={(e) => handleWorkflowSettingChange("name", e.target.value)}
                        className="text-lg font-bold bg-transparent border-none outline-none text-stone-900 p-0 min-w-0"
                        placeholder="Workflow Name"
                    />
                </div>

                {/* Right: actions */}
                <div className="flex items-center gap-2 shrink-0">
                    <button
                        onClick={() => setShowLogs(!showLogs)}
                        className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all border ${showLogs ? "bg-indigo-50 border-indigo-200 text-indigo-600" : "bg-white border-stone-200 text-stone-500 hover:bg-stone-50"}`}
                    >
                        <TerminalSquare size={14} />
                        Logs
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={saving || running}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-stone-200 text-stone-600 hover:bg-stone-50 disabled:opacity-50 rounded-lg text-xs font-medium transition-all"
                    >
                        <Save size={14} />
                        {saving ? "Saving..." : "Save"}
                    </button>
                    <button
                        onClick={handleRun}
                        disabled={running || saving}
                        className="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg text-xs font-semibold transition-all shadow-sm"
                    >
                        {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} className="fill-current" />}
                        {running ? "Running..." : "Run"}
                    </button>
                </div>
            </div>

            {/* ─── Node Toolbar ─────────────────────────────────────────── */}
            <div className="flex items-center gap-1.5 px-1 pb-2 shrink-0">
                <span className="text-[10px] text-stone-400 font-medium uppercase tracking-wider mr-1">Add</span>
                <button onClick={handleAddInput} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all border bg-white hover:shadow-sm text-stone-600 border-stone-200 hover:bg-stone-50">
                    <Type size={12} /> Input
                </button>
                <button onClick={handleAddAgent} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all border bg-white hover:shadow-sm text-indigo-600 border-indigo-200 hover:bg-indigo-50">
                    <Bot size={12} /> Agent
                </button>
                <button onClick={handleAddConditional} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all border bg-white hover:shadow-sm text-amber-600 border-amber-200 hover:bg-amber-50">
                    <GitBranch size={12} /> If/Else
                </button>
                <button onClick={handleAddParallel} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all border bg-white hover:shadow-sm text-violet-600 border-violet-200 hover:bg-violet-50">
                    <Layers size={12} /> Parallel
                </button>
                <button onClick={handleAddLoop} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all border bg-white hover:shadow-sm text-cyan-600 border-cyan-200 hover:bg-cyan-50">
                    <RefreshCw size={12} /> Loop
                </button>
                <button onClick={handleAddSubWorkflow} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all border bg-white hover:shadow-sm text-stone-600 border-stone-200 hover:bg-stone-50">
                    <Network size={12} /> Sub-workflow
                </button>
                <button onClick={handleAddApprovalGate} className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all border bg-white hover:shadow-sm text-rose-600 border-rose-200 hover:bg-rose-50">
                    <ShieldCheck size={12} /> Approval
                </button>
            </div>

            {/* ─── Canvas + Panels ──────────────────────────────────────── */}
            <div className="flex-1 flex overflow-hidden rounded-xl border border-stone-200 bg-stone-50">
                {/* Canvas */}
                <div className="flex-1 h-full">
                    <WorkflowCanvas
                        key={`canvas-${id}`}
                        nodes={nodes}
                        edges={edges}
                        agents={agents}
                        activeNodeId={
                            running && workflow.last_run_logs?.length
                                ? (workflow.last_run_logs[workflow.last_run_logs.length - 1]?.node_id ?? null)
                                : null
                        }
                        onChange={(n, e) => { setNodes(n); setEdges(e); }}
                        onSelectNode={setSelectedNode}
                    />
                </div>

                {/* ─── Config Sidebar ───────────────────────────────────── */}
                {selectedNode && (
                    <div className="w-72 bg-white border-l border-stone-200 overflow-y-auto">
                        <div className="flex items-center justify-between px-4 py-3 border-b border-stone-100">
                            <div className="flex items-center gap-2">
                                <Settings className="text-stone-400" size={14} />
                                <h2 className="text-sm font-semibold text-stone-700 capitalize">
                                    {(selectedNode.type || "Node").replace("_", " ")}
                                </h2>
                            </div>
                            <button onClick={() => setSelectedNode(null)} className="text-stone-300 hover:text-stone-500 transition-colors">
                                <X size={14} />
                            </button>
                        </div>

                        <div className="p-4 space-y-4">
                            {/* Label */}
                            <Field label="Label">
                                <input type="text" value={selectedNode.data?.label as string || ""}
                                    onChange={(e) => updateSelectedNode("label", e.target.value)}
                                    className="field-input" placeholder="Node label" />
                            </Field>

                            {/* Agent */}
                            {selectedNode.type === "agent" && (
                                <>
                                    <Field label="Agent">
                                        <select value={selectedNode.data?.agent_id as string || ""}
                                            onChange={(e) => updateSelectedNode("agent_id", e.target.value)}
                                            className="field-input">
                                            <option value="">-- Choose --</option>
                                            {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                                        </select>
                                    </Field>
                                    <Field label="Prompt" hint="Use {input} for upstream data">
                                        <textarea value={selectedNode.data?.prompt as string || ""} onChange={(e) => updateSelectedNode("prompt", e.target.value)}
                                            rows={5} className="field-input font-mono resize-none" placeholder="{input}" />
                                    </Field>
                                    <Field label="Retries" hint="0 = no retry, exponential backoff">
                                        <input type="number" min={0} max={5}
                                            value={selectedNode.data?.max_retries as number || 0}
                                            onChange={(e) => updateSelectedNode("max_retries", e.target.value)}
                                            className="field-input" />
                                    </Field>
                                </>
                            )}

                            {/* Input */}
                            {selectedNode.type === "input" && (
                                <Field label="Value">
                                    <textarea value={selectedNode.data?.value as string || ""} onChange={(e) => updateSelectedNode("value", e.target.value)}
                                        rows={6} className="field-input font-mono resize-none" placeholder="Enter text or JSON..." />
                                </Field>
                            )}

                            {/* Conditional */}
                            {selectedNode.type === "conditional" && (
                                <>
                                    <Field label="Condition" hint="Natural language">
                                        <textarea value={selectedNode.data?.condition as string || ""} onChange={(e) => updateSelectedNode("condition", e.target.value)}
                                            rows={3} className="field-input resize-none" placeholder="e.g. Output is high quality" />
                                    </Field>
                                    <Field label="Evaluator Agent">
                                        <select value={selectedNode.data?.agent_id as string || ""}
                                            onChange={(e) => updateSelectedNode("agent_id", e.target.value)}
                                            className="field-input">
                                            <option value="">Auto-pass if empty</option>
                                            {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                                        </select>
                                    </Field>
                                    <p className="text-[10px] text-stone-400 leading-relaxed">Green handle = TRUE branch, Red handle = FALSE branch.</p>
                                </>
                            )}

                            {/* Parallel */}
                            {selectedNode.type === "parallel" && (
                                <p className="text-xs text-stone-500 leading-relaxed">Connect multiple nodes from the output handle. They run concurrently and outputs are joined.</p>
                            )}

                            {/* Approval */}
                            {selectedNode.type === "approval_gate" && (
                                <Field label="Description" hint="Context for the reviewer">
                                    <textarea value={selectedNode.data?.description as string || ""} onChange={(e) => updateSelectedNode("description", e.target.value)}
                                        rows={4} className="field-input resize-none" placeholder="What should the reviewer check?" />
                                </Field>
                            )}

                            {/* Loop */}
                            {selectedNode.type === "loop" && (
                                <>
                                    <Field label="Agent">
                                        <select value={selectedNode.data?.agent_id as string || ""}
                                            onChange={(e) => updateSelectedNode("agent_id", e.target.value)}
                                            className="field-input">
                                            <option value="">-- Choose --</option>
                                            {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                                        </select>
                                    </Field>
                                    <Field label="Prompt">
                                        <textarea value={selectedNode.data?.prompt as string || ""} onChange={(e) => updateSelectedNode("prompt", e.target.value)}
                                            rows={4} className="field-input font-mono resize-none" placeholder="{input}" />
                                    </Field>
                                    <div className="grid grid-cols-2 gap-3">
                                        <Field label="Iterations">
                                            <input type="number" min={1} max={10}
                                                value={selectedNode.data?.max_iterations as number || 3}
                                                onChange={(e) => updateSelectedNode("max_iterations", e.target.value)}
                                                className="field-input" />
                                        </Field>
                                        <Field label="Retries">
                                            <input type="number" min={0} max={5}
                                                value={selectedNode.data?.max_retries as number || 0}
                                                onChange={(e) => updateSelectedNode("max_retries", e.target.value)}
                                                className="field-input" />
                                        </Field>
                                    </div>
                                </>
                            )}

                            {/* Sub-workflow */}
                            {selectedNode.type === "sub_workflow" && (
                                <>
                                    <Field label="Workflow">
                                        <select value={selectedNode.data?.workflow_id as string || ""}
                                            onChange={(e) => handleSubWorkflowChange(e.target.value)}
                                            className="field-input">
                                            <option value="">-- Select Workflow --</option>
                                            {allWorkflows.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                                        </select>
                                    </Field>
                                    <p className="text-[10px] text-stone-500 leading-relaxed italic">
                                        The sub-workflow will receive current node input and its final output will be passed downstream.
                                    </p>
                                </>
                            )}
                        </div>
                    </div>
                )}

                {/* ─── Logs Panel ───────────────────────────────────────── */}
                {showLogs && (
                    <div className="w-80 bg-white border-l border-stone-200 flex flex-col overflow-hidden">
                        <div className="flex items-center justify-between px-4 py-3 border-b border-stone-100">
                            <div className="flex items-center gap-2">
                                <TerminalSquare className="text-indigo-500" size={14} />
                                <h2 className="text-sm font-semibold text-stone-700">Logs</h2>
                            </div>
                            <button onClick={() => setShowLogs(false)} className="text-stone-300 hover:text-stone-500 transition-colors">
                                <X size={14} />
                            </button>
                        </div>

                        <div className="px-4 py-3 border-b border-stone-100 bg-stone-50/50">
                            <div className="flex items-center gap-2">
                                <div className={`w-2 h-2 rounded-full ${workflow.last_run_status === "success" ? "bg-emerald-500" : workflow.last_run_status === "failed" ? "bg-rose-500" : workflow.last_run_status === "running" ? "bg-indigo-500 animate-pulse" : "bg-stone-300"}`} />
                                <span className="text-xs font-semibold text-stone-600 capitalize">{workflow.last_run_status || "Never run"}</span>
                                {workflow.last_run_at && (
                                    <span className="text-[10px] text-stone-400 ml-auto">
                                        {new Date(workflow.last_run_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
                                    </span>
                                )}
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-3 bg-stone-900 font-mono text-[11px]">
                            {(!workflow.last_run_logs || workflow.last_run_logs.length === 0) ? (
                                <p className="text-stone-500 text-center mt-8">No logs yet. Run the workflow.</p>
                            ) : (
                                <div className="flex flex-col gap-2">
                                    {workflow.last_run_logs.map((log, idx) => (
                                        <div key={idx} className={`px-2.5 py-2 rounded-md border ${log.type === "error" ? "bg-rose-950/30 border-rose-900/40 text-rose-300" : log.type === "success" ? "bg-emerald-950/20 border-emerald-900/30 text-emerald-300" : "bg-stone-800/60 border-stone-700/50 text-stone-300"}`}>
                                            <div className="flex items-center justify-between mb-0.5 text-[9px] opacity-60">
                                                <span className="text-indigo-400">{new Date(log.timestamp).toLocaleTimeString()}</span>
                                                {log.node_id && <span className="text-stone-500 truncate ml-2 max-w-[80px]">{log.node_id}</span>}
                                            </div>
                                            <div className="whitespace-pre-wrap break-words leading-relaxed">{log.message}</div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>

            {/* Scoped styles for form fields */}
            <style jsx global>{`
                .field-input {
                    width: 100%;
                    background: #f8fafc;
                    border: 1px solid #e2e8f0;
                    border-radius: 0.5rem;
                    padding: 0.5rem 0.75rem;
                    font-size: 0.8125rem;
                    color: #334155;
                    outline: none;
                    transition: border-color 0.15s, box-shadow 0.15s;
                }
                .field-input:focus {
                    border-color: #6366f1;
                    box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.1);
                }
            `}</style>
        </div>
    );
}

/* ─── Tiny helper for form fields ──────────────────────────────────────── */

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
    return (
        <div>
            <label className="block text-[10px] font-semibold text-stone-500 uppercase tracking-wider mb-1.5">
                {label}
                {hint && <span className="block text-[9px] font-normal text-stone-400 normal-case tracking-normal mt-0.5">{hint}</span>}
            </label>
            {children}
        </div>
    );
}
