"use client";

import { Handle, Position, NodeProps } from "@xyflow/react";
import { Brain, ArrowRightFromLine, ArrowLeftToLine, Shield } from "lucide-react";

const baseCls =
    "rounded-lg border-2 px-4 py-3 bg-white shadow-sm min-w-[180px] text-sm transition";

export function InputNode({ data, selected }: NodeProps) {
    const grds = (data as any).guardrailCount || 0;
    return (
        <div
            className={`${baseCls} ${
                selected ? "border-amber-600" : "border-amber-300"
            }`}
        >
            <div className="flex items-center gap-2 font-semibold text-amber-700">
                <ArrowRightFromLine className="w-4 h-4" /> Input
            </div>
            <div className="text-xs text-gray-500 mt-1 flex items-center gap-1">
                <Shield className="w-3 h-3" /> {grds} guardrail{grds === 1 ? "" : "s"}
            </div>
            <Handle type="source" position={Position.Right} />
        </div>
    );
}

export function LLMNode({ data, selected }: NodeProps) {
    const d = data as any;
    return (
        <div
            className={`${baseCls} ${
                selected ? "border-blue-600" : "border-blue-300"
            }`}
        >
            <div className="flex items-center gap-2 font-semibold text-blue-700">
                <Brain className="w-4 h-4" /> {d.label || "LLM"}
            </div>
            <div className="text-xs text-gray-500 mt-1 truncate max-w-[200px]">
                {d.model || "default model"}
            </div>
            {(d.preGuardrails > 0 || d.postGuardrails > 0) && (
                <div className="text-xs text-gray-500 mt-1 flex items-center gap-1">
                    <Shield className="w-3 h-3" /> pre:{d.preGuardrails} · post:{d.postGuardrails}
                </div>
            )}
            <Handle type="target" position={Position.Left} />
            <Handle type="source" position={Position.Right} />
        </div>
    );
}

export function OutputNode({ data, selected }: NodeProps) {
    const grds = (data as any).guardrailCount || 0;
    return (
        <div
            className={`${baseCls} ${
                selected ? "border-emerald-600" : "border-emerald-300"
            }`}
        >
            <div className="flex items-center gap-2 font-semibold text-emerald-700">
                <ArrowLeftToLine className="w-4 h-4" /> Output
            </div>
            <div className="text-xs text-gray-500 mt-1 flex items-center gap-1">
                <Shield className="w-3 h-3" /> {grds} guardrail{grds === 1 ? "" : "s"}
            </div>
            <Handle type="target" position={Position.Left} />
        </div>
    );
}

export const nodeTypes = {
    input: InputNode,
    llm: LLMNode,
    output: OutputNode,
};
