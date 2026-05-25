"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Save, ArrowLeft, Plus, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import {
    composedAgentsApi,
    type ComposedAgent,
    type ComposedAgentGraphSpec,
    type ComposedAgentNode,
    type GuardrailDescriptor,
} from "@/lib/api";
import Canvas from "./Canvas";
import GuardrailRail from "./GuardrailRail";
import NodeInspector from "./NodeInspector";
import TestRunner from "./TestRunner";
import EvalsTab from "./EvalsTab";

type SaveState = "idle" | "saving" | "saved" | "error";
type ViewTab = "graph" | "evals";

export default function ComposedAgentDetailPage() {
    const params = useParams();
    const id = params?.id as string;

    const [agent, setAgent] = useState<ComposedAgent | null>(null);
    const [descriptors, setDescriptors] = useState<GuardrailDescriptor[]>([]);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const [saveState, setSaveState] = useState<SaveState>("idle");
    const [saveErr, setSaveErr] = useState<string | null>(null);
    const [tab, setTab] = useState<ViewTab>("graph");

    useEffect(() => {
        Promise.all([composedAgentsApi.get(id), composedAgentsApi.listGuardrails()])
            .then(([a, gs]) => {
                setAgent(a);
                setDescriptors(gs);
            })
            .catch(console.error);
    }, [id]);

    const spec = agent?.graph_spec;
    const inputNode = useMemo(() => spec?.nodes.find((n) => n.kind === "input"), [spec]);
    const outputNode = useMemo(() => spec?.nodes.find((n) => n.kind === "output"), [spec]);
    const selectedNode = useMemo(
        () => (selectedNodeId ? spec?.nodes.find((n) => n.id === selectedNodeId) : null),
        [spec, selectedNodeId]
    );

    function patchSpec(next: ComposedAgentGraphSpec) {
        if (!agent) return;
        setAgent({ ...agent, graph_spec: next });
    }

    function patchNode(updated: ComposedAgentNode) {
        if (!spec) return;
        patchSpec({
            ...spec,
            nodes: spec.nodes.map((n) => (n.id === updated.id ? updated : n)),
        });
    }

    function patchRail(stage: "input" | "output", guardrails: any[]) {
        if (!spec) return;
        patchSpec({
            ...spec,
            nodes: spec.nodes.map((n) =>
                n.kind === stage ? { ...n, guardrails } : n
            ),
        });
    }

    function addLLMNode() {
        if (!spec) return;
        const i = spec.nodes.filter((n) => n.kind === "llm").length + 1;
        const newId = `llm_${i}`;
        const newNode: ComposedAgentNode = {
            id: newId,
            kind: "llm",
            ui: { position: { x: 400, y: 200 + i * 100 }, label: newId },
            system_prompt: "",
            llm_provider: "openai",
            llm_model: "gpt-4o-mini",
            temperature: 0.7,
            max_tokens: 2048,
        };
        patchSpec({ ...spec, nodes: [...spec.nodes, newNode] });
    }

    async function save() {
        if (!agent) return;
        setSaveState("saving");
        setSaveErr(null);
        try {
            const updated = await composedAgentsApi.update(id, {
                graph_spec: agent.graph_spec,
                name: agent.name,
                description: agent.description ?? undefined,
            });
            setAgent(updated);
            setSaveState("saved");
            setTimeout(() => setSaveState("idle"), 1500);
        } catch (e: any) {
            console.error(e);
            setSaveErr(e?.detail?.graph_spec_error || e?.message || "Save failed");
            setSaveState("error");
        }
    }

    async function publish() {
        if (!agent) return;
        try {
            const updated = await composedAgentsApi.publish(id);
            setAgent(updated);
            alert(`Published v${updated.published_version}.`);
        } catch (e: any) {
            alert(`Publish failed: ${e?.message || e}`);
        }
    }

    if (!agent || !spec || !inputNode || !outputNode) {
        return <div className="p-8 text-gray-500">Loading…</div>;
    }

    return (
        <div className="flex flex-col h-screen">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-white">
                <div className="flex items-center gap-3">
                    <Link
                        href="/composed-agents"
                        className="p-1 text-gray-500 hover:text-gray-900"
                    >
                        <ArrowLeft className="w-4 h-4" />
                    </Link>
                    <input
                        value={agent.name}
                        onChange={(e) => setAgent({ ...agent, name: e.target.value })}
                        className="text-lg font-semibold bg-transparent border-none focus:outline-none focus:ring-0 px-0"
                    />
                    <span className="text-xs text-gray-400">
                        v{agent.version}
                        {agent.published_version !== null && ` · published v${agent.published_version}`}
                    </span>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={addLLMNode}
                        className="flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 rounded hover:bg-gray-50"
                    >
                        <Plus className="w-3.5 h-3.5" /> LLM node
                    </button>
                    <button
                        onClick={save}
                        disabled={saveState === "saving"}
                        className="flex items-center gap-1 text-xs px-3 py-1.5 bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-40"
                    >
                        {saveState === "saving" ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : saveState === "saved" ? (
                            <CheckCircle2 className="w-3.5 h-3.5" />
                        ) : saveState === "error" ? (
                            <AlertCircle className="w-3.5 h-3.5" />
                        ) : (
                            <Save className="w-3.5 h-3.5" />
                        )}
                        {saveState === "saving"
                            ? "Saving…"
                            : saveState === "saved"
                            ? "Saved"
                            : saveState === "error"
                            ? "Error"
                            : "Save"}
                    </button>
                    <button
                        onClick={publish}
                        className="text-xs px-3 py-1.5 bg-gray-900 text-white rounded hover:bg-black"
                    >
                        Publish
                    </button>
                </div>
            </div>
            {saveErr && (
                <div className="px-4 py-2 bg-red-50 text-red-700 text-sm border-b border-red-200">
                    {saveErr}
                </div>
            )}

            {/* Tab bar */}
            <div className="flex border-b border-gray-200 bg-white px-4">
                <button
                    onClick={() => setTab("graph")}
                    className={`px-3 py-2 text-sm border-b-2 ${
                        tab === "graph"
                            ? "border-amber-600 text-amber-700 font-semibold"
                            : "border-transparent text-gray-500 hover:text-gray-700"
                    }`}
                >
                    Graph
                </button>
                <button
                    onClick={() => setTab("evals")}
                    className={`px-3 py-2 text-sm border-b-2 ${
                        tab === "evals"
                            ? "border-amber-600 text-amber-700 font-semibold"
                            : "border-transparent text-gray-500 hover:text-gray-700"
                    }`}
                >
                    Evals
                </button>
            </div>

            {tab === "graph" ? (
                <>
                    {/* Canvas + side panel */}
                    <div className="flex flex-1 overflow-hidden">
                        <div className="flex-1 flex flex-col">
                            <GuardrailRail
                                stage="input"
                                attachments={inputNode.guardrails || []}
                                descriptors={descriptors}
                                onChange={(g) => patchRail("input", g)}
                            />
                            <div className="flex-1 bg-gray-50">
                                <Canvas
                                    spec={spec}
                                    selectedNodeId={selectedNodeId}
                                    onChange={patchSpec}
                                    onSelect={setSelectedNodeId}
                                />
                            </div>
                            <GuardrailRail
                                stage="output"
                                attachments={outputNode.guardrails || []}
                                descriptors={descriptors}
                                onChange={(g) => patchRail("output", g)}
                            />
                        </div>
                        {selectedNode && (
                            <div className="w-[360px] border-l border-gray-200 bg-white overflow-y-auto">
                                <NodeInspector node={selectedNode} onChange={patchNode} />
                            </div>
                        )}
                    </div>

                    {/* Test runner */}
                    <TestRunner agentId={id} />
                </>
            ) : (
                <div className="flex-1 overflow-hidden bg-white">
                    <EvalsTab agentId={id} />
                </div>
            )}
        </div>
    );
}
