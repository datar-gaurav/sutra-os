"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
    Bot,
    Cpu,
    MessageSquare,
    Activity,
    Zap,
    ArrowRight,
    Server,
    CheckCircle2,
    XCircle,
} from "lucide-react";
import { agentsApi, systemApi, type Agent } from "@/lib/api";
import AgentAvatar from "@/components/AgentAvatar";

export default function DashboardPage() {
    const [agents, setAgents] = useState<Agent[]>([]);
    const [health, setHealth] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function load() {
            try {
                const [agentList, healthData] = await Promise.all([
                    agentsApi.list(),
                    systemApi.health(),
                ]);
                setAgents(agentList);
                setHealth(healthData);
            } catch (err) {
                console.error("Failed to load dashboard:", err);
            } finally {
                setLoading(false);
            }
        }
        load();
    }, []);

    const runningAgents = agents.filter((a) => a.status === "running");
    const totalAgents = agents.length;

    const stats = [
        {
            label: "Total Agents",
            value: totalAgents,
            icon: Bot,
            color: "from-stone-700 to-stone-900",
            shadow: "shadow-stone-600/20",
        },
        {
            label: "Running",
            value: runningAgents.length,
            icon: Zap,
            color: "from-emerald-500 to-emerald-700",
            shadow: "shadow-emerald-600/20",
        },
        {
            label: "Conversations",
            value: "—",
            icon: MessageSquare,
            color: "from-violet-500 to-violet-700",
            shadow: "shadow-violet-600/20",
        },
        {
            label: "Uptime",
            value: "Online",
            icon: Activity,
            color: "from-amber-500 to-amber-700",
            shadow: "shadow-amber-600/20",
        },
    ];

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-stone-900 dark:text-white">
                    Dashboard
                </h1>
                <p className="text-sm text-stone-500 dark:text-stone-400 mt-1">
                    Overview of your AI agent ecosystem
                </p>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {stats.map((stat) => (
                    <div key={stat.label} className="glass-card p-4 animate-slide-up">
                        <div className="flex items-center gap-4">
                            <div
                                className={`w-10 h-10 rounded-lg bg-gradient-to-br ${stat.color} flex items-center justify-center shadow-sm ${stat.shadow} shrink-0`}
                            >
                                <stat.icon className="w-5 h-5 text-white" />
                            </div>
                            <div>
                                <p className="text-xs font-medium text-stone-500 dark:text-stone-400 uppercase tracking-wider">
                                    {stat.label}
                                </p>
                                <p className="text-xl font-semibold text-stone-900 dark:text-white mt-0.5">
                                    {loading ? "..." : stat.value}
                                </p>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* System Status + Agents Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* System Status */}
                <div className="glass-card p-5">
                    <h2 className="text-base font-semibold text-stone-900 dark:text-white mb-4 flex items-center gap-2">
                        <Server className="w-4 h-4 text-stone-600" />
                        System Status
                    </h2>
                    <div className="space-y-2.5">
                        <StatusRow
                            label="Backend API"
                            connected={!!health}
                        />
                        <StatusRow
                            label="Ollama"
                            connected={health?.ollama_connected ?? false}
                        />
                        <StatusRow
                            label="Database"
                            connected={health?.db_connected ?? false}
                        />
                        <StatusRow
                            label="Redis"
                            connected={health?.redis_connected ?? false}
                        />
                    </div>
                </div>

                {/* Active Agents */}
                <div className="lg:col-span-2 glass-card p-6">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                            <Bot className="w-5 h-5 text-stone-600" />
                            Active Agents
                        </h2>
                        <Link
                            href="/agents"
                            className="text-sm text-stone-600 hover:text-stone-500 flex items-center gap-1 transition-colors"
                        >
                            View All <ArrowRight className="w-4 h-4" />
                        </Link>
                    </div>

                    {loading ? (
                        <div className="text-center py-8 text-gray-400">Loading...</div>
                    ) : agents.length === 0 ? (
                        <div className="text-center py-12">
                            <Bot className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
                            <p className="text-gray-500 dark:text-gray-400 mb-4">
                                No agents configured yet
                            </p>
                            <Link href="/agents/new" className="btn-primary inline-flex items-center gap-2">
                                <Zap className="w-4 h-4" />
                                Create First Agent
                            </Link>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {agents.slice(0, 5).map((agent) => (
                                <Link
                                    key={agent.id}
                                    href={`/agents/${agent.id}`}
                                    className="flex items-center justify-between p-3 rounded-xl hover:bg-surface-2 dark:hover:bg-surface-dark3 transition-colors group"
                                >
                                    <div className="flex items-center gap-3">
                                        <AgentAvatar name={agent.name} avatarUrl={agent.avatar_url} size="md" />
                                        <div>
                                            <p className="font-medium text-gray-900 dark:text-white text-sm">
                                                {agent.name}
                                            </p>
                                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                                {agent.llm_provider}/{agent.llm_model}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <div
                                            className={`status-dot ${agent.status === "running"
                                                ? "status-dot-running"
                                                : agent.status === "starting"
                                                    ? "status-dot-starting"
                                                    : agent.status === "error"
                                                        ? "status-dot-error"
                                                        : "status-dot-stopped"
                                                }`}
                                        />
                                        <span className="text-xs text-gray-400 capitalize">
                                            {agent.status}
                                        </span>
                                        <ArrowRight className="w-4 h-4 text-gray-300 dark:text-gray-600 opacity-0 group-hover:opacity-100 transition-opacity" />
                                    </div>
                                </Link>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function StatusRow({ label, connected }: { label: string; connected: boolean }) {
    return (
        <div className="flex items-center justify-between py-1">
            <span className="text-sm text-gray-600 dark:text-gray-300">{label}</span>
            <div className="flex items-center gap-1.5">
                {connected ? (
                    <>
                        <CheckCircle2 className="w-4 h-4 text-accent-success" />
                        <span className="text-xs text-accent-success">Connected</span>
                    </>
                ) : (
                    <>
                        <XCircle className="w-4 h-4 text-accent-error" />
                        <span className="text-xs text-accent-error">Offline</span>
                    </>
                )}
            </div>
        </div>
    );
}
