"use client";

import { useEffect, useState } from "react";
import {
    BarChart3, TrendingUp, Users, Bot, CheckSquare, DollarSign,
    Loader2, RefreshCw, AlertTriangle, ChevronDown, Activity,
    Clock, Zap, Target, ArrowRight,
} from "lucide-react";
import {
    analyticsApi, teamsApi,
    type ExecutiveSummary, type AgentSummary, type AgentScorecard,
    type TeamAnalytics, type AnalyticsTrends,
} from "@/lib/api";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(usd: number): string {
    if (usd === 0) return "$0.00";
    if (usd < 0.0001) return `$${usd.toExponential(2)}`;
    if (usd < 0.01) return `$${usd.toFixed(6)}`;
    return `$${usd.toFixed(4)}`;
}

function fmtNum(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
}

function pct(n: number): string {
    return `${Math.round(n * 100)}%`;
}

function StatusDot({ status }: { status: string }) {
    const color =
        status === "running" ? "bg-green-500" :
        status === "error" ? "bg-red-500" :
        status === "starting" ? "bg-amber-500" : "bg-stone-300";
    return <span className={`inline-block w-2 h-2 rounded-full ${color}`} />;
}

const PERIODS = [
    { value: "day", label: "Today" },
    { value: "week", label: "This Week" },
    { value: "month", label: "This Month" },
    { value: "all", label: "All Time" },
];

// ─── Mini sparkline ───────────────────────────────────────────────────────────

function SparkBar({
    data,
    valueKey,
    color = "bg-stone-500",
}: {
    data: Record<string, number>[];
    valueKey: string;
    color?: string;
}) {
    const max = Math.max(...data.map(d => d[valueKey] ?? 0), 0.000001);
    return (
        <div className="flex items-end gap-px h-10 w-full">
            {data.map((d, i) => (
                <div
                    key={i}
                    className={`flex-1 ${color} rounded-t opacity-80 hover:opacity-100 transition-opacity`}
                    style={{ height: `${Math.max(((d[valueKey] ?? 0) / max) * 100, 2)}%` }}
                    title={`${d.date}: ${d[valueKey]}`}
                />
            ))}
        </div>
    );
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

function KPICard({
    label, value, sub, icon: Icon, color = "text-stone-700",
}: {
    label: string;
    value: string | number;
    sub?: string;
    icon: React.ElementType;
    color?: string;
}) {
    return (
        <div className="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
            <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide">{label}</p>
                <Icon className={`w-4 h-4 ${color}`} />
            </div>
            <p className="text-2xl font-bold text-stone-900">{value}</p>
            {sub && <p className="text-xs text-stone-400 mt-0.5">{sub}</p>}
        </div>
    );
}

// ─── Progress Bar ─────────────────────────────────────────────────────────────

function ProgressBar({ pct: p, color = "bg-stone-700" }: { pct: number; color?: string }) {
    const filled = Math.min(p * 100, 100);
    return (
        <div className="w-full h-1.5 bg-stone-100 rounded-full overflow-hidden">
            <div className={`h-full rounded-full ${color}`} style={{ width: `${filled}%` }} />
        </div>
    );
}

// ─── Executive Summary Tab ────────────────────────────────────────────────────

function ExecutiveTab({
    summary,
    trends,
    period,
    onPeriodChange,
}: {
    summary: ExecutiveSummary;
    trends: AnalyticsTrends | null;
    period: string;
    onPeriodChange: (p: string) => void;
}) {
    return (
        <div className="space-y-6 max-w-6xl">
            {/* Period selector */}
            <div className="flex gap-2">
                {PERIODS.map(p => (
                    <button
                        key={p.value}
                        onClick={() => onPeriodChange(p.value)}
                        className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                            period === p.value
                                ? "bg-stone-700 text-white border-stone-600"
                                : "border-stone-200 text-stone-600 hover:bg-stone-50"
                        }`}
                    >
                        {p.label}
                    </button>
                ))}
            </div>

            {/* Alerts */}
            {summary.approvals_pending > 0 && (
                <div className="flex items-center gap-2 px-4 py-2.5 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
                    <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                    <span><strong>{summary.approvals_pending}</strong> approval{summary.approvals_pending !== 1 ? "s" : ""} pending human review</span>
                    <a href="/approvals" className="ml-auto flex items-center gap-1 text-amber-700 font-medium hover:underline">
                        Review <ArrowRight className="w-3 h-3" />
                    </a>
                </div>
            )}

            {/* KPI grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                <KPICard label="Tasks Completed" value={fmtNum(summary.tasks_completed)} sub={`of ${fmtNum(summary.tasks_created)} created`} icon={CheckSquare} color="text-green-600" />
                <KPICard label="Completion Rate" value={pct(summary.completion_rate)} sub={`${fmtNum(summary.tasks_in_progress)} in progress`} icon={Target} color="text-stone-700" />
                <KPICard label="Avg Time to Done" value={`${summary.avg_time_to_done_hours}h`} sub="from creation to done" icon={Clock} color="text-purple-600" />
                <KPICard label="Total Cost" value={fmt(summary.total_cost_usd)} sub={summary.tasks_completed > 0 ? `${fmt(summary.cost_per_task)} / task` : "this period"} icon={DollarSign} color="text-emerald-600" />
                <KPICard label="LLM Requests" value={fmtNum(summary.total_requests)} sub={`${fmtNum(summary.total_tokens)} tokens`} icon={Zap} color="text-amber-600" />
                <KPICard label="Avg Latency" value={`${fmtNum(summary.avg_latency_ms)}ms`} sub="per request" icon={Activity} color="text-blue-600" />
                <KPICard label="Error Rate" value={pct(summary.error_rate)} sub={summary.error_rate < 0.05 ? "healthy" : "needs attention"} icon={AlertTriangle} color={summary.error_rate > 0.1 ? "text-red-600" : "text-stone-500"} />
                <KPICard label="Active Agents" value={summary.active_agents} sub={`of ${summary.total_agents} total`} icon={Bot} color="text-stone-700" />
            </div>

            {/* Trends chart */}
            {trends && (
                <div className="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
                    <h2 className="text-sm font-semibold text-stone-700 flex items-center gap-1.5 mb-4">
                        <TrendingUp className="w-4 h-4 text-stone-600" /> 30-Day Trends
                    </h2>
                    <div className="grid grid-cols-2 gap-6">
                        <div>
                            <p className="text-xs font-medium text-stone-500 mb-2">Daily Requests</p>
                            <SparkBar data={trends.data as any} valueKey="requests" color="bg-stone-500" />
                        </div>
                        <div>
                            <p className="text-xs font-medium text-stone-500 mb-2">Tasks Completed</p>
                            <SparkBar data={trends.data as any} valueKey="tasks_completed" color="bg-green-400" />
                        </div>
                        <div>
                            <p className="text-xs font-medium text-stone-500 mb-2">Daily Cost (USD)</p>
                            <SparkBar data={trends.data as any} valueKey="cost_usd" color="bg-emerald-400" />
                        </div>
                        <div>
                            <p className="text-xs font-medium text-stone-500 mb-2">Errors</p>
                            <SparkBar data={trends.data as any} valueKey="errors" color="bg-red-400" />
                        </div>
                    </div>
                    <div className="flex justify-between text-xs text-stone-400 mt-2">
                        <span>{trends.data[0]?.date}</span>
                        <span>{trends.data[trends.data.length - 1]?.date}</span>
                    </div>
                </div>
            )}

            {/* Top agents */}
            {summary.top_agents_by_tasks.length > 0 && (
                <div className="bg-white rounded-xl border border-stone-200 shadow-sm">
                    <div className="px-4 py-3 border-b border-stone-100">
                        <h2 className="text-sm font-semibold text-stone-700">Top Agents by Tasks Completed</h2>
                    </div>
                    <div className="p-4 space-y-3">
                        {summary.top_agents_by_tasks.map((a, i) => (
                            <div key={a.agent_id} className="flex items-center gap-3">
                                <span className="text-xs font-bold text-stone-400 w-5">#{i + 1}</span>
                                <span className="flex-1 text-sm font-medium text-stone-800">{a.agent_name}</span>
                                <span className="text-sm font-bold text-stone-700">{a.tasks_completed} tasks</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// ─── Agent Scorecards Tab ─────────────────────────────────────────────────────

function AgentRow({
    agent,
    onClick,
}: {
    agent: AgentSummary;
    onClick: () => void;
}) {
    return (
        <tr
            className="hover:bg-stone-50 cursor-pointer transition-colors"
            onClick={onClick}
        >
            <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                    <StatusDot status={agent.status} />
                    <span className="font-medium text-stone-800">{agent.agent_name}</span>
                </div>
                <p className="text-xs text-stone-400 ml-4">{agent.llm_provider} / {agent.llm_model}</p>
            </td>
            <td className="px-4 py-3 text-right text-stone-700">{fmtNum(agent.total_requests)}</td>
            <td className="px-4 py-3 text-right">
                <span className={`text-sm font-medium ${agent.error_rate > 0.1 ? "text-red-600" : "text-stone-600"}`}>
                    {pct(agent.error_rate)}
                </span>
            </td>
            <td className="px-4 py-3 text-right text-stone-600">{fmtNum(agent.avg_latency_ms)}ms</td>
            <td className="px-4 py-3 text-right font-mono text-stone-700">{fmt(agent.total_cost_usd)}</td>
            <td className="px-4 py-3 text-right">
                <span className="text-stone-700">{agent.tasks_completed}</span>
                <span className="text-stone-400 text-xs"> / {agent.tasks_assigned}</span>
            </td>
            <td className="px-4 py-3 text-right">
                <span className="text-stone-700 text-xs font-medium">Details →</span>
            </td>
        </tr>
    );
}

function ScorecardDetail({ scorecard, onBack }: { scorecard: AgentScorecard; onBack: () => void }) {
    return (
        <div className="space-y-6 max-w-4xl">
            <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-stone-500 hover:text-stone-800">
                ← Back to all agents
            </button>

            <div className="flex items-center gap-3">
                <StatusDot status={scorecard.status} />
                <div>
                    <h2 className="text-lg font-bold text-stone-900">{scorecard.agent_name}</h2>
                    <p className="text-sm text-stone-500">{scorecard.llm_provider} / {scorecard.llm_model}</p>
                </div>
            </div>

            {/* Metrics grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                <KPICard label="Requests" value={fmtNum(scorecard.total_requests)} sub={`${fmtNum(scorecard.total_tokens)} tokens`} icon={Zap} />
                <KPICard label="Error Rate" value={pct(scorecard.error_rate)} sub={`${scorecard.error_count} errors`} icon={AlertTriangle} color={scorecard.error_rate > 0.1 ? "text-red-600" : "text-stone-500"} />
                <KPICard label="Avg Latency" value={`${fmtNum(scorecard.avg_latency_ms)}ms`} icon={Clock} />
                <KPICard label="Total Cost" value={fmt(scorecard.total_cost_usd)} sub={`${fmt(scorecard.cost_per_request)} / request`} icon={DollarSign} color="text-emerald-600" />
                <KPICard label="Tasks Done" value={scorecard.tasks_completed} sub={`of ${scorecard.tasks_assigned} assigned`} icon={CheckSquare} color="text-green-600" />
                <KPICard label="Task Rate" value={pct(scorecard.task_completion_rate)} sub={`${scorecard.tasks_in_progress} in progress`} icon={Target} />
            </div>

            {/* Request trend */}
            {scorecard.daily_trend.length > 0 && (
                <div className="bg-white rounded-xl border border-stone-200 p-4 shadow-sm">
                    <p className="text-sm font-semibold text-stone-700 mb-3">Requests — Last 14 Days</p>
                    <SparkBar data={scorecard.daily_trend as any} valueKey="requests" color="bg-stone-500" />
                    <div className="flex justify-between text-xs text-stone-400 mt-1">
                        <span>{scorecard.daily_trend[0]?.date}</span>
                        <span>{scorecard.daily_trend[scorecard.daily_trend.length - 1]?.date}</span>
                    </div>
                </div>
            )}

            {/* Top tools */}
            {scorecard.top_tools.length > 0 && (
                <div className="bg-white rounded-xl border border-stone-200 shadow-sm">
                    <div className="px-4 py-3 border-b border-stone-100">
                        <h3 className="text-sm font-semibold text-stone-700">
                            Tool Usage ({scorecard.unique_tools_used} unique tools)
                        </h3>
                    </div>
                    <div className="p-4 space-y-2">
                        {scorecard.top_tools.map(t => {
                            const maxCount = scorecard.top_tools[0]?.count ?? 1;
                            return (
                                <div key={t.tool} className="flex items-center gap-3">
                                    <span className="text-xs font-mono text-stone-600 w-40 truncate">{t.tool}</span>
                                    <div className="flex-1">
                                        <ProgressBar pct={t.count / maxCount} />
                                    </div>
                                    <span className="text-xs text-stone-500 w-8 text-right">{t.count}</span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}

function AgentScorecardsTab({ period }: { period: string }) {
    const [agents, setAgents] = useState<AgentSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState<AgentScorecard | null>(null);
    const [loadingDetail, setLoadingDetail] = useState(false);

    useEffect(() => {
        setLoading(true);
        analyticsApi.allAgents(period)
            .then(d => setAgents(d.agents))
            .finally(() => setLoading(false));
    }, [period]);

    async function handleSelect(agentId: string) {
        setLoadingDetail(true);
        try {
            const scorecard = await analyticsApi.agentScorecard(agentId, period);
            setSelected(scorecard);
        } finally {
            setLoadingDetail(false);
        }
    }

    if (loadingDetail) {
        return <div className="flex items-center justify-center h-40"><Loader2 className="w-5 h-5 animate-spin text-stone-600" /></div>;
    }

    if (selected) {
        return <ScorecardDetail scorecard={selected} onBack={() => setSelected(null)} />;
    }

    if (loading) {
        return <div className="flex items-center justify-center h-40"><Loader2 className="w-5 h-5 animate-spin text-stone-600" /></div>;
    }

    if (agents.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-48 text-stone-400">
                <Bot className="w-10 h-10 mb-2 opacity-30" />
                <p className="text-sm">No agent data for this period</p>
            </div>
        );
    }

    return (
        <div className="max-w-6xl">
            <div className="bg-white rounded-xl border border-stone-200 shadow-sm overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-stone-50">
                        <tr>
                            <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Agent</th>
                            <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Requests</th>
                            <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Error Rate</th>
                            <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Latency</th>
                            <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Cost</th>
                            <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Tasks</th>
                            <th className="px-4 py-2.5"></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-stone-50">
                        {agents.map(agent => (
                            <AgentRow key={agent.agent_id} agent={agent} onClick={() => handleSelect(agent.agent_id)} />
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

// ─── Team Analytics Tab ───────────────────────────────────────────────────────

function TeamAnalyticsTab({ period }: { period: string }) {
    const [teams, setTeams] = useState<{ id: string; name: string; member_count: number }[]>([]);
    const [selectedTeamId, setSelectedTeamId] = useState<string>("");
    const [teamData, setTeamData] = useState<TeamAnalytics | null>(null);
    const [loading, setLoading] = useState(true);
    const [loadingTeam, setLoadingTeam] = useState(false);

    useEffect(() => {
        setLoading(true);
        analyticsApi.listTeams()
            .then(t => {
                setTeams(t);
                if (t.length > 0 && !selectedTeamId) setSelectedTeamId(t[0].id);
            })
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        if (!selectedTeamId) return;
        setLoadingTeam(true);
        analyticsApi.team(selectedTeamId, period)
            .then(setTeamData)
            .finally(() => setLoadingTeam(false));
    }, [selectedTeamId, period]);

    if (loading) {
        return <div className="flex items-center justify-center h-40"><Loader2 className="w-5 h-5 animate-spin text-stone-600" /></div>;
    }

    if (teams.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-48 text-stone-400">
                <Users className="w-10 h-10 mb-2 opacity-30" />
                <p className="text-sm">No teams yet — create teams in the Organization section</p>
                <a href="/org" className="mt-2 text-xs text-stone-700 hover:underline">Go to Organization →</a>
            </div>
        );
    }

    return (
        <div className="space-y-6 max-w-5xl">
            {/* Team selector */}
            <div className="flex items-center gap-3">
                <label className="text-sm font-medium text-stone-700">Team:</label>
                <div className="relative">
                    <select
                        value={selectedTeamId}
                        onChange={e => setSelectedTeamId(e.target.value)}
                        className="pl-3 pr-8 py-2 text-sm border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-stone-600 bg-white appearance-none"
                    >
                        {teams.map(t => (
                            <option key={t.id} value={t.id}>{t.name} ({t.member_count} members)</option>
                        ))}
                    </select>
                    <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400 pointer-events-none" />
                </div>
            </div>

            {loadingTeam && (
                <div className="flex items-center justify-center h-32">
                    <Loader2 className="w-5 h-5 animate-spin text-stone-600" />
                </div>
            )}

            {!loadingTeam && teamData && (
                <>
                    {/* Team KPIs */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                        <KPICard label="Members" value={teamData.member_count} icon={Users} />
                        <KPICard label="Tasks Completed" value={teamData.tasks_completed} sub={`of ${teamData.total_tasks} total`} icon={CheckSquare} color="text-green-600" />
                        <KPICard label="Total Cost" value={fmt(teamData.total_cost_usd)} icon={DollarSign} color="text-emerald-600" />
                        <KPICard label="LLM Requests" value={fmtNum(teamData.total_requests)} icon={Zap} />
                        <KPICard label="Discussions" value={teamData.discussions_participated} sub="participated in" icon={Activity} />
                        <KPICard label="Collaboration Index" value={teamData.collaboration_index} sub="multi-member discussions" icon={Users} color="text-purple-600" />
                    </div>

                    {/* Member breakdown */}
                    {teamData.members.length > 0 && (
                        <div className="bg-white rounded-xl border border-stone-200 shadow-sm overflow-hidden">
                            <div className="px-4 py-3 border-b border-stone-100">
                                <h3 className="text-sm font-semibold text-stone-700">Member Breakdown</h3>
                            </div>
                            <table className="w-full text-sm">
                                <thead className="bg-stone-50">
                                    <tr>
                                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Agent</th>
                                        <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Requests</th>
                                        <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Tasks Done</th>
                                        <th className="text-right px-4 py-2.5 text-xs font-semibold text-stone-500 uppercase tracking-wide">Cost</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-stone-50">
                                    {teamData.members.map(m => (
                                        <tr key={m.agent_id} className="hover:bg-stone-50">
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-2">
                                                    <StatusDot status={m.status} />
                                                    <span className="font-medium text-stone-800">{m.agent_name}</span>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-right text-stone-600">{fmtNum(m.requests)}</td>
                                            <td className="px-4 py-3 text-right">
                                                <span className="text-stone-700">{m.tasks_completed}</span>
                                                <span className="text-stone-400 text-xs"> / {m.tasks_assigned}</span>
                                            </td>
                                            <td className="px-4 py-3 text-right font-mono text-stone-700">{fmt(m.cost_usd)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

type Tab = "executive" | "scorecards" | "teams";

export default function AnalyticsPage() {
    const [tab, setTab] = useState<Tab>("executive");
    const [period, setPeriod] = useState("month");
    const [summary, setSummary] = useState<ExecutiveSummary | null>(null);
    const [trends, setTrends] = useState<AnalyticsTrends | null>(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    async function loadExecutive(showSpin = false) {
        if (showSpin) setRefreshing(true);
        try {
            const [s, t] = await Promise.all([
                analyticsApi.executive(period),
                analyticsApi.trends(30),
            ]);
            setSummary(s);
            setTrends(t);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }

    useEffect(() => {
        setLoading(true);
        loadExecutive();
    }, [period]);

    const TABS = [
        { key: "executive" as Tab, label: "Executive Summary", icon: BarChart3 },
        { key: "scorecards" as Tab, label: "Agent Scorecards", icon: Bot },
        { key: "teams" as Tab, label: "Team Analytics", icon: Users },
    ];

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-6 py-4 border-b border-stone-200 bg-white flex items-center justify-between gap-4">
                <div>
                    <h1 className="text-xl font-semibold text-stone-900 flex items-center gap-2">
                        <BarChart3 className="w-5 h-5 text-stone-700" />
                        Analytics
                    </h1>
                    <p className="text-sm text-stone-500">Performance insights, agent scorecards, and team metrics</p>
                </div>
                <button
                    onClick={() => loadExecutive(true)}
                    disabled={refreshing}
                    className="p-2 rounded-lg border border-stone-200 hover:bg-stone-50 text-stone-500"
                >
                    <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
                </button>
            </div>

            {/* Tabs */}
            <div className="px-6 pt-4 bg-white border-b border-stone-200 flex items-center gap-1">
                {TABS.map(t => (
                    <button
                        key={t.key}
                        onClick={() => setTab(t.key)}
                        className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
                            tab === t.key
                                ? "border-stone-600 text-stone-700"
                                : "border-transparent text-stone-500 hover:text-stone-700"
                        }`}
                    >
                        <t.icon className="w-4 h-4" />
                        {t.label}
                    </button>
                ))}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
                {tab === "executive" && (
                    loading ? (
                        <div className="flex items-center justify-center h-40">
                            <Loader2 className="w-6 h-6 animate-spin text-stone-600" />
                        </div>
                    ) : summary ? (
                        <ExecutiveTab
                            summary={summary}
                            trends={trends}
                            period={period}
                            onPeriodChange={setPeriod}
                        />
                    ) : null
                )}

                {tab === "scorecards" && (
                    <div className="space-y-4">
                        {/* Period selector for scorecards */}
                        <div className="flex gap-2">
                            {PERIODS.map(p => (
                                <button
                                    key={p.value}
                                    onClick={() => setPeriod(p.value)}
                                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                                        period === p.value
                                            ? "bg-stone-700 text-white border-stone-600"
                                            : "border-stone-200 text-stone-600 hover:bg-stone-50"
                                    }`}
                                >
                                    {p.label}
                                </button>
                            ))}
                        </div>
                        <AgentScorecardsTab period={period} />
                    </div>
                )}

                {tab === "teams" && (
                    <div className="space-y-4">
                        {/* Period selector for teams */}
                        <div className="flex gap-2">
                            {PERIODS.map(p => (
                                <button
                                    key={p.value}
                                    onClick={() => setPeriod(p.value)}
                                    className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                                        period === p.value
                                            ? "bg-stone-700 text-white border-stone-600"
                                            : "border-stone-200 text-stone-600 hover:bg-stone-50"
                                    }`}
                                >
                                    {p.label}
                                </button>
                            ))}
                        </div>
                        <TeamAnalyticsTab period={period} />
                    </div>
                )}
            </div>
        </div>
    );
}
