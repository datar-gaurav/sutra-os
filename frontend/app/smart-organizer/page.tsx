"use client";

import { useCallback, useEffect, useState } from "react";
import {
    Inbox,
    RefreshCw,
    Download,
    Loader2,
    AlertCircle,
    ExternalLink,
} from "lucide-react";
import Link from "next/link";
import {
    smartOrganizerApi,
    type SmartOrganizerOverview,
    type SmartOrganizerQueueItem,
    type SmartOrganizerDigest,
    type SmartOrganizerPrior,
    type SmartOrganizerFeedback,
    type SmartOrganizerAuditEntry,
} from "@/lib/api";

type TabId = "queue" | "digest" | "review" | "rules" | "learning" | "audit";

const TABS: { id: TabId; label: string }[] = [
    { id: "queue", label: "Queue" },
    { id: "digest", label: "Digest" },
    { id: "review", label: "Needs Review" },
    { id: "rules", label: "Rules" },
    { id: "learning", label: "Learning" },
    { id: "audit", label: "Audit" },
];

function labelClass(label: string | null): string {
    switch (label) {
        case "Actionable":
            return "bg-emerald-50 text-emerald-700 border-emerald-200";
        case "Important-FYI":
            return "bg-blue-50 text-blue-700 border-blue-200";
        case "Junk":
            return "bg-gray-100 text-gray-500 border-gray-200";
        default:
            return "bg-gray-50 text-gray-500 border-gray-200";
    }
}

function Badge({ children, className = "" }: { children: React.ReactNode; className?: string }) {
    return (
        <span className={`inline-block px-2 py-0.5 rounded-full text-xs border ${className}`}>
            {children}
        </span>
    );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
    return (
        <div className="bg-white border border-gray-200 rounded-lg px-4 py-3">
            <div className="text-2xl font-semibold text-gray-900">{value}</div>
            <div className="text-xs text-gray-500 mt-0.5">{label}</div>
        </div>
    );
}

export default function SmartOrganizerPage() {
    const [activeTab, setActiveTab] = useState<TabId>("queue");
    const [overview, setOverview] = useState<SmartOrganizerOverview | null>(null);
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadOverview = useCallback(async () => {
        try {
            setOverview(await smartOrganizerApi.overview());
        } catch (e: any) {
            setError(e.message || "Failed to load overview");
        }
    }, []);

    const loadTab = useCallback(async (tab: TabId) => {
        setError(null);
        if (tab === "rules") {
            setData(null);
            return;
        }
        setLoading(true);
        try {
            let result: any;
            if (tab === "queue") result = await smartOrganizerApi.queue();
            else if (tab === "digest") result = await smartOrganizerApi.digest();
            else if (tab === "review") result = await smartOrganizerApi.needsReview();
            else if (tab === "learning")
                result = {
                    priors: await smartOrganizerApi.priors(),
                    feedback: await smartOrganizerApi.feedback(),
                };
            else if (tab === "audit") result = await smartOrganizerApi.audit();
            setData(result);
        } catch (e: any) {
            setError(e.message || "Failed to load data");
            setData(null);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadOverview();
    }, [loadOverview]);

    useEffect(() => {
        loadTab(activeTab);
    }, [activeTab, loadTab]);

    const refresh = () => {
        loadOverview();
        loadTab(activeTab);
    };

    return (
        <div className="p-6 max-w-7xl mx-auto space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Inbox className="w-6 h-6 text-stone-700" />
                    <div>
                        <h1 className="text-xl font-semibold text-gray-900">Smart Organizer</h1>
                        <p className="text-sm text-gray-500">
                            Apple Mail triage — queue, digest, and what it&apos;s learning.
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <a
                        href={smartOrganizerApi.csvUrl()}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-700"
                    >
                        <Download className="w-4 h-4" /> Queue CSV
                    </a>
                    <button
                        onClick={refresh}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-700"
                    >
                        <RefreshCw className="w-4 h-4" /> Refresh
                    </button>
                </div>
            </div>

            {/* Overview stats */}
            {overview && (
                <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                    <StatCard label="Pending" value={overview.queue.pending ?? 0} />
                    <StatCard label="Classified" value={overview.queue.classified ?? 0} />
                    <StatCard label="Routed" value={overview.queue.routed ?? 0} />
                    <StatCard label="Needs review" value={overview.needs_review} />
                    <StatCard label="Sender priors" value={overview.sender_priors} />
                    <StatCard label="Corrections" value={overview.corrections} />
                </div>
            )}

            {/* Tabs */}
            <div className="border-b border-gray-200 flex gap-1">
                {TABS.map((t) => (
                    <button
                        key={t.id}
                        onClick={() => setActiveTab(t.id)}
                        className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                            activeTab === t.id
                                ? "border-stone-800 text-stone-800"
                                : "border-transparent text-gray-500 hover:text-gray-700"
                        }`}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {/* Body */}
            {error && (
                <div className="flex items-center gap-2 bg-red-50 text-red-700 text-sm px-4 py-3 rounded-lg border border-red-200">
                    <AlertCircle className="w-4 h-4" /> {error}
                </div>
            )}
            {loading ? (
                <div className="flex items-center gap-2 text-gray-400 text-sm py-12 justify-center">
                    <Loader2 className="w-4 h-4 animate-spin" /> Loading…
                </div>
            ) : (
                <div>
                    {activeTab === "queue" && <QueueTable rows={data ?? []} />}
                    {activeTab === "review" && <ReviewTable rows={data ?? []} />}
                    {activeTab === "digest" && <DigestView digest={data} />}
                    {activeTab === "learning" && <LearningView data={data} />}
                    {activeTab === "audit" && <AuditTable rows={data ?? []} />}
                    {activeTab === "rules" && <RulesPanel />}
                </div>
            )}
        </div>
    );
}

function Empty({ text }: { text: string }) {
    return <div className="text-sm text-gray-400 py-10 text-center">{text}</div>;
}

function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
    return (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
                <thead>
                    <tr className="text-left text-gray-500 border-b border-gray-100">
                        {head.map((h) => (
                            <th key={h} className="px-4 py-2 font-medium">
                                {h}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>{children}</tbody>
            </table>
        </div>
    );
}

function QueueTable({ rows }: { rows: SmartOrganizerQueueItem[] }) {
    if (!rows.length) return <Empty text="Queue is empty." />;
    return (
        <Table head={["Sender", "Subject", "State", "Label", "Conf.", "Due"]}>
            {rows.map((r) => (
                <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-4 py-2 text-gray-700 whitespace-nowrap">{r.sender}</td>
                    <td className="px-4 py-2 text-gray-900 max-w-md truncate">
                        {r.subject}
                        {r.urgency === "urgent" && (
                            <Badge className="ml-2 bg-red-50 text-red-600 border-red-200">urgent</Badge>
                        )}
                    </td>
                    <td className="px-4 py-2 text-gray-500">{r.state}</td>
                    <td className="px-4 py-2">
                        {r.label && <Badge className={labelClass(r.label)}>{r.label}</Badge>}
                        {r.escalated ? (
                            <Badge className="ml-1 bg-purple-50 text-purple-600 border-purple-200">esc</Badge>
                        ) : null}
                    </td>
                    <td className="px-4 py-2 text-gray-500">
                        {r.confidence != null ? r.confidence.toFixed(2) : "—"}
                    </td>
                    <td className="px-4 py-2 text-gray-500 whitespace-nowrap">{r.due_date ?? "—"}</td>
                </tr>
            ))}
        </Table>
    );
}

function ReviewTable({ rows }: { rows: SmartOrganizerQueueItem[] }) {
    if (!rows.length) return <Empty text="Nothing awaiting review." />;
    return (
        <Table head={["Sender", "Subject", "Label", "Summary", "Conf."]}>
            {rows.map((r) => (
                <tr key={r.message_ref} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-4 py-2 text-gray-700 whitespace-nowrap">{r.sender}</td>
                    <td className="px-4 py-2 text-gray-900 max-w-xs truncate">{r.subject}</td>
                    <td className="px-4 py-2">
                        {r.label && <Badge className={labelClass(r.label)}>{r.label}</Badge>}
                    </td>
                    <td className="px-4 py-2 text-gray-600 max-w-sm truncate">{r.summary ?? "—"}</td>
                    <td className="px-4 py-2 text-gray-500">
                        {r.confidence != null ? r.confidence.toFixed(2) : "—"}
                    </td>
                </tr>
            ))}
        </Table>
    );
}

function DigestView({ digest }: { digest: SmartOrganizerDigest | null }) {
    if (!digest) return <Empty text="No digest yet." />;
    const section = (
        title: string,
        items: SmartOrganizerDigest["actionable"]
    ) => (
        <div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">
                {title} <span className="text-gray-400">({items.length})</span>
            </h3>
            {items.length ? (
                <div className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-50">
                    {items.map((it, i) => (
                        <div key={i} className="px-4 py-2.5">
                            <div className="text-sm text-gray-900">{it.summary || it.subject}</div>
                            <div className="text-xs text-gray-400 mt-0.5">
                                {it.sender}
                                {it.due_date ? ` · due ${it.due_date}` : ""}
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <Empty text="Nothing here today." />
            )}
        </div>
    );
    return (
        <div className="grid md:grid-cols-2 gap-6">
            {section("Actionable → Reminders", digest.actionable)}
            {section("Important-FYI → Daily Note", digest.fyi)}
        </div>
    );
}

function LearningView({
    data,
}: {
    data: { priors: SmartOrganizerPrior[]; feedback: SmartOrganizerFeedback[] } | null;
}) {
    if (!data) return <Empty text="No learning data yet." />;
    return (
        <div className="grid md:grid-cols-2 gap-6">
            <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">Sender importance priors</h3>
                {data.priors.length ? (
                    <Table head={["Sender", "Score", "Samples"]}>
                        {data.priors.map((p) => (
                            <tr key={p.sender} className="border-b border-gray-50">
                                <td className="px-4 py-2 text-gray-700">{p.sender}</td>
                                <td
                                    className={`px-4 py-2 font-medium ${
                                        p.score >= 0 ? "text-emerald-600" : "text-red-600"
                                    }`}
                                >
                                    {p.score >= 0 ? "+" : ""}
                                    {p.score.toFixed(2)}
                                </td>
                                <td className="px-4 py-2 text-gray-500">{p.sample_count}</td>
                            </tr>
                        ))}
                    </Table>
                ) : (
                    <Empty text="No priors learned yet." />
                )}
            </div>
            <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">Recent corrections</h3>
                {data.feedback.length ? (
                    <Table head={["Sender", "Model → Correct"]}>
                        {data.feedback.map((f) => (
                            <tr key={f.id} className="border-b border-gray-50">
                                <td className="px-4 py-2 text-gray-700">{f.sender}</td>
                                <td className="px-4 py-2 text-gray-600">
                                    <span className="text-gray-400">{f.model_label ?? "?"}</span> →{" "}
                                    <Badge className={labelClass(f.user_label)}>{f.user_label}</Badge>
                                </td>
                            </tr>
                        ))}
                    </Table>
                ) : (
                    <Empty text="No corrections recorded yet." />
                )}
            </div>
        </div>
    );
}

function AuditTable({ rows }: { rows: SmartOrganizerAuditEntry[] }) {
    if (!rows.length) return <Empty text="No decisions logged yet." />;
    return (
        <Table head={["Tier", "Decision", "Conf.", "When"]}>
            {rows.map((r) => (
                <tr key={r.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-4 py-2">
                        <Badge className="bg-gray-100 text-gray-600 border-gray-200">{r.tier}</Badge>
                    </td>
                    <td className="px-4 py-2 text-gray-700 font-mono text-xs">{r.decision}</td>
                    <td className="px-4 py-2 text-gray-500">
                        {r.confidence != null ? r.confidence.toFixed(2) : "—"}
                    </td>
                    <td className="px-4 py-2 text-gray-400 whitespace-nowrap">{r.timestamp}</td>
                </tr>
            ))}
        </Table>
    );
}

function RulesPanel() {
    return (
        <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-3">
            <h3 className="text-sm font-medium text-gray-800">Tier 0 rules</h3>
            <p className="text-sm text-gray-500 max-w-xl">
                Sender allow/block lists and discard regexes are configured on the Smart Organizer
                integration. Edit them there; use the agent tool{" "}
                <code className="px-1 py-0.5 bg-gray-100 rounded text-xs">smart_organizer_test_rules</code>{" "}
                to dry-run a rule against a sample.
            </p>
            <Link
                href="/integrations"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-700"
            >
                Open Integrations <ExternalLink className="w-3.5 h-3.5" />
            </Link>
        </div>
    );
}
