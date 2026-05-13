"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fleetApi, FleetJob, FleetStatus, FleetWorkerHealth, systemSettingsApi } from "@/lib/api";

// ─── Status helpers ──────────────────────────────────────────────────────────

const STATUS_LABEL: Record<FleetStatus, string> = {
    queued: "Queued",
    claimed: "Claimed",
    running: "Running",
    pushing: "Pushing",
    pr_created: "PR Created",
    failed: "Failed",
    cancelled: "Cancelled",
};

const STATUS_COLOR: Record<FleetStatus, string> = {
    queued: "bg-stone-100 text-stone-600",
    claimed: "bg-blue-100 text-blue-700",
    running: "bg-orange-100 text-orange-700",
    pushing: "bg-purple-100 text-purple-700",
    pr_created: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
    cancelled: "bg-stone-100 text-stone-500",
};

function StatusBadge({ status }: { status: FleetStatus }) {
    return (
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_COLOR[status]}`}>
            {STATUS_LABEL[status]}
        </span>
    );
}

function relativeTime(iso: string): string {
    const ms = Date.now() - new Date(iso).getTime();
    const s = Math.floor(ms / 1000);
    if (s < 60) return `${s}s ago`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
}


// ─── First-time setup help (Gemini OAuth) ────────────────────────────────────

function SetupHelp({ health }: { health: FleetWorkerHealth | null }) {
    const missingCreds = !!health?.online && health.auth_ready === false;
    const [open, setOpen] = useState(missingCreds);
    useEffect(() => { if (missingCreds) setOpen(true); }, [missingCreds]);

    if (!health) return null;
    const home = health.gemini_home || "~/.gemini-fleet-home";

    const tone = missingCreds
        ? "border-amber-300 bg-amber-50"
        : "border-stone-200 bg-stone-50";
    const heading = missingCreds
        ? "Finish setup — Gemini OAuth missing"
        : "First-time setup help";
    const intro = missingCreds
        ? "The worker is online but cannot reach Gemini until you complete OAuth into its sandboxed HOME. Run the steps below once on this Mac."
        : "Already working — keep this around in case you ever rotate creds or set up a new host.";

    return (
        <div className={`border rounded-lg p-4 ${tone}`}>
            <button
                onClick={() => setOpen(o => !o)}
                className="w-full flex items-center justify-between text-left"
            >
                <div>
                    <h2 className="text-sm font-semibold">{heading}</h2>
                    <p className="text-xs text-stone-600 mt-0.5">{intro}</p>
                </div>
                <span className="text-stone-500 text-sm">{open ? "▾" : "▸"}</span>
            </button>

            {open && (
                <div className="mt-3 space-y-3 text-sm text-stone-700">
                    <ol className="list-decimal list-inside space-y-2">
                        <li>
                            In a terminal on the host (this Mac), run Gemini with HOME redirected to the fleet sandbox:
                            <CodeBlock>{`HOME=${home} gemini`}</CodeBlock>
                        </li>
                        <li>
                            Pick <span className="font-mono bg-white border border-stone-200 px-1 rounded">Login with Google</span> in the auth picker. Complete the browser flow.
                        </li>
                        <li>
                            Back in the terminal, type <span className="font-mono bg-white border border-stone-200 px-1 rounded">/quit</span> to exit. OAuth is saved.
                        </li>
                        <li>
                            Verify the creds file landed in the right place:
                            <CodeBlock>{`ls ${home}/.gemini/oauth_creds.json`}</CodeBlock>
                        </li>
                        <li>
                            <span className="text-stone-500">(Optional, only if you also use a personal Gemini API key in <span className="font-mono">~/.env</span>):</span> the worker passes a scrubbed env to Gemini, so stray <span className="font-mono">GEMINI_API_KEY</span> / <span className="font-mono">GOOGLE_GENAI_USE_*</span> in your shell rc won't leak in — but if Gemini auto-loads a <span className="font-mono">.env</span> walking up from the workspace, it can. Keep <span className="font-mono">~/.env</span> clean of those vars.
                        </li>
                    </ol>
                    <p className="text-xs text-stone-500">
                        The worker re-reads OAuth creds on every job — no restart needed after step 4.
                    </p>
                </div>
            )}
        </div>
    );
}

function CodeBlock({ children }: { children: string }) {
    const [copied, setCopied] = useState(false);
    return (
        <div className="relative mt-1.5">
            <pre className="bg-stone-900 text-stone-100 rounded px-3 py-2 text-xs font-mono overflow-x-auto">{children}</pre>
            <button
                onClick={() => {
                    navigator.clipboard.writeText(children);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1200);
                }}
                className="absolute top-1.5 right-1.5 text-xs text-stone-400 hover:text-stone-100 bg-stone-800 px-2 py-0.5 rounded"
            >
                {copied ? "Copied" : "Copy"}
            </button>
        </div>
    );
}


// ─── Repos config (FLEET_REPOS) ──────────────────────────────────────────────

function RepoConfig() {
    const [value, setValue] = useState<string | null>(null);
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState("");
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState<string | null>(null);

    async function load() {
        try {
            const schema = await systemSettingsApi.get();
            const v = (schema.fleet_repos?.value ?? "") as string;
            setValue(v);
            setDraft(v);
        } catch (e: any) {
            setErr(e.message || "load failed");
        }
    }

    useEffect(() => { load(); }, []);

    async function save() {
        setBusy(true);
        setErr(null);
        try {
            const cleaned = draft
                .split(/[,\n]/)
                .map(s => s.trim())
                .filter(Boolean)
                .join(",");
            await systemSettingsApi.update({ fleet_repos: cleaned });
            setValue(cleaned);
            setDraft(cleaned);
            setEditing(false);
        } catch (e: any) {
            setErr(e.message || "save failed");
        } finally {
            setBusy(false);
        }
    }

    const repos = (value || "").split(",").map(s => s.trim()).filter(Boolean);

    return (
        <div className="border border-stone-200 rounded-lg bg-white p-4">
            <div className="flex items-center justify-between mb-2">
                <div>
                    <h2 className="text-sm font-semibold">Configured repos</h2>
                    <p className="text-xs text-stone-500">Hourly triage scans these for candidate issues. Edit syncs to <code className="bg-stone-100 px-1 rounded">fleet_repos</code> live — no restart needed.</p>
                </div>
                {!editing && (
                    <button
                        onClick={() => { setEditing(true); setDraft(value || ""); }}
                        className="text-sm text-stone-600 hover:text-stone-900 underline"
                    >
                        Edit
                    </button>
                )}
            </div>
            {err && <div className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded mb-2">{err}</div>}
            {!editing ? (
                repos.length === 0 ? (
                    <div className="text-sm text-stone-500">No repos configured. <button onClick={() => setEditing(true)} className="text-blue-600 hover:underline">Add one</button>.</div>
                ) : (
                    <div className="flex flex-wrap gap-1.5">
                        {repos.map(r => (
                            <span key={r} className="text-xs font-mono bg-stone-100 text-stone-700 px-2 py-0.5 rounded">
                                {r}
                            </span>
                        ))}
                    </div>
                )
            ) : (
                <div className="space-y-2">
                    <textarea
                        value={draft}
                        onChange={e => setDraft(e.target.value)}
                        rows={3}
                        placeholder="owner/repo, owner2/repo2&#10;(one per line or comma-separated)"
                        className="w-full border border-stone-200 rounded px-2 py-1.5 text-sm font-mono"
                    />
                    <div className="flex justify-end gap-2">
                        <button
                            onClick={() => { setEditing(false); setDraft(value || ""); setErr(null); }}
                            className="px-3 py-1 text-sm text-stone-600 hover:text-stone-900"
                        >
                            Cancel
                        </button>
                        <button
                            disabled={busy}
                            onClick={save}
                            className="px-3 py-1 bg-stone-800 text-white rounded text-sm disabled:opacity-50"
                        >
                            {busy ? "Saving…" : "Save"}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}


// ─── New-job form ────────────────────────────────────────────────────────────

function NewJobForm({ onCreated, onCancel }: { onCreated: () => void; onCancel: () => void }) {
    const [repo, setRepo] = useState("");
    const [title, setTitle] = useState("");
    const [prompt, setPrompt] = useState("");
    const [issueRef, setIssueRef] = useState("");
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState<string | null>(null);

    async function submit() {
        if (!repo.trim() || !prompt.trim()) {
            setErr("repo and prompt are required");
            return;
        }
        setBusy(true);
        setErr(null);
        try {
            await fleetApi.create({
                repo_url: repo.trim(),
                title: title.trim() || undefined,
                prompt: prompt.trim(),
                issue_ref: issueRef.trim() || undefined,
            });
            onCreated();
        } catch (e: any) {
            setErr(e.message || "create failed");
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="border border-stone-200 rounded-lg p-4 bg-white space-y-3">
            <div className="flex items-center justify-between">
                <h2 className="font-semibold">New fleet job</h2>
                <button onClick={onCancel} className="text-stone-500 hover:text-stone-700 text-sm">Cancel</button>
            </div>
            {err && <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded">{err}</div>}
            <input
                value={repo} onChange={e => setRepo(e.target.value)}
                placeholder="owner/repo (e.g. me/proj-a)"
                className="w-full border border-stone-200 rounded px-3 py-2 text-sm"
            />
            <input
                value={title} onChange={e => setTitle(e.target.value)}
                placeholder="Short title (optional — first 80 chars of prompt by default)"
                className="w-full border border-stone-200 rounded px-3 py-2 text-sm"
            />
            <input
                value={issueRef} onChange={e => setIssueRef(e.target.value)}
                placeholder="Issue ref (optional, e.g. #42 — gets surfaced in PR body)"
                className="w-full border border-stone-200 rounded px-3 py-2 text-sm"
            />
            <textarea
                value={prompt} onChange={e => setPrompt(e.target.value)}
                placeholder="Task for the agent. Be specific — minimal changes, focused scope."
                rows={5}
                className="w-full border border-stone-200 rounded px-3 py-2 text-sm font-mono"
            />
            <div className="flex justify-end">
                <button
                    disabled={busy}
                    onClick={submit}
                    className="px-4 py-2 bg-stone-800 text-white rounded text-sm disabled:opacity-50"
                >
                    {busy ? "Creating…" : "Enqueue"}
                </button>
            </div>
        </div>
    );
}


// ─── Expanded job detail ─────────────────────────────────────────────────────

const TERMINAL_STATES: FleetStatus[] = ["pr_created", "failed", "cancelled"];

function JobDetail({ job, onCancel, onDelete }: { job: FleetJob; onCancel: (id: string) => void; onDelete: (id: string) => void }) {
    const decisions = job.decisions || [];
    const log = job.run_log || [];
    const tail = log.slice(-40);

    return (
        <div className="bg-stone-50 border-t border-stone-200 p-4 space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-4">
                <div>
                    <div className="text-xs text-stone-500 mb-1">Branch</div>
                    <div className="font-mono">{job.branch_name || "—"}</div>
                </div>
                <div>
                    <div className="text-xs text-stone-500 mb-1">Claimed by</div>
                    <div className="font-mono">{job.claimed_by || "—"}</div>
                </div>
                <div className="col-span-2">
                    <div className="text-xs text-stone-500 mb-1">Prompt</div>
                    <pre className="bg-white border border-stone-200 rounded p-2 text-xs whitespace-pre-wrap">{job.prompt}</pre>
                </div>
            </div>

            {job.triage?.reason && (
                <div>
                    <div className="text-xs text-stone-500 mb-1">Triage reason ({job.triage.model})</div>
                    <div className="text-stone-700">{job.triage.reason}</div>
                </div>
            )}

            {decisions.length > 0 && (
                <div>
                    <div className="text-xs text-stone-500 mb-1">Decisions ({decisions.length})</div>
                    <table className="w-full text-xs">
                        <thead><tr className="text-stone-500">
                            <th className="text-left font-normal pb-1">When</th>
                            <th className="text-left font-normal pb-1">Decision</th>
                            <th className="text-left font-normal pb-1">Detail</th>
                        </tr></thead>
                        <tbody>
                            {decisions.map((d, i) => (
                                <tr key={i} className="border-t border-stone-200">
                                    <td className="py-1 text-stone-400">{relativeTime(d.timestamp)}</td>
                                    <td className="py-1 font-medium">{d.decision}</td>
                                    <td className="py-1 text-stone-600">{d.detail}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {tail.length > 0 && (
                <div>
                    <div className="text-xs text-stone-500 mb-1">Run log (last {tail.length} of {log.length})</div>
                    <pre className="bg-black text-green-400 rounded p-2 text-xs font-mono max-h-60 overflow-y-auto">
{tail.map(l => l.line).join("\n")}
                    </pre>
                </div>
            )}

            {job.error_log && (
                <div>
                    <div className="text-xs text-red-600 mb-1">Error</div>
                    <pre className="bg-red-50 text-red-800 rounded p-2 text-xs whitespace-pre-wrap">{job.error_log}</pre>
                </div>
            )}

            <div className="flex gap-2 items-center pt-2 border-t border-stone-200">
                {job.pr_url && (
                    <a
                        href={job.pr_url} target="_blank" rel="noopener noreferrer"
                        className="text-blue-600 hover:underline text-sm"
                    >
                        View PR #{job.pr_number} ↗
                    </a>
                )}
                {["queued", "claimed", "running", "pushing"].includes(job.status) && (
                    <button
                        onClick={() => onCancel(job.id)}
                        className="ml-auto px-3 py-1 border border-stone-300 rounded text-xs text-stone-700 hover:bg-stone-100"
                    >
                        Cancel
                    </button>
                )}
                {TERMINAL_STATES.includes(job.status) && (
                    <button
                        onClick={() => onDelete(job.id)}
                        className="ml-auto px-3 py-1 border border-red-200 text-red-700 rounded text-xs hover:bg-red-50"
                    >
                        Delete
                    </button>
                )}
            </div>
        </div>
    );
}


// ─── Page ────────────────────────────────────────────────────────────────────

export default function FleetPage() {
    const [jobs, setJobs] = useState<FleetJob[]>([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState<string | null>(null);
    const [expanded, setExpanded] = useState<string | null>(null);
    const [showNew, setShowNew] = useState(false);
    const [triaging, setTriaging] = useState(false);
    const [health, setHealth] = useState<FleetWorkerHealth | null>(null);
    const [dispatching, setDispatching] = useState(false);

    async function refresh() {
        try {
            const [list, h] = await Promise.all([fleetApi.list(), fleetApi.workerHealth()]);
            setJobs(list);
            setHealth(h);
            setErr(null);
        } catch (e: any) {
            setErr(e.message || "fetch failed");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        refresh();
        const t = setInterval(refresh, 3000);
        return () => clearInterval(t);
    }, []);

    async function dispatch() {
        setDispatching(true);
        try {
            const r = await fleetApi.dispatch();
            if (!r.dispatched) {
                alert("Worker did not acknowledge — is the host daemon running?");
            }
            await refresh();
        } catch (e: any) {
            alert(`Dispatch failed: ${e.message}`);
        } finally {
            setDispatching(false);
        }
    }

    async function runTriage() {
        setTriaging(true);
        try {
            const job = await fleetApi.triage();
            if (!job) {
                alert("Triage ran but enqueued nothing — queue not empty, no candidates, or LLM picked nothing.");
            }
            await refresh();
        } catch (e: any) {
            alert(`Triage failed: ${e.message}`);
        } finally {
            setTriaging(false);
        }
    }

    async function cancel(id: string) {
        if (!confirm("Cancel this job? Any in-flight run on the host worker will finish on its own.")) return;
        await fleetApi.cancel(id);
        await refresh();
    }

    async function remove(id: string) {
        if (!confirm("Delete this job permanently? The PR (if any) is left untouched on GitHub.")) return;
        try {
            await fleetApi.remove(id);
            if (expanded === id) setExpanded(null);
            await refresh();
        } catch (e: any) {
            alert(`Delete failed: ${e.message}`);
        }
    }

    const active = jobs.filter(j => ["queued", "claimed", "running", "pushing"].includes(j.status));
    const recent = jobs.filter(j => !["queued", "claimed", "running", "pushing"].includes(j.status));

    return (
        <div className="max-w-6xl mx-auto p-6 space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-semibold">Fleet</h1>
                    <p className="text-sm text-stone-500 mt-1">
                        Cross-repo automation. Sutra triages issues across your repos and queues jobs;
                        the host-side Gemini CLI worker (launchd, hourly) claims them, makes a PR, and posts decisions as a comment.
                    </p>
                </div>
                <div className="flex gap-2 items-center">
                    {health && (
                        <span
                            className={`text-xs px-2 py-1 rounded-full font-medium ${
                                health.online
                                    ? health.busy
                                        ? "bg-orange-100 text-orange-700"
                                        : "bg-green-100 text-green-700"
                                    : "bg-stone-200 text-stone-600"
                            }`}
                            title={health.online ? `worker_id=${health.worker_id} v${health.version}` : (health.error || "")}
                        >
                            ● Worker {health.online ? (health.busy ? "busy" : "online") : "offline"}
                        </span>
                    )}
                    <button
                        onClick={dispatch}
                        disabled={dispatching || !health?.online || !!health?.busy}
                        className="px-3 py-2 border border-stone-300 rounded text-sm hover:bg-stone-50 disabled:opacity-50"
                        title="POST /api/fleet/dispatch — pokes the host worker to claim the next queued job"
                    >
                        {dispatching ? "Dispatching…" : "Dispatch worker"}
                    </button>
                    <button
                        onClick={runTriage}
                        disabled={triaging}
                        className="px-3 py-2 border border-stone-300 rounded text-sm hover:bg-stone-50 disabled:opacity-50"
                    >
                        {triaging ? "Triaging…" : "Run triage now"}
                    </button>
                    <button
                        onClick={() => setShowNew(s => !s)}
                        className="px-3 py-2 bg-stone-800 text-white rounded text-sm"
                    >
                        {showNew ? "Close" : "+ New job"}
                    </button>
                </div>
            </div>

            {err && (
                <div className="bg-red-50 border border-red-200 text-red-700 rounded px-3 py-2 text-sm">
                    {err}
                </div>
            )}

            {showNew && (
                <NewJobForm
                    onCreated={() => { setShowNew(false); refresh(); }}
                    onCancel={() => setShowNew(false)}
                />
            )}

            <SetupHelp health={health} />
            <RepoConfig />

            {loading && jobs.length === 0 ? (
                <div className="text-stone-500 text-sm">Loading…</div>
            ) : jobs.length === 0 ? (
                <div className="border border-dashed border-stone-300 rounded-lg p-8 text-center text-stone-500 text-sm">
                    No fleet jobs yet. Click <span className="font-semibold">Run triage now</span> to pick an issue from
                    your <code className="bg-stone-100 px-1 rounded">FLEET_REPOS</code>, or <span className="font-semibold">+ New job</span> to enqueue one manually.
                </div>
            ) : (
                <>
                    {active.length > 0 && (
                        <Section title={`Active (${active.length})`} jobs={active} expanded={expanded} setExpanded={setExpanded} onCancel={cancel} onDelete={remove} />
                    )}
                    {recent.length > 0 && (
                        <Section title={`Recent (${recent.length})`} jobs={recent} expanded={expanded} setExpanded={setExpanded} onCancel={cancel} onDelete={remove} />
                    )}
                </>
            )}
        </div>
    );
}


function Section({
    title, jobs, expanded, setExpanded, onCancel, onDelete,
}: {
    title: string;
    jobs: FleetJob[];
    expanded: string | null;
    setExpanded: (id: string | null) => void;
    onCancel: (id: string) => void;
    onDelete: (id: string) => void;
}) {
    return (
        <div>
            <h2 className="text-sm font-semibold text-stone-600 uppercase tracking-wide mb-2">{title}</h2>
            <div className="border border-stone-200 rounded-lg overflow-hidden bg-white">
                {jobs.map(j => (
                    <div key={j.id} className="border-b border-stone-200 last:border-b-0">
                        <button
                            onClick={() => setExpanded(expanded === j.id ? null : j.id)}
                            className="w-full flex items-center gap-3 px-4 py-3 hover:bg-stone-50 text-left text-sm"
                        >
                            <StatusBadge status={j.status} />
                            <div className="font-mono text-xs text-stone-400">{j.id.slice(0, 8)}</div>
                            <div className="flex-1 min-w-0">
                                <div className="font-medium truncate">{j.title}</div>
                                <div className="text-xs text-stone-500 truncate">
                                    {j.repo_url}
                                    {j.issue_ref && <span className="ml-2">{j.issue_ref}</span>}
                                </div>
                            </div>
                            {j.pr_url && (
                                <Link href={j.pr_url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} className="text-blue-600 hover:underline text-xs">
                                    PR #{j.pr_number}
                                </Link>
                            )}
                            <div className="text-xs text-stone-400 w-16 text-right">{relativeTime(j.created_at)}</div>
                            {TERMINAL_STATES.includes(j.status) && (
                                <span
                                    role="button"
                                    tabIndex={0}
                                    onClick={e => { e.stopPropagation(); onDelete(j.id); }}
                                    onKeyDown={e => { if (e.key === "Enter") { e.stopPropagation(); onDelete(j.id); } }}
                                    className="text-stone-400 hover:text-red-600 text-sm px-1 cursor-pointer"
                                    title="Delete"
                                >
                                    ×
                                </span>
                            )}
                        </button>
                        {expanded === j.id && <JobDetail job={j} onCancel={onCancel} onDelete={onDelete} />}
                    </div>
                ))}
            </div>
        </div>
    );
}
