"use client";

import { useEffect, useState } from "react";
import {
    Plus,
    Play,
    Sparkles,
    Loader2,
    CheckCircle2,
    AlertCircle,
    ChevronRight,
    Trash2,
} from "lucide-react";
import {
    composedAgentsApi,
    type EvalSuite,
    type EvalCase,
    type EvalRunSummary,
    type EvalResultRow,
} from "@/lib/api";

interface Props {
    agentId: string;
}

// Top-level Evals tab. Shows the agent's suites; expanding one reveals its
// cases plus a results panel for the most recent run.
export default function EvalsTab({ agentId }: Props) {
    const [suites, setSuites] = useState<EvalSuite[]>([]);
    const [activeSuiteId, setActiveSuiteId] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        composedAgentsApi
            .listEvalSuites(agentId)
            .then((s) => {
                setSuites(s);
                if (s.length > 0) setActiveSuiteId(s[0].id);
            })
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [agentId]);

    async function createSuite() {
        const name = prompt("Name for the new eval suite?");
        if (!name) return;
        try {
            const s = await composedAgentsApi.createEvalSuite(agentId, { name });
            setSuites((cur) => [...cur, s]);
            setActiveSuiteId(s.id);
        } catch (e: any) {
            alert(`Failed: ${e?.message || e}`);
        }
    }

    if (loading) return <div className="p-6 text-gray-500">Loading…</div>;

    return (
        <div className="h-full flex">
            {/* Suite list */}
            <div className="w-[220px] border-r border-gray-200 bg-gray-50">
                <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200">
                    <div className="text-xs font-semibold uppercase tracking-wide text-gray-600">
                        Suites
                    </div>
                    <button
                        onClick={createSuite}
                        className="p-1 text-gray-500 hover:text-amber-700"
                        title="New suite"
                    >
                        <Plus className="w-4 h-4" />
                    </button>
                </div>
                {suites.length === 0 ? (
                    <div className="p-3 text-xs text-gray-400 italic">
                        No suites yet. Create one to start.
                    </div>
                ) : (
                    suites.map((s) => (
                        <button
                            key={s.id}
                            onClick={() => setActiveSuiteId(s.id)}
                            className={`flex items-center gap-1 w-full text-left px-3 py-2 text-sm border-b border-gray-100 ${
                                activeSuiteId === s.id
                                    ? "bg-amber-50 text-amber-800 font-semibold"
                                    : "hover:bg-white"
                            }`}
                        >
                            <ChevronRight className="w-3 h-3" />
                            <span className="truncate">{s.name}</span>
                        </button>
                    ))
                )}
            </div>
            {/* Active suite detail */}
            <div className="flex-1 overflow-y-auto">
                {activeSuiteId ? (
                    <SuiteDetail suiteId={activeSuiteId} />
                ) : (
                    <div className="p-6 text-gray-500 italic">Select or create a suite.</div>
                )}
            </div>
        </div>
    );
}

function SuiteDetail({ suiteId }: { suiteId: string }) {
    const [cases, setCases] = useState<EvalCase[]>([]);
    const [runs, setRuns] = useState<EvalRunSummary[]>([]);
    const [activeRunId, setActiveRunId] = useState<string | null>(null);
    const [results, setResults] = useState<EvalResultRow[]>([]);
    const [busy, setBusy] = useState<"generate" | "run" | null>(null);
    const [err, setErr] = useState<string | null>(null);

    useEffect(() => {
        Promise.all([
            composedAgentsApi.listEvalCases(suiteId),
            composedAgentsApi.listEvalRuns(suiteId),
        ])
            .then(([c, r]) => {
                setCases(c);
                setRuns(r);
                if (r.length > 0) setActiveRunId(r[0].id);
            })
            .catch((e) => setErr(e?.message || String(e)));
    }, [suiteId]);

    useEffect(() => {
        if (!activeRunId) {
            setResults([]);
            return;
        }
        composedAgentsApi
            .listEvalResults(activeRunId)
            .then(setResults)
            .catch(console.error);
    }, [activeRunId]);

    async function addCase() {
        const name = prompt("Case name?");
        if (!name) return;
        const input = prompt("Test input?");
        if (!input) return;
        const rubric = prompt("Judge rubric (optional)?") || null;
        try {
            const c = await composedAgentsApi.createEvalCase(suiteId, {
                name,
                input,
                judge_rubric: rubric,
                source: "authored",
            });
            setCases((cur) => [...cur, c]);
        } catch (e: any) {
            alert(`Failed: ${e?.message || e}`);
        }
    }

    async function deleteCase(id: string) {
        if (!confirm("Delete this case?")) return;
        try {
            await composedAgentsApi.deleteEvalCase(id);
            setCases((cur) => cur.filter((c) => c.id !== id));
        } catch (e) {
            console.error(e);
        }
    }

    async function generate() {
        setBusy("generate");
        setErr(null);
        try {
            const newCases = await composedAgentsApi.generateEvalCases(suiteId, {
                target_count: 10,
            });
            setCases((cur) => [...cur, ...newCases]);
        } catch (e: any) {
            setErr(e?.message || "Generate failed");
        } finally {
            setBusy(null);
        }
    }

    async function run() {
        setBusy("run");
        setErr(null);
        try {
            const r = await composedAgentsApi.runEvalSuite(suiteId);
            setRuns((cur) => [r, ...cur]);
            setActiveRunId(r.id);
        } catch (e: any) {
            setErr(e?.message || "Run failed");
        } finally {
            setBusy(null);
        }
    }

    const activeRun = runs.find((r) => r.id === activeRunId);
    const passRate =
        activeRun && activeRun.total > 0
            ? Math.round((activeRun.passed / activeRun.total) * 100)
            : null;

    return (
        <div className="p-5 space-y-5">
            <div className="flex items-center gap-2">
                <button
                    onClick={addCase}
                    className="flex items-center gap-1 text-xs px-2.5 py-1 border border-gray-300 rounded hover:bg-gray-50"
                >
                    <Plus className="w-3.5 h-3.5" /> Add case
                </button>
                <button
                    onClick={generate}
                    disabled={busy === "generate"}
                    className="flex items-center gap-1 text-xs px-2.5 py-1 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
                >
                    {busy === "generate" ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                        <Sparkles className="w-3.5 h-3.5" />
                    )}
                    Generate synthetic
                </button>
                <button
                    onClick={run}
                    disabled={busy === "run" || cases.length === 0}
                    className="flex items-center gap-1 text-xs px-2.5 py-1 bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-40"
                >
                    {busy === "run" ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                        <Play className="w-3.5 h-3.5" />
                    )}
                    Run suite ({cases.length})
                </button>
                {activeRun && (
                    <div
                        className={`ml-auto text-xs px-2.5 py-1 rounded flex items-center gap-1 ${
                            passRate === 100
                                ? "bg-emerald-100 text-emerald-800"
                                : passRate !== null && passRate >= 80
                                ? "bg-amber-100 text-amber-800"
                                : "bg-red-100 text-red-800"
                        }`}
                    >
                        {activeRun.status === "error" ? (
                            <AlertCircle className="w-3.5 h-3.5" />
                        ) : (
                            <CheckCircle2 className="w-3.5 h-3.5" />
                        )}
                        Last run: {activeRun.passed}/{activeRun.total} passed
                        {passRate !== null && ` (${passRate}%)`}
                    </div>
                )}
            </div>
            {err && (
                <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                    {err}
                </div>
            )}

            {/* Cases */}
            <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-gray-600 mb-2">
                    Cases ({cases.length})
                </div>
                {cases.length === 0 ? (
                    <div className="text-sm text-gray-400 italic">
                        No cases. Add manually or hit "Generate synthetic".
                    </div>
                ) : (
                    <div className="space-y-1.5">
                        {cases.map((c) => (
                            <div
                                key={c.id}
                                className="flex items-start gap-2 p-2.5 border border-gray-200 rounded text-sm"
                            >
                                <div className="flex-1 min-w-0">
                                    <div className="font-medium">
                                        {c.name}
                                        {c.category && (
                                            <span className="ml-2 text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                                                {c.category}
                                            </span>
                                        )}
                                        {c.source !== "authored" && (
                                            <span className="ml-1 text-xs text-amber-600">
                                                · {c.source}
                                            </span>
                                        )}
                                    </div>
                                    <div className="text-xs text-gray-500 truncate font-mono">
                                        {c.input}
                                    </div>
                                </div>
                                <button
                                    onClick={() => deleteCase(c.id)}
                                    className="p-1 text-gray-400 hover:text-red-600"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Results from active run */}
            {activeRunId && results.length > 0 && (
                <div>
                    <div className="text-xs font-semibold uppercase tracking-wide text-gray-600 mb-2">
                        Results
                    </div>
                    <div className="space-y-1">
                        {results.map((r) => {
                            const c = cases.find((x) => x.id === r.case_id);
                            return (
                                <div
                                    key={r.id}
                                    className={`p-2 rounded border text-xs ${
                                        r.passed
                                            ? "bg-emerald-50 border-emerald-200"
                                            : r.verdict === "ERROR"
                                            ? "bg-gray-100 border-gray-300"
                                            : "bg-red-50 border-red-200"
                                    }`}
                                >
                                    <div className="flex items-center gap-2">
                                        <span className="font-semibold">
                                            {r.passed ? "PASS" : r.verdict}
                                        </span>
                                        <span className="font-medium">
                                            {c?.name || r.case_id}
                                        </span>
                                        <span className="text-gray-500 ml-auto">
                                            {r.latency_ms}ms
                                            {r.judge_confidence !== null &&
                                                ` · conf ${r.judge_confidence.toFixed(2)}`}
                                        </span>
                                    </div>
                                    {r.reason && (
                                        <div className="text-gray-700 mt-1">{r.reason}</div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}
