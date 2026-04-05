import React from "react";
import { Handle, Position } from "@xyflow/react";
import { Bot, Type, GitBranch, Layers, ShieldCheck, RefreshCw, Network } from "lucide-react";

/* ────────────────────────────────────────────────────────────────────────── */
/*  Shared node shell — Clay-style card with optional tooltip                */
/* ────────────────────────────────────────────────────────────────────────── */

function NodeShell({
    children,
    selected,
    tooltip,
    isActive,
}: {
    children: React.ReactNode;
    selected?: boolean;
    tooltip?: string;
    isActive?: boolean;
}) {
    const borderClass = isActive
        ? "border-indigo-400 shadow-lg"
        : selected
        ? "border-stone-300 shadow-lg ring-2 ring-stone-300/30"
        : "border-stone-100 shadow-sm hover:shadow-md hover:border-stone-200";

    return (
        <div className={`group/node relative bg-white border rounded-2xl transition-all w-[260px] ${borderClass}`}>
            {isActive && (
                <span className="absolute inset-0 rounded-2xl ring-2 ring-indigo-400/60 animate-ping pointer-events-none" />
            )}
            {children}
            {tooltip && (
                <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 px-3 py-2 bg-stone-800 text-white text-xs rounded-lg shadow-lg max-w-[280px] whitespace-pre-wrap opacity-0 group-hover/node:opacity-100 pointer-events-none transition-opacity duration-200 z-50">
                    {tooltip}
                    <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-[5px] border-l-transparent border-r-[5px] border-r-transparent border-t-[5px] border-t-stone-800" />
                </div>
            )}
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Icon badge — pastel bg with colored icon                                 */
/* ────────────────────────────────────────────────────────────────────────── */

function IconBadge({
    children,
    bg,
}: {
    children: React.ReactNode;
    bg: string;
}) {
    return (
        <div className={`${bg} w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0`}>
            {children}
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Handle styles                                                            */
/* ────────────────────────────────────────────────────────────────────────── */

const handleTarget = "!w-3 !h-3 !bg-white !border-2 !border-stone-300 !-top-1.5";
const handleSource = "!w-3 !h-3 !bg-white !border-2 !border-stone-300 !-bottom-1.5";

/* ────────────────────────────────────────────────────────────────────────── */
/*  Agent Node                                                               */
/* ────────────────────────────────────────────────────────────────────────── */

export function AgentNode({ data, selected }: { data: any; selected?: boolean }) {
    const tooltip = data.prompt && data.prompt !== "{input}" ? data.prompt : undefined;
    return (
        <NodeShell selected={selected} tooltip={tooltip} isActive={data.isActive}>
            <Handle type="target" position={Position.Top} className={handleTarget} />

            <div className="px-4 py-3.5">
                <div className="flex items-center gap-3">
                    <IconBadge bg="bg-indigo-100/80">
                        <Bot size={18} className="text-indigo-600" />
                    </IconBadge>
                    <p className="text-sm font-semibold text-stone-800 truncate flex-1 min-w-0">{data.label || "Agent"}</p>
                </div>
            </div>

            <Handle type="source" position={Position.Bottom} className={handleSource} />
        </NodeShell>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Input Node                                                               */
/* ────────────────────────────────────────────────────────────────────────── */

export function InputNode({ data, selected }: { data: any; selected?: boolean }) {
    const tooltip = data.value || undefined;
    return (
        <NodeShell selected={selected} tooltip={tooltip} isActive={data.isActive}>
            <div className="px-4 py-3.5">
                <div className="flex items-center gap-3">
                    <IconBadge bg="bg-teal-100/80">
                        <Type size={18} className="text-teal-600" />
                    </IconBadge>
                    <p className="text-sm font-semibold text-stone-800 truncate">{data.label || "Input"}</p>
                </div>
            </div>

            <Handle type="source" position={Position.Bottom} className={handleSource} />
        </NodeShell>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Conditional Node                                                         */
/* ────────────────────────────────────────────────────────────────────────── */

export function ConditionalNode({ data, selected }: { data: any; selected?: boolean }) {
    const tooltip = data.condition || undefined;
    return (
        <NodeShell selected={selected} tooltip={tooltip} isActive={data.isActive}>
            <Handle type="target" position={Position.Top} className={handleTarget} />

            <div className="px-4 py-3.5">
                <div className="flex items-center gap-3">
                    <IconBadge bg="bg-yellow-100/80">
                        <GitBranch size={18} className="text-yellow-600" />
                    </IconBadge>
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-stone-800 truncate">{data.label || "Condition"}</p>
                        <p className="text-xs text-stone-400">If / Else</p>
                    </div>
                </div>
                <div className="flex justify-between text-[10px] mt-2.5 font-semibold">
                    <span className="text-emerald-500">TRUE</span>
                    <span className="text-rose-400">FALSE</span>
                </div>
            </div>

            <Handle type="source" position={Position.Bottom} id="true" style={{ left: "30%" }}
                className="!w-3 !h-3 !bg-white !border-2 !border-emerald-400 !-bottom-1.5" />
            <Handle type="source" position={Position.Bottom} id="false" style={{ left: "70%" }}
                className="!w-3 !h-3 !bg-white !border-2 !border-rose-400 !-bottom-1.5" />
        </NodeShell>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Parallel Node                                                            */
/* ────────────────────────────────────────────────────────────────────────── */

export function ParallelNode({ data, selected }: { data: any; selected?: boolean }) {
    return (
        <NodeShell selected={selected} isActive={data.isActive}>
            <Handle type="target" position={Position.Top} className={handleTarget} />

            <div className="px-4 py-3.5">
                <div className="flex items-center gap-3">
                    <IconBadge bg="bg-violet-100/80">
                        <Layers size={18} className="text-violet-600" />
                    </IconBadge>
                    <div>
                        <p className="text-sm font-semibold text-stone-800">{data.label || "Parallel"}</p>
                        <p className="text-xs text-stone-400">Fan-out / Fan-in</p>
                    </div>
                </div>
            </div>

            <Handle type="source" position={Position.Bottom} className={handleSource} />
        </NodeShell>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Approval Gate Node                                                       */
/* ────────────────────────────────────────────────────────────────────────── */

export function ApprovalGateNode({ data, selected }: { data: any; selected?: boolean }) {
    const tooltip = data.description || undefined;
    return (
        <NodeShell selected={selected} tooltip={tooltip} isActive={data.isActive}>
            <Handle type="target" position={Position.Top} className={handleTarget} />

            <div className="px-4 py-3.5">
                <div className="flex items-center gap-3">
                    <IconBadge bg="bg-pink-100/80">
                        <ShieldCheck size={18} className="text-pink-600" />
                    </IconBadge>
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-stone-800 truncate">{data.label || "Approval Gate"}</p>
                        <p className="text-xs text-stone-400">Human Review</p>
                    </div>
                </div>
            </div>

            <Handle type="source" position={Position.Bottom} className={handleSource} />
        </NodeShell>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Loop Node                                                                */
/* ────────────────────────────────────────────────────────────────────────── */

export function LoopNode({ data, selected }: { data: any; selected?: boolean }) {
    const tooltip = data.prompt && data.prompt !== "{input}" ? data.prompt : undefined;
    return (
        <NodeShell selected={selected} tooltip={tooltip} isActive={data.isActive}>
            <Handle type="target" position={Position.Top} className={handleTarget} />

            <div className="px-4 py-3.5">
                <div className="flex items-center gap-3">
                    <IconBadge bg="bg-green-100/80">
                        <RefreshCw size={18} className="text-green-600" />
                    </IconBadge>
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-stone-800 truncate">{data.label || "Loop"}</p>
                        <p className="text-xs text-stone-400">{data.max_iterations || 3} iterations</p>
                    </div>
                </div>
            </div>

            <Handle type="source" position={Position.Bottom} className={handleSource} />
        </NodeShell>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Sub-workflow Node                                                        */
/* ────────────────────────────────────────────────────────────────────────── */

export function SubWorkflowNode({ data, selected }: { data: any; selected?: boolean }) {
    return (
        <NodeShell selected={selected} isActive={data.isActive}>
            <Handle type="target" position={Position.Top} className={handleTarget} />

            <div className="px-4 py-3.5">
                <div className="flex items-center gap-3">
                    <IconBadge bg="bg-stone-100">
                        <Network size={18} className="text-stone-600" />
                    </IconBadge>
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-stone-800 truncate">{data.label || "Sub-workflow"}</p>
                        <p className="text-xs text-stone-400 truncate">{data.workflow_name || "Select Workflow"}</p>
                    </div>
                </div>
            </div>

            <Handle type="source" position={Position.Bottom} className={handleSource} />
        </NodeShell>
    );
}
