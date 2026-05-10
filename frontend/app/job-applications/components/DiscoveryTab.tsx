"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
    Plus, Play, Trash2, X, Settings as SettingsIcon, RefreshCw,
    ExternalLink, Search, Building2, MapPin, Briefcase, ShieldCheck,
    AlertTriangle, Globe2, Clock, Target,
} from "lucide-react";
import {
    jobDiscoveryApi,
    type JobSearchConfig,
    type JobPosting,
    type CompanyBoard,
    type JobDiscoverySourceMeta,
    type H1bStats,
} from "@/lib/api";

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ALL_SOURCES = ["greenhouse", "lever", "ashby", "smartrecruiters", "discovery"];
const PER_BOARD_SOURCES = new Set(["greenhouse", "lever", "ashby", "smartrecruiters"]);

function timeAgo(iso: string | null): string {
    if (!iso) return "—";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
}

function htmlToText(raw: string): string {
    const decoded = raw
        .replace(/&lt;/g, "<").replace(/&gt;/g, ">")
        .replace(/&amp;/g, "&").replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'").replace(/&nbsp;/g, " ");
    return decoded
        .replace(/<br\s*\/?>/gi, "\n")
        .replace(/<\/p>/gi, "\n").replace(/<\/div>/gi, "\n")
        .replace(/<\/h[1-6]>/gi, "\n").replace(/<h[1-6][^>]*>/gi, "\n")
        .replace(/<li[^>]*>/gi, "\n• ").replace(/<\/li>/gi, "")
        .replace(/<[^>]+>/g, "")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
}

const SOURCE_COLORS: Record<string, string> = {
    greenhouse:      "bg-emerald-50 text-emerald-700 border-emerald-200",
    lever:           "bg-blue-50 text-blue-700 border-blue-200",
    ashby:           "bg-violet-50 text-violet-700 border-violet-200",
    smartrecruiters: "bg-amber-50 text-amber-700 border-amber-200",
    discovery:       "bg-indigo-50 text-indigo-700 border-indigo-200",
};

function sourceBadgeCls(source: string): string {
    return SOURCE_COLORS[source] ?? "bg-stone-100 text-stone-700 border-stone-200";
}

function tierBadge(tier: number | null): { label: string; cls: string } {
    if (tier == null) return { label: "—", cls: "bg-stone-100 text-stone-500 border-stone-200" };
    if (tier === 0) return { label: "no H-1B", cls: "bg-rose-50 text-rose-700 border-rose-200" };
    if (tier === 1) return { label: "H-1B 1+", cls: "bg-amber-50 text-amber-700 border-amber-200" };
    if (tier === 2) return { label: "H-1B 10+", cls: "bg-blue-50 text-blue-700 border-blue-200" };
    return { label: "H-1B 100+", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" };
}

const DEFAULT_NEW_CONFIG: Partial<JobSearchConfig> = {
    name: "PM jobs daily",
    title_query: "Product Manager",
    keywords: [],
    exclude_keywords: ["intern", "contract"],
    location_filter: null,
    lookback_hours: 24,
    schedule_cron: "0 7 * * *",
    timezone: "America/Los_Angeles",
    sources_enabled: ALL_SOURCES,
    max_results_per_run: 200,
    h1b_only: true,
    h1b_min_tier: 1,
    exclude_companies: [],
    is_active: true,
};

// ─── Config editor ────────────────────────────────────────────────────────────

function ConfigEditor({
    initial,
    onSave,
    onCancel,
}: {
    initial: Partial<JobSearchConfig>;
    onSave: (data: Partial<JobSearchConfig>) => Promise<void>;
    onCancel: () => void;
}) {
    const [data, setData] = useState<Partial<JobSearchConfig>>(initial);
    const [saving, setSaving] = useState(false);

    const set = <K extends keyof JobSearchConfig>(k: K, v: JobSearchConfig[K]) =>
        setData((d) => ({ ...d, [k]: v }));

    const toggleSource = (s: string) => {
        const cur = new Set(data.sources_enabled || []);
        if (cur.has(s)) cur.delete(s);
        else cur.add(s);
        set("sources_enabled", Array.from(cur));
    };

    const submit = async () => {
        if (!data.name || !data.title_query) {
            alert("Name and title query are required");
            return;
        }
        setSaving(true);
        try {
            await onSave(data);
        } finally {
            setSaving(false);
        }
    };

    const csvField = (
        label: string,
        key: keyof JobSearchConfig,
        placeholder: string,
    ) => (
        <div>
            <label className="block text-[11px] uppercase tracking-wider text-stone-500 mb-1">
                {label}
            </label>
            <input
                value={((data[key] as string[] | undefined) || []).join(", ")}
                onChange={(e) =>
                    set(
                        key,
                        e.target.value
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean) as never,
                    )
                }
                placeholder={placeholder}
                className="w-full bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
            />
        </div>
    );

    return (
        <div className="bg-white border border-stone-200 rounded-xl p-4 space-y-3 shadow-sm">
            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="block text-[11px] uppercase tracking-wider text-stone-500 mb-1">
                        Name
                    </label>
                    <input
                        value={data.name || ""}
                        onChange={(e) => set("name", e.target.value)}
                        className="w-full bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                    />
                </div>
                <div>
                    <label className="block text-[11px] uppercase tracking-wider text-stone-500 mb-1">
                        Title query
                    </label>
                    <input
                        value={data.title_query || ""}
                        onChange={(e) => set("title_query", e.target.value)}
                        placeholder="Product Manager"
                        className="w-full bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                    />
                </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
                {csvField("Bonus keywords (OR)", "keywords", "PM, Product Lead")}
                {csvField("Exclude keywords", "exclude_keywords", "intern, contract")}
            </div>

            <div className="grid grid-cols-3 gap-3">
                <div>
                    <label className="block text-[11px] uppercase tracking-wider text-stone-500 mb-1">
                        Lookback hours
                    </label>
                    <input
                        type="number"
                        min={1}
                        value={data.lookback_hours ?? 24}
                        onChange={(e) => set("lookback_hours", Number(e.target.value) || 24)}
                        className="w-full bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                    />
                </div>
                <div>
                    <label className="block text-[11px] uppercase tracking-wider text-stone-500 mb-1">
                        Schedule (cron)
                    </label>
                    <input
                        value={data.schedule_cron || "0 7 * * *"}
                        onChange={(e) => set("schedule_cron", e.target.value)}
                        className="w-full bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm font-mono text-stone-900 focus:border-indigo-500 focus:outline-none"
                    />
                </div>
                <div>
                    <label className="block text-[11px] uppercase tracking-wider text-stone-500 mb-1">
                        Timezone
                    </label>
                    <input
                        value={data.timezone || "America/Los_Angeles"}
                        onChange={(e) => set("timezone", e.target.value)}
                        className="w-full bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                    />
                </div>
            </div>

            <div>
                <label className="block text-[11px] uppercase tracking-wider text-stone-500 mb-1">
                    Location filter (substring)
                </label>
                <input
                    value={data.location_filter || ""}
                    onChange={(e) => set("location_filter", e.target.value || null)}
                    placeholder="e.g. United States, Remote, NYC"
                    className="w-full bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                />
            </div>

            <div>
                <label className="block text-[11px] uppercase tracking-wider text-stone-500 mb-1">
                    Sources enabled
                </label>
                <div className="flex flex-wrap gap-2">
                    {ALL_SOURCES.map((s) => {
                        const on = (data.sources_enabled || []).includes(s);
                        return (
                            <button
                                key={s}
                                onClick={() => toggleSource(s)}
                                className={`px-2.5 py-1 rounded-md text-xs border transition-colors ${
                                    on
                                        ? "bg-indigo-50 text-indigo-700 border-indigo-300"
                                        : "bg-white text-stone-500 border-stone-200 hover:border-stone-400"
                                }`}
                            >
                                {s}
                            </button>
                        );
                    })}
                </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
                <label className="inline-flex items-center gap-2 text-sm text-stone-700">
                    <input
                        type="checkbox"
                        checked={data.h1b_only ?? true}
                        onChange={(e) => set("h1b_only", e.target.checked)}
                        className="accent-indigo-500"
                    />
                    H-1B sponsors only
                </label>
                <div>
                    <label className="block text-[11px] uppercase tracking-wider text-stone-500 mb-1">
                        Min H-1B tier
                    </label>
                    <select
                        value={data.h1b_min_tier ?? 1}
                        onChange={(e) => set("h1b_min_tier", Number(e.target.value))}
                        className="w-full bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                    >
                        <option value={0}>0 — show all</option>
                        <option value={1}>1+ — any sponsor</option>
                        <option value={2}>10+ — regular sponsor</option>
                        <option value={3}>100+ — high volume</option>
                    </select>
                </div>
                <div>
                    <label className="block text-[11px] uppercase tracking-wider text-stone-500 mb-1">
                        Max per run
                    </label>
                    <input
                        type="number"
                        value={data.max_results_per_run ?? 200}
                        onChange={(e) => set("max_results_per_run", Number(e.target.value) || 200)}
                        className="w-full bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                    />
                </div>
            </div>

            {csvField("Exclude companies", "exclude_companies", "Cognizant, Infosys")}

            <div className="flex items-center gap-2 pt-2 border-t border-stone-200">
                <label className="inline-flex items-center gap-2 text-sm text-stone-700 mr-auto">
                    <input
                        type="checkbox"
                        checked={data.is_active ?? true}
                        onChange={(e) => set("is_active", e.target.checked)}
                        className="accent-indigo-500"
                    />
                    Active
                </label>
                <button
                    onClick={onCancel}
                    className="px-3 py-1.5 text-sm text-stone-500 hover:text-stone-700"
                >
                    Cancel
                </button>
                <button
                    onClick={submit}
                    disabled={saving}
                    className="px-3 py-1.5 text-sm bg-indigo-600 text-white border border-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                >
                    {saving ? "Saving…" : "Save"}
                </button>
            </div>
        </div>
    );
}

// ─── Boards manager ───────────────────────────────────────────────────────────

function BoardsManager({
    boards,
    onChange,
}: {
    boards: CompanyBoard[];
    onChange: () => Promise<void>;
}) {
    const [adding, setAdding] = useState(false);
    const [draft, setDraft] = useState({
        company_name: "",
        source: "greenhouse" as JobDiscoverySourceMeta["name"],
        board_token: "",
        is_active: true,
    });

    const create = async () => {
        if (!draft.company_name || !draft.board_token) {
            alert("Company name and board token required");
            return;
        }
        try {
            await jobDiscoveryApi.createBoard(draft as never);
            setDraft({ company_name: "", source: "greenhouse", board_token: "", is_active: true });
            setAdding(false);
            await onChange();
        } catch (e) {
            alert(`Failed to add board: ${(e as Error).message || e}`);
        }
    };

    const remove = async (id: string) => {
        if (!confirm("Remove this board?")) return;
        await jobDiscoveryApi.deleteBoard(id);
        await onChange();
    };

    const toggle = async (b: CompanyBoard) => {
        await jobDiscoveryApi.updateBoard(b.id, { ...b, is_active: !b.is_active });
        await onChange();
    };

    return (
        <div className="bg-white border border-stone-200 rounded-xl p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
                <div className="text-xs uppercase tracking-wider text-stone-500 flex items-center gap-1.5">
                    <Globe2 size={12} /> Company boards ({boards.length})
                </div>
                {!adding && (
                    <button
                        onClick={() => setAdding(true)}
                        className="text-xs text-indigo-600 hover:text-indigo-700 inline-flex items-center gap-1"
                    >
                        <Plus size={12} /> Add board
                    </button>
                )}
            </div>

            {adding && (
                <div className="grid grid-cols-12 gap-2 mb-3">
                    <input
                        value={draft.company_name}
                        onChange={(e) => setDraft({ ...draft, company_name: e.target.value })}
                        placeholder="Company name"
                        className="col-span-4 bg-white border border-stone-200 rounded-md px-2 py-1.5 text-xs text-stone-900"
                    />
                    <select
                        value={draft.source}
                        onChange={(e) => setDraft({ ...draft, source: e.target.value })}
                        className="col-span-3 bg-white border border-stone-200 rounded-md px-2 py-1.5 text-xs text-stone-900"
                    >
                        {Array.from(PER_BOARD_SOURCES).map((s) => (
                            <option key={s} value={s}>
                                {s}
                            </option>
                        ))}
                    </select>
                    <input
                        value={draft.board_token}
                        onChange={(e) => setDraft({ ...draft, board_token: e.target.value })}
                        placeholder="Board token / slug"
                        className="col-span-3 bg-white border border-stone-200 rounded-md px-2 py-1.5 text-xs text-stone-900"
                    />
                    <button
                        onClick={create}
                        className="col-span-1 bg-indigo-600 text-white border border-indigo-600 rounded-md px-2 text-xs hover:bg-indigo-700"
                    >
                        Add
                    </button>
                    <button
                        onClick={() => setAdding(false)}
                        className="col-span-1 text-stone-500 text-xs"
                    >
                        Cancel
                    </button>
                </div>
            )}

            <div className="space-y-1 max-h-64 overflow-y-auto">
                {boards.map((b) => (
                    <div
                        key={b.id}
                        className="flex items-center gap-2 text-xs py-1.5 px-2 rounded-md hover:bg-stone-50"
                    >
                        <span className="w-40 truncate text-stone-800">{b.company_name}</span>
                        <span className="w-28 text-stone-500">{b.source}</span>
                        <span className="flex-1 truncate font-mono text-stone-400">{b.board_token}</span>
                        {b.consecutive_failures > 0 && (
                            <span className="text-rose-500 inline-flex items-center gap-1">
                                <AlertTriangle size={10} />
                                {b.consecutive_failures}
                            </span>
                        )}
                        <button
                            onClick={() => toggle(b)}
                            className={`px-1.5 py-0.5 rounded text-[10px] border ${
                                b.is_active
                                    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                    : "bg-stone-100 text-stone-500 border-stone-200"
                            }`}
                        >
                            {b.is_active ? "active" : "off"}
                        </button>
                        <button
                            onClick={() => remove(b.id)}
                            className="text-rose-500 hover:text-rose-600"
                            title="Remove"
                        >
                            <Trash2 size={12} />
                        </button>
                    </div>
                ))}
                {boards.length === 0 && (
                    <div className="text-stone-400 text-xs py-3 text-center border border-dashed border-stone-200 rounded">
                        No boards added — Greenhouse/Lever/Ashby/SmartRecruiters adapters need at least one each.
                    </div>
                )}
            </div>
        </div>
    );
}

// ─── H-1B panel ───────────────────────────────────────────────────────────────

function H1bPanel() {
    const [stats, setStats] = useState<H1bStats | null>(null);
    const [busy, setBusy] = useState(false);
    const [lastResult, setLastResult] = useState<string | null>(null);
    const [lastError, setLastError] = useState<string | null>(null);
    const [uploadFy, setUploadFy] = useState<number>(2024);
    const [urlInput, setUrlInput] = useState<string>("");
    const [urlFy, setUrlFy] = useState<number>(2024);

    const load = useCallback(async () => {
        try {
            setStats(await jobDiscoveryApi.h1bStats());
        } catch {
            /* ignore */
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const formatResult = (r: {
        status: string;
        fiscal_year?: number;
        rows_seen?: number;
        employers?: number;
        written?: number;
        error?: string;
        headers?: string[];
    }): { ok: boolean; msg: string } => {
        if (r.status === "ok") {
            return {
                ok: true,
                msg: `FY${r.fiscal_year}: ${r.employers?.toLocaleString() ?? 0} employers loaded (${r.rows_seen?.toLocaleString() ?? 0} rows scanned).`,
            };
        }
        if (r.status === "error") {
            return {
                ok: false,
                msg: `${r.error || "load failed"}${r.headers ? ` — saw columns: ${r.headers.slice(0, 6).join(", ")}…` : ""}`,
            };
        }
        return { ok: false, msg: r.status };
    };

    const refreshDefaults = async () => {
        if (!confirm("Re-download USCIS data using the default URLs? If those 404, use the URL or upload field below.")) return;
        setBusy(true);
        setLastResult(null);
        setLastError(null);
        try {
            await jobDiscoveryApi.h1bRefresh();
            setLastResult("Queued in background — refresh stats in ~1-2 min.");
            await load();
        } catch (e) {
            setLastError(`Refresh failed: ${(e as Error).message}`);
        } finally {
            setBusy(false);
        }
    };

    const refreshOneUrl = async () => {
        if (!urlInput) {
            setLastError("Paste a CSV URL first.");
            return;
        }
        setBusy(true);
        setLastResult(null);
        setLastError(null);
        try {
            const r = await jobDiscoveryApi.h1bRefresh({ url: urlInput, fiscal_year: urlFy });
            const f = formatResult(r);
            if (f.ok) {
                setLastResult(f.msg);
                await load();
            } else {
                setLastError(f.msg);
            }
        } catch (e) {
            setLastError(`Load failed: ${(e as Error).message}`);
        } finally {
            setBusy(false);
        }
    };

    const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setBusy(true);
        setLastResult(null);
        setLastError(null);
        try {
            const r = await jobDiscoveryApi.h1bUpload(file, uploadFy);
            const f = formatResult(r);
            if (f.ok) {
                setLastResult(f.msg);
                await load();
            } else {
                setLastError(f.msg);
            }
        } catch (err) {
            setLastError(`Upload failed: ${(err as Error).message}`);
        } finally {
            setBusy(false);
            e.target.value = "";
        }
    };

    return (
        <div className="bg-white border border-stone-200 rounded-xl p-4 space-y-3 shadow-sm">
            <div className="flex items-center justify-between">
                <div className="text-xs uppercase tracking-wider text-stone-500 flex items-center gap-1.5">
                    <ShieldCheck size={12} /> H-1B sponsor data
                </div>
                <button
                    onClick={refreshDefaults}
                    disabled={busy}
                    className="text-xs text-indigo-600 hover:text-indigo-700 inline-flex items-center gap-1 disabled:opacity-50"
                >
                    <RefreshCw size={12} className={busy ? "animate-spin" : ""} />
                    Try default URLs
                </button>
            </div>

            {stats ? (
                <div className="text-xs text-stone-700 space-y-1">
                    <div>
                        <span className="text-stone-500">Total rows:</span>{" "}
                        <span className="font-mono">{stats.total_rows.toLocaleString()}</span>
                    </div>
                    <div className="flex flex-wrap gap-2 mt-1">
                        {stats.by_fiscal_year.map((row) => (
                            <span
                                key={row.fiscal_year}
                                className="px-2 py-0.5 rounded border border-stone-200 bg-stone-50 text-stone-700"
                            >
                                FY{row.fiscal_year}: {row.count.toLocaleString()}
                            </span>
                        ))}
                    </div>
                    {stats.total_rows === 0 && (
                        <div className="text-amber-600 text-[11px] mt-1 inline-flex items-center gap-1">
                            <AlertTriangle size={10} />
                            No data loaded yet — use one of the options below.
                        </div>
                    )}
                </div>
            ) : (
                <div className="text-stone-400 text-xs">Loading…</div>
            )}

            <div className="border-t border-stone-200 pt-3 space-y-3">
                {/* URL fallback */}
                <div>
                    <div className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">
                        Load from URL
                    </div>
                    <div className="flex items-center gap-1.5">
                        <input
                            type="text"
                            value={urlInput}
                            onChange={(e) => setUrlInput(e.target.value)}
                            placeholder="https://www.uscis.gov/.../H-1B_…_FY2024.csv"
                            className="flex-1 bg-white border border-stone-200 rounded-md px-2 py-1.5 text-xs font-mono text-stone-900"
                        />
                        <input
                            type="number"
                            value={urlFy}
                            onChange={(e) => setUrlFy(Number(e.target.value) || 2024)}
                            placeholder="FY"
                            className="w-20 bg-white border border-stone-200 rounded-md px-2 py-1.5 text-xs text-stone-900"
                        />
                        <button
                            onClick={refreshOneUrl}
                            disabled={busy}
                            className="bg-indigo-600 text-white border border-indigo-600 rounded-md px-2 py-1.5 text-xs hover:bg-indigo-700 disabled:opacity-50"
                        >
                            Load
                        </button>
                    </div>
                </div>

                {/* Upload fallback */}
                <div>
                    <div className="text-[10px] uppercase tracking-wider text-stone-500 mb-1">
                        Upload CSV (most reliable)
                    </div>
                    <div className="flex items-center gap-1.5">
                        <input
                            type="number"
                            value={uploadFy}
                            onChange={(e) => setUploadFy(Number(e.target.value) || 2024)}
                            placeholder="FY"
                            className="w-20 bg-white border border-stone-200 rounded-md px-2 py-1.5 text-xs text-stone-900"
                        />
                        <input
                            type="file"
                            accept=".csv,.zip"
                            onChange={onUpload}
                            disabled={busy}
                            className="flex-1 text-xs text-stone-500 file:mr-2 file:py-1 file:px-2 file:rounded file:border file:border-stone-200 file:bg-stone-100 file:text-stone-700 file:text-xs hover:file:bg-stone-200"
                        />
                    </div>
                    <div className="text-[10px] text-stone-500 mt-1">
                        Get the .csv from{" "}
                        <a
                            className="underline text-indigo-600"
                            target="_blank"
                            rel="noreferrer"
                            href="https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub"
                        >
                            uscis.gov/h-1b-employer-data-hub
                        </a>
                        , then upload here.
                    </div>
                </div>

                {lastResult && (
                    <div className="text-[11px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-1.5">
                        {lastResult}
                    </div>
                )}
                {lastError && (
                    <div className="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded px-2 py-1.5 flex items-start gap-1">
                        <AlertTriangle size={11} className="mt-0.5 shrink-0" />
                        <span className="break-all">{lastError}</span>
                    </div>
                )}
            </div>
        </div>
    );
}

// ─── Posting drawer ───────────────────────────────────────────────────────────

function PostingDrawer({
    posting,
    onClose,
    onPatch,
    onApplied,
}: {
    posting: JobPosting;
    onClose: () => void;
    onPatch: (id: string, patch: Partial<JobPosting>) => Promise<void>;
    onApplied: (applicationId: string) => void;
}) {
    const [applying, setApplying] = useState(false);

    const apply = async () => {
        if (!confirm(`Apply to "${posting.job_title}" at ${posting.company}? This creates a JobApplication and fires the resume builder.`)) {
            return;
        }
        setApplying(true);
        try {
            const r = await jobDiscoveryApi.applyPosting(posting.id);
            if (r.application_id) onApplied(r.application_id);
            onClose();
        } catch (e) {
            alert(`Apply failed: ${(e as Error).message}`);
        } finally {
            setApplying(false);
        }
    };

    const dismiss = async () => {
        await onPatch(posting.id, { status: "dismissed" });
        onClose();
    };

    const tier = tierBadge(posting.sponsor_tier);

    return (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
            <div
                className="w-full max-w-2xl bg-white border-l border-stone-200 h-full flex flex-col shadow-xl"
                onClick={(e) => e.stopPropagation()}
            >
                {/* ── Sticky header ── */}
                <div className="shrink-0 border-b border-stone-200 px-5 py-4 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <h2 className="text-base font-semibold text-stone-900 leading-snug">{posting.job_title}</h2>
                        <p className="text-sm text-stone-500 mt-0.5 truncate">
                            {posting.company}
                            {posting.location ? ` · ${posting.location}` : ""}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="shrink-0 p-1.5 rounded-lg hover:bg-stone-100 text-stone-400 mt-0.5"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                {/* ── Scrollable body ── */}
                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

                    {/* Badges + apply link */}
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium border ${sourceBadgeCls(posting.source)}`}>
                            {posting.source}
                        </span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium border ${tier.cls}`}>
                            {tier.label}
                        </span>
                        {posting.no_sponsorship_signal && (
                            <span className="px-2 py-0.5 rounded text-xs border bg-amber-50 text-amber-700 border-amber-200 inline-flex items-center gap-1">
                                <AlertTriangle size={10} /> No sponsorship signal
                            </span>
                        )}
                        <a
                            href={posting.job_url}
                            target="_blank"
                            rel="noreferrer"
                            className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700"
                        >
                            <ExternalLink size={12} /> Apply page
                        </a>
                    </div>

                    {/* Compact meta row */}
                    <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-xs text-stone-500">
                        <span>Posted <span className="text-stone-700 font-medium">{timeAgo(posting.posted_at)}</span></span>
                        <span className="text-stone-300">·</span>
                        <span>First seen <span className="text-stone-700 font-medium">{timeAgo(posting.first_seen_at)}</span></span>
                        {posting.salary && (
                            <>
                                <span className="text-stone-300">·</span>
                                <span className="text-stone-700 font-medium">{posting.salary}</span>
                            </>
                        )}
                        {posting.sponsor_match_method && posting.sponsor_match_method !== "none" && (
                            <>
                                <span className="text-stone-300">·</span>
                                <span>match: <span className="font-mono">{posting.sponsor_match_method}</span></span>
                            </>
                        )}
                    </div>

                    {/* Matched terms */}
                    {posting.matched_terms.length > 0 && (
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-stone-400 mb-1.5">Matched terms</div>
                            <div className="flex flex-wrap gap-1">
                                {posting.matched_terms.map((t) => (
                                    <span
                                        key={t}
                                        className="px-2 py-0.5 rounded text-xs border bg-indigo-50 text-indigo-700 border-indigo-200"
                                    >
                                        {t}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Description — fills remaining scroll space */}
                    <div>
                        <div className="text-[10px] uppercase tracking-wider text-stone-400 mb-2">Description</div>
                        <div className="text-sm text-stone-700 leading-relaxed whitespace-pre-wrap">
                            {posting.description_snippet ? htmlToText(posting.description_snippet) : "—"}
                        </div>
                    </div>
                </div>

                {/* ── Sticky footer ── */}
                <div className="shrink-0 border-t border-stone-200 px-5 py-3 flex items-center gap-3 bg-white">
                    <button
                        onClick={dismiss}
                        className="px-4 py-2 text-sm text-stone-600 hover:text-rose-600 border border-stone-200 hover:border-rose-200 rounded-lg transition-colors"
                    >
                        Dismiss
                    </button>
                    <button
                        onClick={apply}
                        disabled={applying || posting.status === "applied"}
                        className="ml-auto px-5 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                    >
                        {posting.status === "applied"
                            ? "Already applied"
                            : applying
                            ? "Applying…"
                            : "Apply (build resume)"}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Top-level Discovery tab ──────────────────────────────────────────────────

export default function DiscoveryTab({
    onAppliedJump,
}: {
    onAppliedJump: (applicationId: string) => void;
}) {
    const [configs, setConfigs] = useState<JobSearchConfig[]>([]);
    const [postings, setPostings] = useState<JobPosting[]>([]);
    const [boards, setBoards] = useState<CompanyBoard[]>([]);
    const [activeConfigId, setActiveConfigId] = useState<string | "">("");
    const [editing, setEditing] = useState<Partial<JobSearchConfig> | null>(null);
    const [showSettings, setShowSettings] = useState(false);
    const [selected, setSelected] = useState<JobPosting | null>(null);
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState<string>("");
    const [sourceFilter, setSourceFilter] = useState<string>("");
    const [sinceHours, setSinceHours] = useState<number>(48);
    const [loading, setLoading] = useState(false);
    const [running, setRunning] = useState(false);

    const reloadConfigs = useCallback(async () => {
        const list = await jobDiscoveryApi.listConfigs();
        setConfigs(list);
        if (!activeConfigId && list.length > 0) setActiveConfigId(list[0].id);
    }, [activeConfigId]);

    const reloadBoards = useCallback(async () => {
        setBoards(await jobDiscoveryApi.listBoards());
    }, []);

    const reloadPostings = useCallback(async () => {
        setLoading(true);
        try {
            const list = await jobDiscoveryApi.listPostings({
                config_id: activeConfigId || undefined,
                status: (statusFilter as never) || undefined,
                source: sourceFilter || undefined,
                since_hours: sinceHours || undefined,
                search: search || undefined,
                limit: 200,
            });
            setPostings(list);
        } finally {
            setLoading(false);
        }
    }, [activeConfigId, statusFilter, sourceFilter, sinceHours, search]);

    useEffect(() => {
        reloadConfigs();
        reloadBoards();
    }, [reloadConfigs, reloadBoards]);

    useEffect(() => {
        reloadPostings();
    }, [reloadPostings]);

    const activeConfig = useMemo(
        () => configs.find((c) => c.id === activeConfigId) || null,
        [configs, activeConfigId],
    );

    const runNow = async () => {
        if (!activeConfig) return;
        setRunning(true);
        try {
            const r = await jobDiscoveryApi.runConfig(activeConfig.id, true);
            await reloadPostings();
            await reloadConfigs();
            const newCount = "new" in r && typeof r.new === "number" ? r.new : 0;
            const seenCount = "seen" in r && typeof r.seen === "number" ? r.seen : 0;
            alert(`Run complete — ${newCount} new, ${seenCount} already seen.`);
        } catch (e) {
            alert(`Run failed: ${(e as Error).message}`);
        } finally {
            setRunning(false);
        }
    };

    const saveConfig = async (data: Partial<JobSearchConfig>) => {
        if (editing && "id" in (editing as JobSearchConfig) && (editing as JobSearchConfig).id) {
            await jobDiscoveryApi.updateConfig((editing as JobSearchConfig).id, data);
        } else {
            const created = await jobDiscoveryApi.createConfig(data);
            setActiveConfigId(created.id);
        }
        setEditing(null);
        await reloadConfigs();
    };

    const deleteConfig = async (id: string) => {
        if (!confirm("Delete this search config? Postings already discovered will remain.")) return;
        await jobDiscoveryApi.deleteConfig(id);
        if (activeConfigId === id) setActiveConfigId("");
        await reloadConfigs();
    };

    const patchPosting = async (id: string, patch: Partial<JobPosting>) => {
        const updated = await jobDiscoveryApi.updatePosting(id, { status: patch.status });
        setPostings((prev) => prev.map((p) => (p.id === id ? updated : p)));
        if (selected?.id === id) setSelected(updated);
    };

    return (
        <div className="space-y-4">
            {/* Config selector + actions */}
            <div className="flex items-center gap-2 flex-wrap">
                <select
                    value={activeConfigId}
                    onChange={(e) => setActiveConfigId(e.target.value)}
                    className="bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                >
                    <option value="">All configs</option>
                    {configs.map((c) => (
                        <option key={c.id} value={c.id}>
                            {c.name} {c.is_active ? "" : " (paused)"}
                        </option>
                    ))}
                </select>

                {activeConfig && (
                    <>
                        <button
                            onClick={runNow}
                            disabled={running}
                            className="inline-flex items-center gap-1.5 px-3 py-2 bg-indigo-600 text-white border border-indigo-600 rounded-lg text-sm hover:bg-indigo-700 disabled:opacity-50"
                        >
                            <Play size={14} className={running ? "animate-pulse" : ""} />
                            {running ? "Running…" : "Run now"}
                        </button>
                        <button
                            onClick={() => setEditing(activeConfig)}
                            className="inline-flex items-center gap-1.5 px-3 py-2 bg-white border border-stone-200 hover:border-stone-300 rounded-lg text-sm text-stone-700"
                        >
                            <SettingsIcon size={14} /> Edit
                        </button>
                        <button
                            onClick={() => deleteConfig(activeConfig.id)}
                            className="inline-flex items-center gap-1.5 px-2 py-2 bg-white border border-stone-200 hover:border-rose-300 rounded-lg text-sm text-rose-500"
                        >
                            <Trash2 size={14} />
                        </button>
                    </>
                )}

                <button
                    onClick={() => setEditing({ ...DEFAULT_NEW_CONFIG })}
                    className="inline-flex items-center gap-1.5 px-3 py-2 bg-white border border-stone-200 hover:border-stone-300 rounded-lg text-sm text-stone-700"
                >
                    <Plus size={14} /> New config
                </button>

                <button
                    onClick={() => setShowSettings((s) => !s)}
                    className="ml-auto inline-flex items-center gap-1.5 px-3 py-2 bg-white border border-stone-200 hover:border-stone-300 rounded-lg text-sm text-stone-700"
                >
                    <SettingsIcon size={14} /> {showSettings ? "Hide" : "Boards & H-1B"}
                </button>
            </div>

            {/* Run summary chip */}
            {activeConfig && (
                <div className="flex items-center gap-2 flex-wrap text-xs text-stone-500">
                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-stone-200 bg-stone-50 text-stone-700">
                        <Clock size={11} /> Schedule: <span className="font-mono">{activeConfig.schedule_cron}</span>
                    </span>
                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-stone-200 bg-stone-50 text-stone-700">
                        <Target size={11} /> Title: <span className="text-stone-900">{activeConfig.title_query}</span>
                    </span>
                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-stone-200 bg-stone-50 text-stone-700">
                        Last run: {activeConfig.last_run_at ? timeAgo(activeConfig.last_run_at) : "never"} —{" "}
                        <span className="text-emerald-600">{activeConfig.last_run_count_new} new</span> /{" "}
                        <span className="text-stone-400">{activeConfig.last_run_count_seen} seen</span>
                    </span>
                    {activeConfig.last_run_error && (
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-rose-200 bg-rose-50 text-rose-700">
                            <AlertTriangle size={11} /> {activeConfig.last_run_error}
                        </span>
                    )}
                </div>
            )}

            {editing && (
                <ConfigEditor
                    initial={editing}
                    onSave={saveConfig}
                    onCancel={() => setEditing(null)}
                />
            )}

            {showSettings && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    <BoardsManager boards={boards} onChange={reloadBoards} />
                    <H1bPanel />
                </div>
            )}

            {/* Filters */}
            <div className="flex items-center gap-2 flex-wrap">
                <div className="relative flex-1 min-w-[220px] max-w-md">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
                    <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search title, company, snippet…"
                        className="w-full bg-white border border-stone-200 rounded-lg pl-9 pr-3 py-2 text-sm placeholder-stone-400 text-stone-900 focus:border-indigo-500 focus:outline-none"
                    />
                </div>
                <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                >
                    <option value="">Any status</option>
                    <option value="new">New</option>
                    <option value="seen">Seen</option>
                    <option value="dismissed">Dismissed</option>
                    <option value="applied">Applied</option>
                </select>
                <select
                    value={sourceFilter}
                    onChange={(e) => setSourceFilter(e.target.value)}
                    className="bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                >
                    <option value="">Any source</option>
                    {ALL_SOURCES.map((s) => (
                        <option key={s} value={s}>
                            {s}
                        </option>
                    ))}
                </select>
                <select
                    value={sinceHours}
                    onChange={(e) => setSinceHours(Number(e.target.value))}
                    className="bg-white border border-stone-200 rounded-lg px-3 py-2 text-sm text-stone-900 focus:border-indigo-500 focus:outline-none"
                >
                    <option value={24}>Last 24h</option>
                    <option value={48}>Last 48h</option>
                    <option value={24 * 7}>Last 7 days</option>
                    <option value={0}>All time</option>
                </select>
                <button
                    onClick={reloadPostings}
                    className="inline-flex items-center gap-1.5 px-3 py-2 bg-white border border-stone-200 hover:border-stone-300 rounded-lg text-sm text-stone-700"
                >
                    <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
                </button>
            </div>

            {/* Postings table */}
            <div className="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
                <table className="w-full text-sm">
                    <thead className="bg-stone-50 border-b border-stone-200">
                        <tr className="text-left text-[11px] uppercase tracking-wider text-stone-500">
                            <th className="px-4 py-2.5 font-medium">Title</th>
                            <th className="px-4 py-2.5 font-medium">Company</th>
                            <th className="px-4 py-2.5 font-medium">Location</th>
                            <th className="px-4 py-2.5 font-medium">Source</th>
                            <th className="px-4 py-2.5 font-medium">H-1B</th>
                            <th className="px-4 py-2.5 font-medium">Posted</th>
                            <th className="px-4 py-2.5 font-medium">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {(statusFilter ? postings : postings.filter(p => p.status !== "dismissed")).map((p) => {
                            const tier = tierBadge(p.sponsor_tier);
                            return (
                                <tr
                                    key={p.id}
                                    onClick={() => setSelected(p)}
                                    className="border-b border-stone-100 hover:bg-stone-50 cursor-pointer"
                                >
                                    <td className="px-4 py-3 font-medium text-stone-900 max-w-[320px] truncate">
                                        {p.job_title}
                                        {p.no_sponsorship_signal && (
                                            <AlertTriangle
                                                size={12}
                                                className="inline ml-1.5 text-amber-500"
                                            />
                                        )}
                                    </td>
                                    <td className="px-4 py-3 text-stone-700 max-w-[220px] truncate">
                                        <span className="inline-flex items-center gap-1.5">
                                            <Building2 size={11} className="text-stone-400" />
                                            {p.company}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-stone-500 max-w-[200px] truncate">
                                        <span className="inline-flex items-center gap-1.5">
                                            <MapPin size={11} className="text-stone-400" />
                                            {p.location || "—"}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={`px-2 py-0.5 rounded text-[10px] border ${sourceBadgeCls(p.source)}`}>
                                            {p.source}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={`px-2 py-0.5 rounded text-[10px] border ${tier.cls}`}>
                                            {tier.label}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-stone-400 text-xs">
                                        {timeAgo(p.posted_at || p.first_seen_at)}
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className="px-2 py-0.5 rounded text-[10px] border bg-stone-100 border-stone-200 text-stone-700">
                                            {p.status}
                                        </span>
                                    </td>
                                </tr>
                            );
                        })}
                        {postings.length === 0 && (
                            <tr>
                                <td colSpan={7} className="px-4 py-12 text-center text-stone-400 text-sm">
                                    {loading
                                        ? "Loading…"
                                        : configs.length === 0
                                        ? "No search configs yet — click \"New config\" to start."
                                        : "No postings match these filters. Click \"Run now\" to fetch the latest."}
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {selected && (
                <PostingDrawer
                    posting={selected}
                    onClose={() => setSelected(null)}
                    onPatch={patchPosting}
                    onApplied={onAppliedJump}
                />
            )}
        </div>
    );
}
