"use client";

import React, { useCallback, useMemo } from "react";
import {
    ReactFlow,
    Controls,
    Background,
    applyNodeChanges,
    applyEdgeChanges,
    addEdge,
    Connection,
    Edge,
    Node,
    NodeChange,
    EdgeChange,
    MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AgentNode, ApprovalGateNode, ConditionalNode, InputNode, LoopNode, ParallelNode, SubWorkflowNode } from "./nodes";
import type { Agent } from "@/lib/api";

const nodeTypes = {
    agent: AgentNode,
    input: InputNode,
    conditional: ConditionalNode,
    parallel: ParallelNode,
    approval_gate: ApprovalGateNode,
    loop: LoopNode,
    sub_workflow: SubWorkflowNode,
};

const defaultEdgeOptions = {
    style: {
        stroke: "#c4b5a0",
        strokeWidth: 1.5,
        strokeDasharray: "6 4",
    },
    type: "smoothstep",
    markerEnd: {
        type: MarkerType.ArrowClosed,
        color: "#c4b5a0",
        width: 18,
        height: 18,
    },
};

interface WorkflowCanvasProps {
    nodes: Node[];
    edges: Edge[];
    agents: Agent[];
    activeNodeId?: string | null;
    onChange: (nodes: Node[], edges: Edge[]) => void;
    onSelectNode: (node: Node | null) => void;
}

export default function WorkflowCanvas({
    nodes,
    edges,
    agents,
    activeNodeId,
    onChange,
    onSelectNode,
}: WorkflowCanvasProps) {
    const onNodesChange = useCallback(
        (changes: NodeChange[]) => {
            const result = applyNodeChanges(changes, nodes);
            onChange(result, edges);
        },
        [nodes, edges, onChange]
    );

    const onEdgesChange = useCallback(
        (changes: EdgeChange[]) => {
            const result = applyEdgeChanges(changes, edges);
            onChange(nodes, result);
        },
        [nodes, edges, onChange]
    );

    const onConnect = useCallback(
        (params: Connection) => {
            const result = addEdge(
                {
                    ...params,
                    type: "smoothstep",
                    style: { stroke: "#c4b5a0", strokeWidth: 1.5, strokeDasharray: "6 4" },
                    markerEnd: { type: MarkerType.ArrowClosed, color: "#c4b5a0", width: 18, height: 18 },
                },
                edges
            );
            onChange(nodes, result);
        },
        [nodes, edges, onChange]
    );

    const handleNodeClick = useCallback(
        (_event: React.MouseEvent, node: Node) => {
            onSelectNode(node);
        },
        [onSelectNode]
    );

    const handlePaneClick = useCallback(() => {
        onSelectNode(null);
    }, [onSelectNode]);

    const displayNodes = useMemo(
        () =>
            nodes.map((n) => ({
                ...n,
                data: { ...n.data, isActive: activeNodeId ? n.id === activeNodeId : false },
            })),
        [nodes, activeNodeId]
    );

    return (
        <ReactFlow
            nodes={displayNodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={handleNodeClick}
            onPaneClick={handlePaneClick}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={defaultEdgeOptions}
            fitView
            fitViewOptions={{ padding: 0.3, maxZoom: 0.85 }}
            minZoom={0.2}
            maxZoom={1.5}
            deleteKeyCode={["Backspace", "Delete"]}
            proOptions={{ hideAttribution: true }}
        >
            <Background gap={24} size={0.8} color="#e2dad0" />
            <Controls className="!bg-white !border-stone-200 !shadow-sm !rounded-xl" />
        </ReactFlow>
    );
}
