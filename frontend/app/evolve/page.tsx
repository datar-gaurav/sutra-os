"use client";

import { useState, useEffect, useCallback } from "react";
import {
    Dna, Activity, TrendingUp, AlertTriangle, CheckCircle2, XCircle,
    Clock, Play, ChevronDown, ChevronRight, ExternalLink, Loader2,
    Zap, Target, Hammer, ListTodo, Eye, Plus, Trash2, Save, Settings2,
} from "lucide-react";
import { evolveApi, EvolveSuggestion, EvolveRun, EvolveDashboard } from "@/lib/api";

type Tab = "dashboard" | "suggestions" | "competitors";

const CATEGORY_COLORS: Record<string, string> = {
    platform_health: "bg-blue-100 text-blue-700",
    error_pattern: "bg-red-100 text-red-700",
    performance: "bg-amber-100 text-amber-700",
    competitor_gap: "bg-purple-100 text-purple-700",
    feature_idea: "bg-green-100 text-green-700",
};

const PRIORITY_COLORS: Record<string, string> = {
    low: "bg-stone-100 text-stone-600",
    medium: "bg-blue-100 text-blue-700",
    high: "bg-amber-100 text-amber-700",
    critical: "bg-red-100 text-red-700",
};

const STATUS_COLORS: Record<string, string> = {
    proposed: "bg-stone-100 text-stone-600",
    pending_approval: "bg-amber-100 text-amber-700",
    approved: "bg-blue-100 text-blue-700",
    in_progress: "bg-indigo-100 text-indigo-700",
    completed: "bg-green-100 text-green-700",
    rejected: "bg-red-100 text-red-700",
    dismissed: "bg-stone-100 text-stone-500",
};

const ACTION_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
    forge_request: Hammer,
    task: ListTodo,
    goal: Target,
};

export default function EvolvePage() {
    const [tab, setTab] = useState<Tab>("dashboard");
    const [dashboard, setDashboard] = useState<EvolveDashboard | null>(null);
    const [suggestions, setSuggestions] = useState<EvolveSuggestion[]>([]);
    const [runs, setRuns] = useState<EvolveRun[]>([]);
    const [loading, setLoading] = useState(true);
    const [triggering, setTriggering] = useState<string | null>(null);
    const [statusFilter, setStatusFilter] = useState("");
    const [categoryFilter, setCategoryFilter] = useState("");
    const [expandedId, setExpandedId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const loadData = useCallback(async () => {
        setLoading(true);
        try {
            const [dash, sugs, rns] = await Promise.all([
                evolveApi.dashboard(),
                evolveApi.suggestions({ status: statusFilter || undefined, category: categoryFilter || undefined }),
                evolveApi.runs(),
            ]);
            setDashboard(dash);
            setSuggestions(sugs);
            setRuns(rns);
        } catch (e) {
            console.error("Failed to load evolve data:", e);
        } finally {
            setLoading(false);
        }
    }, [statusFilter, categoryFilter]);

    useEffect(() => { loadData(); }, [loadData]);

    async function handleTrigger(runType: string) {
        setTriggering(runType);
        setError(null);
        try {
            await evolveApi.trigger(runType);
            await loadData();
        } catch (e: any) {
            const msg = e?.message || String(e);
            setError(`Trigger failed: ${msg}`);
            console.error("Trigger failed:", e);
        } finally {
            setTriggering(null);
        }
    }

    async function handleDismiss(id: string) {
        try {
            await evolveApi.dismiss(id);
            await loadData();
        } catch (e) {
            console.error("Dismiss failed:", e);
        }
    }

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-gradient-to-br from-violet-500 to-fuchsia-500 rounded-xl text-white">
                        <Dna className="w-6 h-6" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold text-stone-900">Evolve</h1>
                        <p className="text-sm text-stone-500">Self-improving platform intelligence</p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={() => handleTrigger("daily_analysis")}
                        disabled={triggering !== null}
                        className="flex items-center gap-2 px-4 py-2 bg-stone-900 text-white rounded-lg hover:bg-stone-800 disabled:opacity-50 text-sm font-medium"
                    >
                        {triggering === "daily_analysis" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                        Run Analysis
                    </button>
                    <button
                        onClick={() => handleTrigger("competitor_monitor")}
                        disabled={triggering !== null}
                        className="flex items-center gap-2 px-4 py-2 bg-white border border-stone-200 text-stone-700 rounded-lg hover:bg-stone-50 disabled:opacity-50 text-sm font-medium"
                    >
                        {triggering === "competitor_monitor" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
                        Scan Competitors
                    </button>
                </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-stone-100 p-1 rounded-lg w-fit">
                {([
                    { id: "dashboard" as Tab, label: "Dashboard", icon: Activity },
                    { id: "suggestions" as Tab, label: "Suggestions", icon: Zap },
                    { id: "competitors" as Tab, label: "Competitor Intel", icon: TrendingUp },
                ]).map(t => (
                    <button
                        key={t.id}
                        onClick={() => setTab(t.id)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                            tab === t.id ? "bg-white text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-700"
                        }`}
                    >
                        <t.icon className="w-4 h-4" />
                        {t.label}
                    </button>
                ))}
            </div>

            {error && (
                <div className="flex items-center gap-2 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                    <span className="flex-1">{error}</span>
                    <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
                        <XCircle className="w-4 h-4" />
                    </button>
                </div>
            )}

            {loading && !dashboard ? (
                <div className="flex items-center justify-center py-20 text-stone-400">
                    <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading...
                </div>
            ) : (
                <>
                    {tab === "dashboard" && dashboard && <DashboardTab dashboard={dashboard} runs={runs} />}
                    {tab === "suggestions" && (
                        <SuggestionsTab
                            suggestions={suggestions}
                            statusFilter={statusFilter}
                            setStatusFilter={setStatusFilter}
                            categoryFilter={categoryFilter}
                            setCategoryFilter={setCategoryFilter}
                            expandedId={expandedId}
                            setExpandedId={setExpandedId}
                            onDismiss={handleDismiss}
                        />
                    )}
                    {tab === "competitors" && <CompetitorTab runs={runs} />}
                </>
            )}
        </div>
    );
}

function DashboardTab({ dashboard, runs }: { dashboard: EvolveDashboard; runs: EvolveRun[] }) {
    const healthColor = dashboard.health_score >= 90 ? "text-green-600" : dashboard.health_score >= 70 ? "text-amber-600" : "text-red-600";

    return (
        <div className="space-y-6">
            {/* Stats cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-white rounded-xl border border-stone-200 p-5">
                    <p className="text-xs font-medium text-stone-500 uppercase tracking-wider">Health Score</p>
                    <p className={`text-3xl font-bold mt-1 ${healthColor}`}>{dashboard.health_score}%</p>
                    <p className="text-xs text-stone-400 mt-1">Last 24 hours</p>
                </div>
                <div className="bg-white rounded-xl border border-stone-200 p-5">
                    <p className="text-xs font-medium text-stone-500 uppercase tracking-wider">Pending Review</p>
                    <p className="text-3xl font-bold mt-1 text-amber-600">{dashboard.pending_count}</p>
                    <p className="text-xs text-stone-400 mt-1">Suggestions awaiting approval</p>
                </div>
                <div className="bg-white rounded-xl border border-stone-200 p-5">
                    <p className="text-xs font-medium text-stone-500 uppercase tracking-wider">Approved</p>
                    <p className="text-3xl font-bold mt-1 text-green-600">{dashboard.approved_count}</p>
                    <p className="text-xs text-stone-400 mt-1">Improvements implemented</p>
                </div>
                <div className="bg-white rounded-xl border border-stone-200 p-5">
                    <p className="text-xs font-medium text-stone-500 uppercase tracking-wider">Competitor Gaps</p>
                    <p className="text-3xl font-bold mt-1 text-purple-600">{dashboard.competitor_gaps}</p>
                    <p className="text-xs text-stone-400 mt-1">Features to evaluate</p>
                </div>
            </div>

            {/* Recent runs */}
            <div className="bg-white rounded-xl border border-stone-200 p-5">
                <h3 className="text-sm font-semibold text-stone-700 mb-3">Recent Runs</h3>
                {runs.length === 0 ? (
                    <p className="text-sm text-stone-400 py-4 text-center">No runs yet. Click &quot;Run Analysis&quot; to start.</p>
                ) : (
                    <div className="space-y-2">
                        {runs.slice(0, 5).map(run => (
                            <div key={run.id} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-stone-50">
                                <div className="flex items-center gap-3">
                                    <RunStatusIcon status={run.status} />
                                    <div>
                                        <p className="text-sm font-medium text-stone-700">
                                            {run.run_type === "daily_analysis" ? "Daily Analysis" : "Competitor Monitor"}
                                        </p>
                                        <p className="text-xs text-stone-400">
                                            {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                                        </p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-3 text-sm">
                                    <span className="text-stone-500">{run.suggestions_generated} suggestions</span>
                                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                        run.status === "completed" ? "bg-green-100 text-green-700" :
                                        run.status === "partial" ? "bg-amber-100 text-amber-700" :
                                        run.status === "failed" ? "bg-red-100 text-red-700" :
                                        "bg-blue-100 text-blue-700"
                                    }`}>
                                        {run.status}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function SuggestionsTab({
    suggestions, statusFilter, setStatusFilter, categoryFilter, setCategoryFilter,
    expandedId, setExpandedId, onDismiss,
}: {
    suggestions: EvolveSuggestion[];
    statusFilter: string; setStatusFilter: (v: string) => void;
    categoryFilter: string; setCategoryFilter: (v: string) => void;
    expandedId: string | null; setExpandedId: (v: string | null) => void;
    onDismiss: (id: string) => void;
}) {
    return (
        <div className="space-y-4">
            {/* Filters */}
            <div className="flex gap-3">
                <select
                    value={statusFilter}
                    onChange={e => setStatusFilter(e.target.value)}
                    className="px-3 py-2 bg-white border border-stone-200 rounded-lg text-sm text-stone-700"
                >
                    <option value="">All Statuses</option>
                    <option value="pending_approval">Pending Approval</option>
                    <option value="approved">Approved</option>
                    <option value="in_progress">In Progress</option>
                    <option value="completed">Completed</option>
                    <option value="rejected">Rejected</option>
                    <option value="dismissed">Dismissed</option>
                </select>
                <select
                    value={categoryFilter}
                    onChange={e => setCategoryFilter(e.target.value)}
                    className="px-3 py-2 bg-white border border-stone-200 rounded-lg text-sm text-stone-700"
                >
                    <option value="">All Categories</option>
                    <option value="platform_health">Platform Health</option>
                    <option value="error_pattern">Error Pattern</option>
                    <option value="performance">Performance</option>
                    <option value="competitor_gap">Competitor Gap</option>
                    <option value="feature_idea">Feature Idea</option>
                </select>
            </div>

            {/* Suggestions list */}
            {suggestions.length === 0 ? (
                <div className="bg-white rounded-xl border border-stone-200 p-10 text-center text-stone-400">
                    <Dna className="w-8 h-8 mx-auto mb-2 opacity-40" />
                    <p className="text-sm">No suggestions found. Run an analysis to generate them.</p>
                </div>
            ) : (
                <div className="space-y-2">
                    {suggestions.map(s => {
                        const expanded = expandedId === s.id;
                        const ActionIcon = ACTION_ICONS[s.action_type || "task"] || ListTodo;
                        return (
                            <div key={s.id} className="bg-white rounded-xl border border-stone-200 overflow-hidden">
                                <button
                                    onClick={() => setExpandedId(expanded ? null : s.id)}
                                    className="w-full flex items-center gap-3 p-4 text-left hover:bg-stone-50 transition-colors"
                                >
                                    {expanded ? <ChevronDown className="w-4 h-4 text-stone-400 flex-shrink-0" /> : <ChevronRight className="w-4 h-4 text-stone-400 flex-shrink-0" />}
                                    <ActionIcon className="w-4 h-4 text-stone-400 flex-shrink-0" />
                                    <span className="flex-1 text-sm font-medium text-stone-800 truncate">{s.title}</span>
                                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CATEGORY_COLORS[s.category] || "bg-stone-100 text-stone-600"}`}>
                                        {s.category.replace("_", " ")}
                                    </span>
                                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${PRIORITY_COLORS[s.priority] || ""}`}>
                                        {s.priority}
                                    </span>
                                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[s.status] || ""}`}>
                                        {s.status.replace("_", " ")}
                                    </span>
                                </button>
                                {expanded && (
                                    <div className="px-4 pb-4 border-t border-stone-100 pt-3 space-y-3">
                                        <p className="text-sm text-stone-600">{s.description}</p>
                                        <div className="flex flex-wrap gap-4 text-xs text-stone-500">
                                            <span>Source: {s.source}</span>
                                            <span>Action: {s.action_type || "—"}</span>
                                            {s.result_id && <span>Result: {s.result_type} ({s.result_id.slice(0, 8)}...)</span>}
                                            {s.approval_request_id && (
                                                <a href={`/approvals`} className="text-blue-600 hover:underline flex items-center gap-1">
                                                    View Approval <ExternalLink className="w-3 h-3" />
                                                </a>
                                            )}
                                        </div>
                                        {s.evidence && Object.keys(s.evidence).length > 0 && (
                                            <details className="text-xs">
                                                <summary className="cursor-pointer text-stone-500 hover:text-stone-700 font-medium">Evidence</summary>
                                                <pre className="mt-2 p-3 bg-stone-50 rounded-lg overflow-auto max-h-48 text-stone-600">
                                                    {JSON.stringify(s.evidence, null, 2)}
                                                </pre>
                                            </details>
                                        )}
                                        {(s.status === "proposed" || s.status === "pending_approval") && (
                                            <button
                                                onClick={() => onDismiss(s.id)}
                                                className="text-xs text-stone-500 hover:text-red-600 transition-colors"
                                            >
                                                Dismiss
                                            </button>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

function CompetitorTab({ runs }: { runs: EvolveRun[] }) {
    const competitorRuns = runs.filter(r => r.run_type === "competitor_monitor");
    const latestRun = competitorRuns[0];
    const competitorData = (latestRun?.stats as Record<string, unknown>)?.competitor_data as Record<string, unknown[]> | undefined;

    const [repos, setRepos] = useState<string[]>([]);
    const [newRepo, setNewRepo] = useState("");
    const [saving, setSaving] = useState(false);
    const [reposLoaded, setReposLoaded] = useState(false);
    const [repoError, setRepoError] = useState("");
    const [showSettings, setShowSettings] = useState(false);

    useEffect(() => {
        evolveApi.getCompetitorRepos().then(data => {
            setRepos(data.repos);
            setReposLoaded(true);
        }).catch(() => setReposLoaded(true));
    }, []);

    async function handleAddRepo() {
        const trimmed = newRepo.trim().replace(/^https?:\/\/(www\.)?github\.com\//, "").replace(/\/$/, "");
        if (!trimmed) return;
        if (trimmed.split("/").length !== 2) {
            setRepoError("Format: owner/repo");
            return;
        }
        if (repos.includes(trimmed)) {
            setRepoError("Already added");
            return;
        }
        setRepoError("");
        const updated = [...repos, trimmed];
        setSaving(true);
        try {
            const result = await evolveApi.updateCompetitorRepos(updated);
            setRepos(result.repos);
            setNewRepo("");
        } catch (e: any) {
            setRepoError(e?.message || "Failed to save");
        } finally {
            setSaving(false);
        }
    }

    async function handleRemoveRepo(repo: string) {
        const updated = repos.filter(r => r !== repo);
        setSaving(true);
        try {
            const result = await evolveApi.updateCompetitorRepos(updated);
            setRepos(result.repos);
        } catch { } finally {
            setSaving(false);
        }
    }

    return (
        <div className="space-y-4">
            {/* Repo management */}
            <div className="bg-white rounded-xl border border-stone-200 p-5">
                <button
                    onClick={() => setShowSettings(!showSettings)}
                    className="flex items-center gap-2 text-sm font-semibold text-stone-700 w-full"
                >
                    <Settings2 className="w-4 h-4 text-stone-400" />
                    Monitored Repositories
                    <span className="text-xs font-normal text-stone-400 ml-1">({repos.length})</span>
                    <ChevronDown className={`w-4 h-4 text-stone-400 ml-auto transition-transform ${showSettings ? "rotate-180" : ""}`} />
                </button>

                {showSettings && reposLoaded && (
                    <div className="mt-4 space-y-3">
                        <div className="flex flex-wrap gap-2">
                            {repos.map(repo => (
                                <div key={repo} className="flex items-center gap-1.5 px-3 py-1.5 bg-stone-50 border border-stone-200 rounded-lg text-sm">
                                    <a
                                        href={`https://github.com/${repo}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-stone-700 hover:text-blue-600 transition-colors"
                                    >
                                        {repo}
                                    </a>
                                    <button
                                        onClick={() => handleRemoveRepo(repo)}
                                        disabled={saving}
                                        className="text-stone-400 hover:text-red-500 transition-colors disabled:opacity-50"
                                    >
                                        <Trash2 className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                            ))}
                            {repos.length === 0 && (
                                <p className="text-xs text-stone-400">No repos configured. Add one below.</p>
                            )}
                        </div>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={newRepo}
                                onChange={e => { setNewRepo(e.target.value); setRepoError(""); }}
                                onKeyDown={e => e.key === "Enter" && handleAddRepo()}
                                placeholder="owner/repo or GitHub URL"
                                className="flex-1 px-3 py-2 bg-white border border-stone-200 rounded-lg text-sm text-stone-700 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400"
                            />
                            <button
                                onClick={handleAddRepo}
                                disabled={saving || !newRepo.trim()}
                                className="flex items-center gap-1.5 px-4 py-2 bg-stone-900 text-white rounded-lg text-sm font-medium hover:bg-stone-800 disabled:opacity-50"
                            >
                                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                                Add
                            </button>
                        </div>
                        {repoError && <p className="text-xs text-red-500">{repoError}</p>}
                    </div>
                )}
            </div>

            {/* Last scan info + competitor data */}
            {!latestRun ? (
                <div className="bg-white rounded-xl border border-stone-200 p-10 text-center text-stone-400">
                    <TrendingUp className="w-8 h-8 mx-auto mb-2 opacity-40" />
                    <p className="text-sm">No competitor data yet. Click &quot;Scan Competitors&quot; to start.</p>
                </div>
            ) : (
                <>
                    <div className="bg-white rounded-xl border border-stone-200 p-4">
                        <p className="text-xs text-stone-500">
                            Last scan: {latestRun.started_at ? new Date(latestRun.started_at).toLocaleString() : "—"}
                            {" · "}Status: <span className={latestRun.status === "completed" ? "text-green-600" : "text-amber-600"}>{latestRun.status}</span>
                            {" · "}{latestRun.suggestions_generated} suggestions generated
                        </p>
                    </div>
                    {competitorData && Object.entries(competitorData).map(([repo, releases]) => (
                        <div key={repo} className="bg-white rounded-xl border border-stone-200 p-5">
                            <div className="flex items-center gap-2 mb-3">
                                <div className="w-8 h-8 bg-stone-100 rounded-lg flex items-center justify-center">
                                    <TrendingUp className="w-4 h-4 text-stone-500" />
                                </div>
                                <div>
                                    <h3 className="text-sm font-semibold text-stone-800">{repo}</h3>
                                    <a
                                        href={`https://github.com/${repo}`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-xs text-blue-500 hover:underline flex items-center gap-1"
                                    >
                                        GitHub <ExternalLink className="w-3 h-3" />
                                    </a>
                                </div>
                            </div>
                            {Array.isArray(releases) ? (
                                <div className="space-y-2">
                                    {(releases as Array<{ tag?: string; name?: string; published_at?: string; body?: string }>).map((rel, i) => (
                                        <div key={i} className="pl-4 border-l-2 border-stone-200 py-1">
                                            <p className="text-sm font-medium text-stone-700">{rel.tag || rel.name || "Unnamed"}</p>
                                            <p className="text-xs text-stone-400">{rel.published_at ? new Date(rel.published_at).toLocaleDateString() : ""}</p>
                                            {rel.body && <p className="text-xs text-stone-500 mt-1 line-clamp-3">{rel.body}</p>}
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <p className="text-xs text-stone-400">No release data available</p>
                            )}
                        </div>
                    ))}
                </>
            )}
        </div>
    );
}

function RunStatusIcon({ status }: { status: string }) {
    switch (status) {
        case "completed": return <CheckCircle2 className="w-4 h-4 text-green-500" />;
        case "partial": return <AlertTriangle className="w-4 h-4 text-amber-500" />;
        case "failed": return <XCircle className="w-4 h-4 text-red-500" />;
        case "running": return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
        default: return <Clock className="w-4 h-4 text-stone-400" />;
    }
}
