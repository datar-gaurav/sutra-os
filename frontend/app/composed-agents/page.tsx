"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Trash2, ShieldCheck } from "lucide-react";
import { composedAgentsApi, type ComposedAgent } from "@/lib/api";

export default function ComposedAgentsPage() {
    const [agents, setAgents] = useState<ComposedAgent[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        load();
    }, []);

    async function load() {
        try {
            setAgents(await composedAgentsApi.list());
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }

    async function handleDelete(id: string, name: string) {
        if (!confirm(`Delete composed agent "${name}"? This cannot be undone.`)) return;
        try {
            await composedAgentsApi.delete(id);
            setAgents(agents.filter((a) => a.id !== id));
        } catch (err) {
            console.error(err);
            alert("Failed to delete.");
        }
    }

    async function create() {
        const name = prompt("Name for the new composed agent?");
        if (!name) return;
        try {
            const a = await composedAgentsApi.create({ name });
            window.location.href = `/composed-agents/${a.id}`;
        } catch (err: any) {
            console.error(err);
            alert(`Failed to create: ${err?.message || err}`);
        }
    }

    return (
        <div className="p-6 max-w-6xl mx-auto">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <ShieldCheck className="w-6 h-6" />
                        Composed Agents
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Graph-defined agents with guardrails and evals. Use these when you need
                        input/output checks, structured flows, or branching logic.
                    </p>
                </div>
                <button
                    onClick={create}
                    className="flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700"
                >
                    <Plus className="w-4 h-4" /> New
                </button>
            </div>

            {loading ? (
                <div className="text-gray-500">Loading…</div>
            ) : agents.length === 0 ? (
                <div className="text-center py-16 border-2 border-dashed border-gray-200 rounded-lg">
                    <ShieldCheck className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                    <div className="text-gray-500">No composed agents yet.</div>
                    <button
                        onClick={create}
                        className="mt-4 px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700"
                    >
                        Create your first
                    </button>
                </div>
            ) : (
                <div className="grid gap-3">
                    {agents.map((a) => (
                        <div
                            key={a.id}
                            className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:border-amber-400 transition"
                        >
                            <div className="flex-1 min-w-0">
                                <Link
                                    href={`/composed-agents/${a.id}`}
                                    className="font-semibold hover:text-amber-700"
                                >
                                    {a.name}
                                </Link>
                                <div className="text-sm text-gray-500 truncate">
                                    {a.description || <span className="italic">No description</span>}
                                </div>
                                <div className="text-xs text-gray-400 mt-1">
                                    v{a.version}
                                    {a.published_version !== null && (
                                        <span> · published v{a.published_version}</span>
                                    )}
                                </div>
                            </div>
                            <button
                                onClick={() => handleDelete(a.id, a.name)}
                                className="p-2 text-gray-400 hover:text-red-600"
                                title="Delete"
                            >
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
