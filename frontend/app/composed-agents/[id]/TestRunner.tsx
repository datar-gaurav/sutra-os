"use client";

import { useState } from "react";
import { Play, Loader2, AlertTriangle, CheckCircle2 } from "lucide-react";
import { composedAgentsApi, type ComposedRunResponse } from "@/lib/api";

interface Props {
    agentId: string;
}

// Test runner — bottom panel on the detail page. Sends an arbitrary user
// input to /run and shows the final assistant text plus the per-guardrail
// trace.
export default function TestRunner({ agentId }: Props) {
    const [input, setInput] = useState("");
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState<ComposedRunResponse | null>(null);
    const [err, setErr] = useState<string | null>(null);

    async function run() {
        setBusy(true);
        setErr(null);
        setResult(null);
        try {
            const res = await composedAgentsApi.run(agentId, input);
            setResult(res);
        } catch (e: any) {
            setErr(e?.message || "Run failed");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="border-t border-gray-200 bg-white">
            <div className="px-4 py-3 border-b border-gray-100">
                <div className="text-sm font-semibold text-gray-700">Test runner</div>
                <div className="text-xs text-gray-500">
                    Invoke the agent (uses the draft graph_spec, not the published version).
                </div>
            </div>
            <div className="p-4 grid grid-cols-2 gap-4">
                <div>
                    <label className="block text-xs text-gray-500 mb-1">Input</label>
                    <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        rows={4}
                        placeholder="Type a user message…"
                        className="w-full px-2 py-1 text-sm border border-gray-300 rounded font-mono"
                    />
                    <button
                        onClick={run}
                        disabled={busy || !input.trim()}
                        className="mt-2 flex items-center gap-1 text-sm px-3 py-1.5 bg-gray-900 text-white rounded disabled:opacity-40"
                    >
                        {busy ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <Play className="w-4 h-4" />
                        )}
                        Run
                    </button>
                    {err && <div className="mt-2 text-xs text-red-600">{err}</div>}
                </div>
                <div>
                    <label className="block text-xs text-gray-500 mb-1">Output</label>
                    {!result ? (
                        <div className="text-sm text-gray-400 italic">No run yet.</div>
                    ) : (
                        <div className="space-y-2">
                            <div
                                className={`flex items-center gap-1 text-xs ${
                                    result.rejected ? "text-red-600" : "text-emerald-600"
                                }`}
                            >
                                {result.rejected ? (
                                    <>
                                        <AlertTriangle className="w-3.5 h-3.5" /> rejected
                                    </>
                                ) : (
                                    <>
                                        <CheckCircle2 className="w-3.5 h-3.5" /> ok
                                    </>
                                )}
                                {result.rejection_reason && (
                                    <span className="text-gray-500"> — {result.rejection_reason}</span>
                                )}
                            </div>
                            <div className="text-sm whitespace-pre-wrap font-mono p-2 bg-gray-50 rounded border border-gray-200 max-h-48 overflow-y-auto">
                                {result.output || <span className="italic text-gray-400">empty</span>}
                            </div>
                            {result.guardrail_results.length > 0 && (
                                <div>
                                    <div className="text-xs text-gray-500 font-semibold mb-1">
                                        Guardrail trace
                                    </div>
                                    <div className="space-y-1">
                                        {result.guardrail_results.map((g, i) => (
                                            <div
                                                key={i}
                                                className="text-xs flex items-start gap-2 p-1.5 bg-gray-50 rounded"
                                            >
                                                <span
                                                    className={`font-semibold ${
                                                        g.action === "reject"
                                                            ? "text-red-600"
                                                            : g.action === "warn"
                                                            ? "text-amber-600"
                                                            : g.action === "mutate"
                                                            ? "text-blue-600"
                                                            : "text-emerald-600"
                                                    }`}
                                                >
                                                    {g.stage}/{g.guardrail_id}: {g.action}
                                                </span>
                                                <span className="text-gray-600 flex-1 truncate">
                                                    {g.reason}
                                                </span>
                                                <span className="text-gray-400">{g.latency_ms}ms</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
