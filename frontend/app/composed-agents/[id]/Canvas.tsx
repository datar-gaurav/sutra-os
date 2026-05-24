"use client";

import { useCallback, useMemo } from "react";
import {
    ReactFlow,
    Controls,
    Background,
    applyNodeChanges,
    applyEdgeChanges,
    addEdge,
    type Connection,
    type Edge,
    type Node,
    type NodeChange,
    type EdgeChange,
    MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { nodeTypes } from "./NodeTypes";
import type { ComposedAgentGraphSpec, ComposedAgentNode } from "@/lib/api";

interface CanvasProps {
    spec: ComposedAgentGraphSpec;
    selectedNodeId: string | null;
    onChange: (spec: ComposedAgentGraphSpec) => void;
    onSelect: (nodeId: string | null) => void;
}

const defaultEdgeOptions = {
    style: { stroke: "#94a3b8", strokeWidth: 2 },
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
};

export default function Canvas({ spec, selectedNodeId, onChange, onSelect }: CanvasProps) {
    // Convert backend GraphSpec -> React Flow nodes/edges.
    const rfNodes: Node[] = useMemo(
        () =>
            spec.nodes.map((n) => ({
                id: n.id,
                type: n.kind,
                position: n.ui?.position || { x: 100, y: 200 },
                data: {
                    label: n.ui?.label || n.id,
                    model: n.kind === "llm" ? `${n.llm_provider || "?"}:${n.llm_model || "?"}` : "",
                    guardrailCount:
                        n.kind === "input" || n.kind === "output" ? (n.guardrails?.length || 0) : 0,
                    preGuardrails: n.pre_guardrails?.length || 0,
                    postGuardrails: n.post_guardrails?.length || 0,
                },
                selected: n.id === selectedNodeId,
            })),
        [spec, selectedNodeId]
    );

    const rfEdges: Edge[] = useMemo(
        () =>
            spec.edges.map((e, i) => ({
                id: `${e.source}->${e.target}-${i}`,
                source: e.source,
                target: e.target,
                label: e.condition || undefined,
                ...defaultEdgeOptions,
            })),
        [spec]
    );

    const onNodesChange = useCallback(
        (changes: NodeChange[]) => {
            const updated = applyNodeChanges(changes, rfNodes);
            // Only flush position changes back to the spec (selection lives in parent state).
            const next: ComposedAgentNode[] = spec.nodes.map((n) => {
                const m = updated.find((u) => u.id === n.id);
                if (!m) return n;
                return {
                    ...n,
                    ui: { ...n.ui, position: m.position },
                };
            });
            onChange({ ...spec, nodes: next });
        },
        [rfNodes, spec, onChange]
    );

    const onEdgesChange = useCallback(
        (changes: EdgeChange[]) => {
            const updated = applyEdgeChanges(changes, rfEdges);
            const next = updated.map((e) => ({ source: e.source, target: e.target }));
            onChange({ ...spec, edges: next });
        },
        [rfEdges, spec, onChange]
    );

    const onConnect = useCallback(
        (conn: Connection) => {
            if (!conn.source || !conn.target) return;
            const next = addEdge(conn, rfEdges).map((e) => ({ source: e.source, target: e.target }));
            onChange({ ...spec, edges: next });
        },
        [rfEdges, spec, onChange]
    );

    return (
        <div className="w-full h-full">
            <ReactFlow
                nodes={rfNodes}
                edges={rfEdges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                onNodeClick={(_, n) => onSelect(n.id)}
                onPaneClick={() => onSelect(null)}
                fitView
                defaultEdgeOptions={defaultEdgeOptions}
            >
                <Background gap={20} color="#e2e8f0" />
                <Controls />
            </ReactFlow>
        </div>
    );
}
