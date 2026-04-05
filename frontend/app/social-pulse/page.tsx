"use client";

import { useState, useEffect, useCallback } from "react";
import {
    TrendingUp, RefreshCw, Globe, Flame, Zap, Hash, Plus, Trash2,
    ExternalLink, ChevronDown, ChevronUp, Lightbulb, X, Check,
    Bookmark, BookmarkCheck, Radio, ArrowRight, Layers, Copy,
    Sparkles, Eye, Clock, Activity, Target, BarChart3, Settings2
} from "lucide-react";
import {
    socialPulseApi,
    type SocialPulseDashboard,
    type SocialPulseItem,
    type PulseNiche,
    type TrendKeyword,
    type SocialPulseTheme,
} from "@/lib/api";

// ── Platform config ────────────────────────────────────────────────────────────

const PLATFORM_CONFIG: Record<string, { label: string; icon: string; gradient: string; glow: string; text: string; bg: string }> = {
    google_trends: { label: "Google Trends", icon: "📈", gradient: "from-blue-500/20 to-blue-600/5", glow: "shadow-blue-500/20", text: "text-blue-400", bg: "bg-blue-500/10" },
    youtube: { label: "YouTube", icon: "▶️", gradient: "from-red-500/20 to-red-600/5", glow: "shadow-red-500/20", text: "text-red-400", bg: "bg-red-500/10" },
    reddit: { label: "Reddit", icon: "🔥", gradient: "from-orange-500/20 to-orange-600/5", glow: "shadow-orange-500/20", text: "text-orange-400", bg: "bg-orange-500/10" },
    hackernews: { label: "Hacker News", icon: "⚡", gradient: "from-amber-500/20 to-amber-600/5", glow: "shadow-amber-500/20", text: "text-amber-400", bg: "bg-amber-500/10" },
};

const SENTIMENT_COLORS: Record<string, string> = {
    positive: "bg-emerald-400",
    negative: "bg-red-400",
    neutral: "bg-stone-400",
    mixed: "bg-purple-400",
};

const REGIONS = ["US", "UK", "IN", "AU", "CA", "DE", "FR", "JP", "BR", "global"];
const TABS = ["All", "Tracked Keywords", "Google Trends", "YouTube", "Reddit", "Hacker News"];
const TAB_PLATFORM: Record<string, string> = {
    "Google Trends": "google_trends",
    "YouTube": "youtube",
    "Reddit": "reddit",
    "Hacker News": "hackernews",
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function timeAgo(isoString: string | null): string {
    if (!isoString) return "—";
    const diff = Date.now() - new Date(isoString).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
}

function getViralityColor(score: number): string {
    if (score >= 80) return "text-red-400";
    if (score >= 60) return "text-orange-400";
    if (score >= 40) return "text-amber-400";
    return "text-blue-400";
}

function getViralityRingColor(score: number): string {
    if (score >= 80) return "stroke-red-400";
    if (score >= 60) return "stroke-orange-400";
    if (score >= 40) return "stroke-amber-400";
    return "stroke-blue-400";
}

function getViralityBg(score: number): string {
    if (score >= 80) return "bg-red-500/10 border-red-500/20";
    if (score >= 60) return "bg-orange-500/10 border-orange-500/20";
    if (score >= 40) return "bg-amber-500/10 border-amber-500/20";
    return "bg-blue-500/10 border-blue-500/20";
}

// ── Virality Ring SVG ──────────────────────────────────────────────────────────

function ViralityRing({ score, size = 44 }: { score: number; size?: number }) {
    const strokeWidth = 3;
    const radius = (size - strokeWidth * 2) / 2;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (Math.min(score, 100) / 100) * circumference;
    return (
        <div className="relative" style={{ width: size, height: size }}>
            <svg width={size} height={size} className="-rotate-90">
                <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={strokeWidth} />
                <circle
                    cx={size / 2} cy={size / 2} r={radius} fill="none"
                    className={`${getViralityRingColor(score)} transition-all duration-700`}
                    strokeWidth={strokeWidth} strokeLinecap="round"
                    strokeDasharray={circumference} strokeDashoffset={offset}
                />
            </svg>
            <span className={`absolute inset-0 flex items-center justify-center text-xs font-bold ${getViralityColor(score)}`}>
                {Math.round(score)}
            </span>
        </div>
    );
}

// ── Stat Card ──────────────────────────────────────────────────────────────────

function StatCard({ label, value, icon: Icon, color, subtitle }: {
    label: string; value: number | string; icon: any; color: string; subtitle?: string;
}) {
    return (
        <div className="relative group">
            <div className={`absolute inset-0 rounded-xl bg-gradient-to-br ${color} opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-xl`} />
            <div className="relative bg-stone-900/60 backdrop-blur-sm border border-white/[0.06] rounded-xl p-4 hover:border-white/[0.12] transition-all duration-300">
                <div className="flex items-center gap-2 mb-2">
                    <div className={`p-1.5 rounded-lg bg-white/[0.06]`}>
                        <Icon className="w-3.5 h-3.5 text-stone-400" />
                    </div>
                    <span className="text-[11px] font-medium text-stone-500 uppercase tracking-wider">{label}</span>
                </div>
                <div className="text-2xl font-bold text-white">{value}</div>
                {subtitle && <p className="text-[11px] text-stone-500 mt-1">{subtitle}</p>}
            </div>
        </div>
    );
}

// ── Platform Radar Card ────────────────────────────────────────────────────────

function PlatformRadar({ platform, items, queue, onToggleQueue }: {
    platform: string; items: SocialPulseItem[]; queue: Set<string>; onToggleQueue: (item: SocialPulseItem) => void;
}) {
    const cfg = PLATFORM_CONFIG[platform] || { label: platform, icon: "📊", gradient: "from-stone-500/20 to-stone-600/5", glow: "shadow-stone-500/20", text: "text-stone-400", bg: "bg-stone-500/10" };
    const top = items.slice(0, 3);

    return (
        <div className={`group relative bg-stone-900/40 backdrop-blur-sm border border-white/[0.06] rounded-xl overflow-hidden hover:border-white/[0.12] transition-all duration-300`}>
            <div className={`absolute inset-0 bg-gradient-to-br ${cfg.gradient} opacity-50`} />
            <div className="relative p-4">
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                        <span className="text-lg">{cfg.icon}</span>
                        <span className={`text-sm font-semibold ${cfg.text}`}>{cfg.label}</span>
                    </div>
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${cfg.bg} ${cfg.text}`}>
                        {items.length} items
                    </span>
                </div>
                <div className="space-y-2">
                    {top.map((item, i) => (
                        <div key={item.id || i} className="flex items-center gap-2 group/item">
                            <ViralityRing score={item.virality_score} size={32} />
                            <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium text-stone-300 truncate group-hover/item:text-white transition-colors">
                                    {item.title}
                                </p>
                            </div>
                            <button
                                onClick={() => onToggleQueue(item)}
                                className={`p-1 rounded-md transition-all duration-200 flex-shrink-0 ${queue.has(item.id)
                                    ? "bg-stone-700/20 text-stone-500"
                                    : "text-stone-600 hover:text-stone-500 hover:bg-white/5"
                                    }`}
                            >
                                {queue.has(item.id) ? <BookmarkCheck className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                            </button>
                        </div>
                    ))}
                    {top.length === 0 && (
                        <p className="text-xs text-stone-600 italic py-2">No data — click Refresh</p>
                    )}
                </div>
            </div>
        </div>
    );
}

// ── Trend Card ─────────────────────────────────────────────────────────────────

function TrendCard({ item, queue, onToggleQueue, niches }: {
    item: SocialPulseItem; queue: Set<string>; onToggleQueue: (item: SocialPulseItem) => void; niches: PulseNiche[];
}) {
    const pcfg = PLATFORM_CONFIG[item.platform] || { label: item.platform, icon: "📊", text: "text-stone-400", bg: "bg-stone-500/10", gradient: "", glow: "" };
    const isQueued = queue.has(item.id);
    const sentColor = SENTIMENT_COLORS[item.sentiment || "neutral"] || SENTIMENT_COLORS.neutral;
    const niche = item.niche_id ? niches.find(n => n.id === item.niche_id) : null;

    return (
        <div className={`group relative bg-stone-900/40 backdrop-blur-sm border rounded-xl overflow-hidden transition-all duration-300 hover:translate-y-[-2px] hover:shadow-lg ${isQueued ? "border-stone-600/30 shadow-stone-500/10" : "border-white/[0.06] hover:border-white/[0.12]"
            }`}>
            <div className="p-4">
                {/* Top row: platform + virality + actions */}
                <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${pcfg.bg} ${pcfg.text}`}>
                            <span>{pcfg.icon}</span> {pcfg.label}
                        </span>
                        {niche && (
                            <span
                                className="text-[10px] font-medium px-2 py-0.5 rounded-full"
                                style={{ backgroundColor: (niche.color || "#6366f1") + "15", color: niche.color || "#6366f1" }}
                            >
                                {niche.name}
                            </span>
                        )}
                        <span className="flex items-center gap-1">
                            <span className={`w-1.5 h-1.5 rounded-full ${sentColor}`} />
                            <span className="text-[10px] text-stone-600 capitalize">{item.sentiment || "neutral"}</span>
                        </span>
                    </div>
                    <ViralityRing score={item.virality_score} size={40} />
                </div>

                {/* Title */}
                <h3 className="text-sm font-semibold text-stone-200 leading-snug mb-2 line-clamp-2 group-hover:text-white transition-colors">
                    {item.title}
                </h3>

                {/* Description */}
                {item.description && (
                    <p className="text-xs text-stone-500 line-clamp-2 mb-3">{item.description}</p>
                )}

                {/* Bottom row: time + actions */}
                <div className="flex items-center justify-between pt-2 border-t border-white/[0.04]">
                    <span className="text-[10px] text-stone-600 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {timeAgo(item.fetched_at)}
                    </span>
                    <div className="flex items-center gap-1">
                        {item.url && (
                            <a
                                href={item.url} target="_blank" rel="noopener noreferrer"
                                className="p-1.5 rounded-lg text-stone-600 hover:text-stone-300 hover:bg-white/5 transition-all"
                                title="View source"
                            >
                                <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                        )}
                        <button
                            onClick={() => onToggleQueue(item)}
                            className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-all duration-200 ${isQueued
                                ? "bg-stone-700/20 text-stone-500 hover:bg-stone-700/30"
                                : "bg-white/5 text-stone-500 hover:text-stone-500 hover:bg-stone-700/10"
                                }`}
                        >
                            {isQueued ? (
                                <><BookmarkCheck className="w-3 h-3" /> Queued</>
                            ) : (
                                <><Plus className="w-3 h-3" /> Queue</>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ── Content Queue Sidebar ──────────────────────────────────────────────────────

function ContentQueue({ queue, queueItems, onRemove, onClear }: {
    queue: Set<string>; queueItems: SocialPulseItem[]; onRemove: (id: string) => void; onClear: () => void;
}) {
    const copyToClipboard = () => {
        const text = queueItems.map((item, i) =>
            `${i + 1}. [${item.platform}] ${item.title}${item.url ? `\n   ${item.url}` : ""}`
        ).join("\n\n");
        navigator.clipboard.writeText(text);
    };

    return (
        <div className="bg-stone-900/60 backdrop-blur-sm border border-white/[0.06] rounded-xl overflow-hidden h-fit sticky top-6">
            {/* Header */}
            <div className="p-4 border-b border-white/[0.06] bg-gradient-to-r from-stone-600/10 to-purple-500/10">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded-lg bg-stone-700/20">
                            <Target className="w-4 h-4 text-stone-500" />
                        </div>
                        <div>
                            <h3 className="text-sm font-bold text-white">Content Queue</h3>
                            <p className="text-[10px] text-stone-500">{queue.size} topics selected</p>
                        </div>
                    </div>
                    {queue.size > 0 && (
                        <div className="flex items-center gap-1">
                            <button
                                onClick={copyToClipboard}
                                className="p-1.5 rounded-lg text-stone-500 hover:text-stone-500 hover:bg-white/5 transition-all"
                                title="Copy to clipboard"
                            >
                                <Copy className="w-3.5 h-3.5" />
                            </button>
                            <button
                                onClick={onClear}
                                className="p-1.5 rounded-lg text-stone-500 hover:text-red-400 hover:bg-red-500/10 transition-all"
                                title="Clear all"
                            >
                                <Trash2 className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* Items */}
            <div className="max-h-[60vh] overflow-y-auto custom-scrollbar">
                {queueItems.length === 0 ? (
                    <div className="p-6 text-center">
                        <Bookmark className="w-8 h-8 mx-auto text-stone-700 mb-2" />
                        <p className="text-xs text-stone-600 mb-1">No topics selected</p>
                        <p className="text-[10px] text-stone-700">
                            Click <Plus className="w-3 h-3 inline" /> on any trend to add it to your content queue
                        </p>
                    </div>
                ) : (
                    <div className="p-2 space-y-1">
                        {queueItems.map((item, i) => {
                            const pcfg = PLATFORM_CONFIG[item.platform] || { text: "text-stone-400", icon: "📊" };
                            return (
                                <div key={item.id} className="group flex items-start gap-2 p-2 rounded-lg hover:bg-white/[0.03] transition-colors">
                                    <span className="text-[10px] font-bold text-stone-600 mt-1 w-4 text-right shrink-0">{i + 1}</span>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs font-medium text-stone-300 line-clamp-2 leading-snug">{item.title}</p>
                                        <div className="flex items-center gap-2 mt-1">
                                            <span className={`text-[10px] ${pcfg.text}`}>{pcfg.icon} {PLATFORM_CONFIG[item.platform]?.label || item.platform}</span>
                                            <span className={`text-[10px] font-semibold ${getViralityColor(item.virality_score)}`}>
                                                ⚡ {Math.round(item.virality_score)}
                                            </span>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => onRemove(item.id)}
                                        className="p-1 rounded text-stone-700 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all shrink-0"
                                    >
                                        <X className="w-3 h-3" />
                                    </button>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function SocialPulsePage() {
    const [dashboard, setDashboard] = useState<SocialPulseDashboard | null>(null);
    const [trends, setTrends] = useState<SocialPulseItem[]>([]);
    const [niches, setNiches] = useState<PulseNiche[]>([]);
    const [keywords, setKeywords] = useState<TrendKeyword[]>([]);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [selectedNiche, setSelectedNiche] = useState<string | undefined>(undefined);
    const [selectedRegion, setSelectedRegion] = useState("US");
    const [activeTab, setActiveTab] = useState("All");
    const [showSettings, setShowSettings] = useState(false);
    const [insights, setInsights] = useState<string | null>(null);
    const [insightsModel, setInsightsModel] = useState<string | null>(null);
    const [loadingInsights, setLoadingInsights] = useState(false);
    const [availableModels, setAvailableModels] = useState<{ provider: string; model: string; label: string }[]>([]);
    const [selectedModelKey, setSelectedModelKey] = useState<string>("groq::moonshotai/kimi-k2-instruct");
    const [newKeyword, setNewKeyword] = useState("");
    const [newNiche, setNewNiche] = useState({ name: "", description: "", google_trends_keywords: "", subreddits: "", color: "#6366f1" });
    const [addingNiche, setAddingNiche] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [platformStatus, setPlatformStatus] = useState<Record<string, { ok: boolean; error?: string; fix?: string; note?: string }> | null>(null);
    const [purging, setPurging] = useState(false);
    const [showPurgeConfirm, setShowPurgeConfirm] = useState(false);
    const [showInsights, setShowInsights] = useState(false);
    const [themes, setThemes] = useState<SocialPulseTheme[]>([]);
    const [loadingThemes, setLoadingThemes] = useState(false);
    const [isTrackedMode, setIsTrackedMode] = useState(false);

    // Dynamic theme colors
    const themeColor = isTrackedMode ? "purple" : "brand";
    const themeColorHex = isTrackedMode ? "#a855f7" : "#6366f1";

    // Content queue state
    const [queue, setQueue] = useState<Set<string>>(new Set());
    const [queueItems, setQueueItems] = useState<SocialPulseItem[]>([]);

    const toggleQueue = useCallback((item: SocialPulseItem) => {
        setQueue(prev => {
            const next = new Set(prev);
            if (next.has(item.id)) {
                next.delete(item.id);
                setQueueItems(qi => qi.filter(q => q.id !== item.id));
            } else {
                next.add(item.id);
                setQueueItems(qi => [...qi, item]);
            }
            return next;
        });
    }, []);

    const clearQueue = useCallback(() => {
        setQueue(new Set());
        setQueueItems([]);
    }, []);

    const removeFromQueue = useCallback((id: string) => {
        setQueue(prev => {
            const next = new Set(prev);
            next.delete(id);
            return next;
        });
        setQueueItems(qi => qi.filter(q => q.id !== id));
    }, []);

    const fetchAll = useCallback(async () => {
        try {
            const [dash, nicheList, kwList, status, models] = await Promise.all([
                socialPulseApi.dashboard(selectedNiche, isTrackedMode),
                socialPulseApi.niches.list(),
                socialPulseApi.keywords.list(),
                socialPulseApi.status(),
                socialPulseApi.models(),
            ]);
            setPlatformStatus(status);
            setAvailableModels(models);
            if (models.length > 0 && !selectedModelKey) {
                setSelectedModelKey(`${models[0].provider}::${models[0].model}`);
            }
            setDashboard(dash);
            setNiches(nicheList);
            setKeywords(kwList);

            const platform = activeTab !== "All" && activeTab !== "Tracked Keywords" ? TAB_PLATFORM[activeTab] : undefined;
            const tracked_only = isTrackedMode || activeTab === "Tracked Keywords";
            const trendList = await socialPulseApi.trends({ 
                platform, 
                niche_id: selectedNiche, 
                tracked_only,
                limit: 100 
            });
            setTrends(trendList);
        } catch (e: any) {
            setError(e.message || "Failed to load data");
        } finally {
            setLoading(false);
        }
    }, [selectedNiche, activeTab, isTrackedMode]);

    useEffect(() => {
        setLoading(true);
        fetchAll();
    }, [fetchAll]);

    useEffect(() => {
        const interval = setInterval(() => { fetchAll(); }, 60000);
        return () => clearInterval(interval);
    }, [fetchAll]);

    async function handlePurge() {
        setPurging(true);
        setShowPurgeConfirm(false);
        try {
            await socialPulseApi.purge();
            setDashboard(null);
            setTrends([]);
            setInsights(null);
            setError(null);
            await fetchAll();
        } catch (e: any) {
            setError("Purge failed: " + e.message);
        } finally {
            setPurging(false);
        }
    }

    async function handleRefresh() {
        setRefreshing(true);
        try {
            await socialPulseApi.refresh(selectedRegion);
            setTimeout(() => fetchAll(), 3000);
        } catch (e: any) {
            setError("Refresh failed: " + e.message);
        } finally {
            setTimeout(() => setRefreshing(false), 3000);
        }
    }

    async function handleAddKeyword() {
        if (!newKeyword.trim()) return;
        try {
            await socialPulseApi.keywords.add(newKeyword.trim());
            setNewKeyword("");
            const updated = await socialPulseApi.keywords.list();
            setKeywords(updated);
        } catch (e: any) { setError(e.message); }
    }

    async function handleDeleteKeyword(id: string) {
        await socialPulseApi.keywords.delete(id);
        setKeywords(kws => kws.filter(k => k.id !== id));
    }

    async function handleAddNiche() {
        if (!newNiche.name.trim()) return;
        setAddingNiche(true);
        try {
            await socialPulseApi.niches.create({
                name: newNiche.name,
                description: newNiche.description,
                google_trends_keywords: newNiche.google_trends_keywords.split(",").map(s => s.trim()).filter(Boolean),
                subreddits: newNiche.subreddits.split(",").map(s => s.trim()).filter(Boolean),
                color: newNiche.color,
            } as any);
            setNewNiche({ name: "", description: "", google_trends_keywords: "", subreddits: "", color: "#6366f1" });
            const updated = await socialPulseApi.niches.list();
            setNiches(updated);
        } catch (e: any) { setError(e.message); }
        finally { setAddingNiche(false); }
    }

    async function handleToggleNiche(niche: PulseNiche) {
        await socialPulseApi.niches.update(niche.id, { is_active: !niche.is_active } as any);
        setNiches(ns => ns.map(n => n.id === niche.id ? { ...n, is_active: !n.is_active } : n));
    }

    async function handleDeleteNiche(id: string) {
        try {
            await socialPulseApi.niches.delete(id);
            setNiches(ns => ns.filter(n => n.id !== id));
        } catch (e: any) { setError(e.message); }
    }

    async function handleGetInsights() {
        setLoadingInsights(true);
        setInsights(null);
        setInsightsModel(null);
        try {
            const [provider, model] = selectedModelKey.split("::");
            
            // Gather titles for deduplication & context
            const queuedTitles = queueItems.map(item => item.title);
            const trackedKeywords = keywords.map(kw => kw.keyword);
            
            const result = await socialPulseApi.insights({ 
                niche_id: selectedNiche, 
                provider, 
                model,
                queued_titles: queuedTitles,
                tracked_keywords: trackedKeywords
            });
            setInsights(result.insights);
            setInsightsModel(result.model || null);
        } catch (e: any) {
            setInsights("Failed to generate insights: " + e.message);
        } finally {
            setLoadingInsights(false);
        }
    }

    async function handleGetThemes() {
        setLoadingThemes(true);
        try {
            const [provider, model] = selectedModelKey.split("::");
            const result = await socialPulseApi.themes({ niche_id: selectedNiche, provider, model });
            setThemes(result);
        } catch (e: any) {
            setError("Failed to generate themes: " + e.message);
        } finally {
            setLoadingThemes(false);
        }
    }

    // Group trends by platform for radar
    const byPlatform: Record<string, SocialPulseItem[]> = {};
    for (const t of trends) {
        if (!byPlatform[t.platform]) byPlatform[t.platform] = [];
        byPlatform[t.platform].push(t);
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center h-screen bg-stone-950">
                <div className="flex flex-col items-center gap-4">
                    <div className="relative">
                        <div className="w-12 h-12 rounded-full border-2 border-stone-600/20 border-t-stone-600 animate-spin" />
                        <Radio className="w-5 h-5 text-stone-500 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                    </div>
                    <p className="text-sm text-stone-500 animate-pulse">Scanning the internet...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-stone-950">
            {/* ── HEADER ─────────────────────────────────────────────────── */}
            <div className="relative overflow-hidden">
                {/* Background effects */}
                <div className="absolute inset-0 bg-gradient-to-br from-stone-900/80 via-stone-950 to-purple-950/40" />
                <div className="absolute top-0 left-1/4 w-96 h-96 bg-stone-700/10 rounded-full blur-3xl" />
                <div className="absolute bottom-0 right-1/4 w-64 h-64 bg-purple-500/10 rounded-full blur-3xl" />

                <div className="relative px-6 pt-6 pb-5">
                    {/* Title row */}
                    <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
                        <div className="flex items-start gap-6">
                            <div>
                                <div className="flex items-center gap-3 mb-1">
                                    <div className="relative">
                                        <Radio className={`w-6 h-6 text-${themeColor}-400`} />
                                        <span className={`absolute -top-0.5 -right-0.5 w-2 h-2 bg-emerald-400 rounded-full animate-pulse`} />
                                    </div>
                                    <h1 className="text-xl font-bold text-white tracking-tight">
                                        Social Pulse
                                        <span className="text-stone-500 font-normal ml-2 text-sm">Mission Control</span>
                                    </h1>
                                </div>
                                <p className="text-xs text-stone-500 ml-9">
                                    {isTrackedMode ? "Showing only content matching your specific tracked keywords" : "Real-time trend intelligence across Google, YouTube, Reddit & HN"}
                                </p>
                            </div>

                            {/* Mode Tabs */}
                            <div className="flex p-1 bg-white/5 rounded-xl border border-white/10 mt-1">
                                <button
                                    onClick={() => { setIsTrackedMode(false); setActiveTab("All"); setThemes([]); }}
                                    className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-all flex items-center gap-2 ${!isTrackedMode ? "bg-stone-700 text-white shadow-lg shadow-stone-500/20" : "text-stone-500 hover:text-stone-300"}`}
                                >
                                    <Globe className="w-3.5 h-3.5" /> Everything
                                </button>
                                <button
                                    onClick={() => { setIsTrackedMode(true); setActiveTab("All"); setThemes([]); }}
                                    className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-all flex items-center gap-2 ${isTrackedMode ? "bg-purple-600 text-white shadow-lg shadow-purple-500/20" : "text-stone-500 hover:text-stone-300"}`}
                                >
                                    <Target className="w-3.5 h-3.5" /> Tracked Keywords
                                </button>
                            </div>
                        </div>

                        <div className="flex items-center gap-2 flex-wrap">
                            {/* Quick Add Keyword */}
                            <div className="relative group">
                                <Hash className={`absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-stone-500 group-focus-within:text-${themeColor}-400 transition-colors`} />
                                <input
                                    type="text"
                                    placeholder="Add keyword..."
                                    value={newKeyword}
                                    onChange={e => setNewKeyword(e.target.value)}
                                    onKeyDown={e => e.key === "Enter" && handleAddKeyword()}
                                    className={`pl-8 pr-3 py-1.5 text-xs bg-white/5 border border-white/10 rounded-lg text-stone-300 focus:outline-none focus:ring-1 focus:ring-${themeColor}-500/50 w-32 md:w-48 placeholder:text-stone-600 transition-all`}
                                />
                            </div>

                            {/* Region */}
                            <select
                                value={selectedRegion}
                                onChange={e => setSelectedRegion(e.target.value)}
                                className="text-xs bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-stone-300 focus:outline-none focus:ring-1 focus:ring-stone-600/50"
                            >
                                {REGIONS.map(r => <option key={r} value={r} className="bg-stone-900">{r}</option>)}
                            </select>

                            {/* Settings */}
                            <button
                                onClick={() => setShowSettings(!showSettings)}
                                className={`p-2 rounded-lg transition-colors ${showSettings ? "bg-white/10 text-white" : "text-stone-500 hover:text-stone-300 hover:bg-white/5"}`}
                            >
                                <Settings2 className="w-4 h-4" />
                            </button>

                            {/* Purge */}
                            {!showPurgeConfirm ? (
                                <button
                                    onClick={() => setShowPurgeConfirm(true)}
                                    disabled={purging}
                                    className="flex items-center gap-1.5 px-3 py-1.5 text-red-400/70 hover:text-red-400 hover:bg-red-500/10 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                                >
                                    <Trash2 className="w-3.5 h-3.5" /> Purge
                                </button>
                            ) : (
                                <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-1.5">
                                    <span className="text-[11px] text-red-400 font-medium">Delete all?</span>
                                    <button onClick={handlePurge} className="text-[11px] px-2 py-0.5 bg-red-500 text-white rounded font-medium hover:bg-red-600">Yes</button>
                                    <button onClick={() => setShowPurgeConfirm(false)} className="text-[11px] px-2 py-0.5 bg-white/10 text-stone-300 rounded font-medium hover:bg-white/20">No</button>
                                </div>
                            )}

                            {/* Refresh */}
                            <button
                                onClick={handleRefresh}
                                disabled={refreshing}
                                className={`flex items-center gap-1.5 px-4 py-1.5 bg-${themeColor === 'purple' ? 'purple-600' : 'stone-700'} hover:bg-${themeColor === 'purple' ? 'purple-500' : 'stone-600'} text-white rounded-lg text-xs font-semibold transition-all disabled:opacity-50 shadow-lg shadow-${themeColor}-500/20`}
                            >
                                <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
                                {refreshing ? "Scanning..." : isTrackedMode ? "Sync Keywords" : "Refresh"}
                            </button>
                        </div>
                    </div>

                    {/* Niche filters */}
                    <div className="flex items-center gap-1.5 flex-wrap mb-3">
                        <button
                            onClick={() => setSelectedNiche(undefined)}
                            className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${!selectedNiche
                                ? `bg-${themeColor === 'purple' ? 'purple-500' : 'stone-600'} text-white shadow-lg shadow-${themeColor}-500/30`
                                : "bg-white/5 text-stone-500 hover:text-stone-300 hover:bg-white/10"
                                }`}
                        >
                            All Niches
                        </button>
                        {niches.filter(n => n.is_active).map(n => (
                            <button
                                key={n.id}
                                onClick={() => setSelectedNiche(n.id === selectedNiche ? undefined : n.id)}
                                className="px-3 py-1 rounded-full text-xs font-medium transition-all"
                                style={selectedNiche === n.id
                                    ? { backgroundColor: n.color || themeColorHex, color: "white", boxShadow: `0 4px 14px ${(n.color || themeColorHex)}40` }
                                    : { backgroundColor: (n.color || themeColorHex) + "12", color: (n.color || themeColorHex) }
                                }
                            >
                                {n.name}
                            </button>
                        ))}
                    </div>

                    {/* Tracked Keyword Chips */}
                    {keywords.length > 0 && (
                        <div className="flex items-center gap-2 flex-wrap mb-5">
                            <span className="text-[10px] font-bold text-stone-600 uppercase tracking-widest mr-1">Tracked:</span>
                            {keywords.map(kw => (
                                <div key={kw.id} className={`flex items-center gap-1.5 px-2.5 py-1 bg-white/[0.03] border border-white/[0.06] rounded-lg group/kw transition-all hover:border-${themeColor}-500/30`}>
                                    <Hash className={`w-2.5 h-2.5 text-stone-600 group-hover/kw:text-${themeColor}-400`} />
                                    <span className="text-[11px] font-medium text-stone-400 group-hover/kw:text-stone-200">{kw.keyword}</span>
                                    <button 
                                        onClick={() => handleDeleteKeyword(kw.id)}
                                        className="text-stone-700 hover:text-red-400 opacity-0 group-hover/kw:opacity-100 transition-all"
                                    >
                                        <X className="w-2.5 h-2.5" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Stat cards */}
                    {dashboard && (
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                            <StatCard label={isTrackedMode ? "Keyword Matches" : "Tracking"} value={dashboard.total_trending} icon={isTrackedMode ? Target : Activity} color={`from-${themeColor}-500/20 to-transparent`} subtitle={isTrackedMode ? "matching content" : "total trends"} />
                            <StatCard label={isTrackedMode ? "Viral Matches" : "Viral"} value={dashboard.viral_count} icon={Flame} color="from-red-500/20 to-transparent" subtitle="score > 70" />
                            <StatCard label={isTrackedMode ? "Tracked" : "Niches"} value={isTrackedMode ? dashboard.keyword_count : dashboard.active_niches} icon={isTrackedMode ? Hash : Layers} color={`from-${themeColor === 'purple' ? 'brand' : 'amber'}-500/20 to-transparent`} subtitle={isTrackedMode ? "keywords" : "active"} />
                            <StatCard label={isTrackedMode ? "Precision" : "Keywords"} value={isTrackedMode ? (dashboard.total_trending > 0 ? "Filtered" : "No Matches") : dashboard.keyword_count} icon={Activity} color="from-emerald-500/20 to-transparent" subtitle={isTrackedMode ? "intelligence mode" : "tracked"} />
                        </div>
                    )}
                </div>
            </div>

            {/* ── ERROR & STATUS ────────────────────────────────────────── */}
            <div className="px-6">
                {error && (
                    <div className="mt-4 bg-red-500/10 border border-red-500/20 rounded-lg p-3 flex items-center justify-between">
                        <span className="text-red-400 text-xs">{error}</span>
                        <button onClick={() => setError(null)} className="text-red-500/50 hover:text-red-400"><X className="w-4 h-4" /></button>
                    </div>
                )}
                {platformStatus && Object.values(platformStatus).some(s => !s.ok) && (
                    <div className="mt-4 bg-amber-500/10 border border-amber-500/20 rounded-lg p-3">
                        <div className="flex flex-wrap gap-4">
                            {Object.entries(platformStatus).map(([p, s]) => (
                                <div key={p} className="flex items-center gap-2">
                                    <span className={`w-2 h-2 rounded-full ${s.ok ? "bg-emerald-400" : "bg-red-400"}`} />
                                    <span className="text-xs text-stone-300 capitalize">{p.replace("_", " ")}</span>
                                    {!s.ok && s.error && <span className="text-[10px] text-red-400/80 max-w-[200px] truncate">{s.error}</span>}
                                    {!s.ok && s.fix && (
                                        <a href={s.fix} target="_blank" rel="noopener noreferrer" className="text-[10px] text-blue-400 hover:underline">Fix →</a>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* ── MAIN CONTENT ─────────────────────────────────────────── */}
            <div className="px-6 py-5">
                <div className="flex gap-5">
                    {/* LEFT: Main content area */}
                    <div className="flex-1 min-w-0 space-y-5">

                        {/* Prominent Themes */}
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <h2 className="text-xs font-semibold text-stone-500 uppercase tracking-wider flex items-center gap-2">
                                    <Layers className={`w-3.5 h-3.5 text-${themeColor}-400`} /> Prominent Themes
                                </h2>
                                <button 
                                    onClick={handleGetThemes}
                                    disabled={loadingThemes}
                                    className="text-[10px] flex items-center gap-1 px-2 py-1 bg-white/5 hover:bg-white/10 text-stone-400 hover:text-white rounded transition-all disabled:opacity-30"
                                >
                                    <RefreshCw className={`w-2.5 h-2.5 ${loadingThemes ? "animate-spin" : ""}`} />
                                    {themes.length > 0 ? "Regenerate Themes" : "Scan for Themes"}
                                </button>
                            </div>

                            {loadingThemes ? (
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                    {[1, 2, 3].map(i => (
                                        <div key={i} className="h-24 bg-stone-900/40 border border-white/[0.04] rounded-xl animate-pulse" />
                                    ))}
                                </div>
                            ) : themes.length > 0 ? (
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                    {themes.map((t, i) => (
                                        <div key={i} className={`group relative bg-stone-900/60 backdrop-blur-sm border border-white/[0.06] rounded-xl p-3 hover:border-${themeColor}-500/30 transition-all duration-300`}>
                                            <div className="flex items-start justify-between mb-2">
                                                <h3 className={`text-xs font-bold text-white group-hover:text-${themeColor}-400 transition-colors line-clamp-1`}>{t.theme}</h3>
                                                <div className="flex items-center gap-1">
                                                    <Zap className="w-2.5 h-2.5 text-amber-400" />
                                                    <span className="text-[10px] font-bold text-amber-400">{Math.round(t.virality_score)}</span>
                                                </div>
                                            </div>
                                            <p className="text-[10px] text-stone-500 line-clamp-2 leading-relaxed mb-2">{t.description}</p>
                                            <div className="flex flex-wrap gap-1">
                                                {t.keywords.slice(0, 2).map((kw, ki) => (
                                                    <span key={ki} className={`text-[9px] px-1.5 py-0.5 bg-${themeColor}-500/10 text-${themeColor}-400 rounded-md border border-${themeColor}-500/10`}>#{kw}</span>
                                                ))}
                                                {t.related_platforms.map(p => (
                                                    <span key={p} className="text-[9px] px-1.5 py-0.5 bg-white/5 text-stone-500 rounded-md uppercase font-bold">{PLATFORM_CONFIG[p]?.icon || "📊"}</span>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="py-8 bg-stone-900/20 border border-dashed border-white/[0.06] rounded-xl flex flex-col items-center justify-center text-center px-4">
                                    <Layers className="w-6 h-6 text-stone-800 mb-2" />
                                    <p className="text-[11px] text-stone-600">No themes identified yet. Scan the current trends to group them into narratives.</p>
                                </div>
                            )}
                        </div>

                        {/* Platform Radar */}
                        <div>
                            <h2 className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                                <BarChart3 className="w-3.5 h-3.5" /> Platform Radar
                            </h2>
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                                {["google_trends", "youtube", "reddit", "hackernews"].map(p => (
                                    <PlatformRadar
                                        key={p}
                                        platform={p}
                                        items={byPlatform[p] || []}
                                        queue={queue}
                                        onToggleQueue={toggleQueue}
                                    />
                                ))}
                            </div>
                        </div>

                        {/* AI Insights (collapsible) */}
                        <div className="bg-stone-900/40 backdrop-blur-sm border border-white/[0.06] rounded-xl overflow-hidden">
                            <button
                                onClick={() => setShowInsights(!showInsights)}
                                className="w-full flex items-center justify-between p-4 hover:bg-white/[0.02] transition-colors"
                            >
                                <div className="flex items-center gap-2">
                                    <Sparkles className="w-4 h-4 text-amber-400" />
                                    <span className="text-sm font-semibold text-stone-300">AI Content Insights</span>
                                    {insights && <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400">Generated</span>}
                                </div>
                                {showInsights ? <ChevronUp className="w-4 h-4 text-stone-600" /> : <ChevronDown className="w-4 h-4 text-stone-600" />}
                            </button>
                            {showInsights && (
                                <div className="p-4 pt-0 border-t border-white/[0.04]">
                                    <div className="flex items-center gap-2 mb-3 pt-3">
                                        {availableModels.length > 0 ? (
                                            <select
                                                value={selectedModelKey}
                                                onChange={e => setSelectedModelKey(e.target.value)}
                                                className={`text-xs bg-white/5 border border-white/10 rounded-lg px-2.5 py-1.5 text-stone-300 focus:outline-none focus:ring-1 focus:ring-${themeColor}-500/50`}
                                            >
                                                {availableModels.map(m => (
                                                    <option key={`${m.provider}::${m.model}`} value={`${m.provider}::${m.model}`} className="bg-stone-900">
                                                        {m.label}
                                                    </option>
                                                ))}
                                            </select>
                                        ) : (
                                            <span className="text-xs text-stone-600">No LLM configured</span>
                                        )}
                                        <button
                                            onClick={handleGetInsights}
                                            disabled={loadingInsights || availableModels.length === 0}
                                            className={`text-xs px-3 py-1.5 bg-${themeColor}-600 text-white rounded-lg hover:bg-${themeColor}-500 disabled:opacity-50 transition-colors font-medium`}
                                        >
                                            {loadingInsights ? "Analyzing..." : "Generate"}
                                        </button>
                                    </div>
                                    {insights ? (
                                        <div className="bg-white/[0.02] rounded-lg p-3">
                                            <p className="text-xs text-stone-300 whitespace-pre-line leading-relaxed">{insights}</p>
                                            {insightsModel && <p className="text-[10px] text-stone-600 mt-2">by {insightsModel}</p>}
                                        </div>
                                    ) : (
                                        <p className="text-[11px] text-stone-600">Generate AI-powered content recommendations from current trends</p>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Tab bar */}
                        <div className="flex items-center gap-1 bg-stone-900/40 backdrop-blur-sm border border-white/[0.06] rounded-xl p-1">
                            {TABS.map(tab => (
                                <button
                                    key={tab}
                                    onClick={() => setActiveTab(tab)}
                                    className={`px-4 py-2 text-xs font-medium rounded-lg transition-all ${activeTab === tab
                                        ? `bg-${themeColor}-500/20 text-${themeColor}-400 shadow-sm`
                                        : "text-stone-500 hover:text-stone-300 hover:bg-white/5"
                                        }`}
                                >
                                    {tab}
                                </button>
                            ))}
                        </div>

                        {/* Trend Cards Grid */}
                        {trends.length === 0 ? (
                            <div className="py-20 text-center">
                                <Radio className="w-10 h-10 mx-auto mb-3 text-stone-800" />
                                <p className="text-sm text-stone-600 mb-1">No signals detected</p>
                                <p className="text-xs text-stone-700">Click <strong className="text-stone-500">Refresh</strong> to scan for trends</p>
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                                {trends.map(item => (
                                    <TrendCard
                                        key={item.id}
                                        item={item}
                                        queue={queue}
                                        onToggleQueue={toggleQueue}
                                        niches={niches}
                                    />
                                ))}
                            </div>
                        )}
                    </div>

                    {/* RIGHT: Content Queue sidebar */}
                    <div className="w-72 shrink-0 hidden lg:block">
                        <ContentQueue
                            queue={queue}
                            queueItems={queueItems}
                            onRemove={removeFromQueue}
                            onClear={clearQueue}
                        />
                    </div>
                </div>
            </div>

            {/* ── SETTINGS PANEL (Niches & Keywords) ───────────────────── */}
            {showSettings && (
                <div className="px-6 pb-6 space-y-4">
                    {/* Niches */}
                    <div className="bg-stone-900/40 backdrop-blur-sm border border-white/[0.06] rounded-xl p-5">
                        <h3 className="text-sm font-semibold text-stone-300 flex items-center gap-2 mb-4">
                            <Zap className="w-4 h-4 text-amber-400" /> Niche Manager
                            <span className="text-[10px] text-stone-600 font-normal ml-1">({niches.length})</span>
                        </h3>
                        <div className="grid gap-2 mb-4">
                            {niches.map(niche => (
                                <div key={niche.id} className="flex items-center justify-between p-3 bg-white/[0.02] rounded-lg border border-white/[0.04]">
                                    <div className="flex items-center gap-3">
                                        <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: niche.color || "#6366f1" }} />
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-medium text-stone-300">{niche.name}</span>
                                                {niche.is_builtin && <span className="text-[10px] bg-white/5 text-stone-600 px-1.5 py-0.5 rounded">built-in</span>}
                                                {!niche.is_active && <span className="text-[10px] bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded">off</span>}
                                            </div>
                                            {niche.google_trends_keywords.length > 0 && (
                                                <p className="text-[10px] text-stone-600 mt-0.5">{niche.google_trends_keywords.slice(0, 3).join(", ")}</p>
                                            )}
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => handleToggleNiche(niche)}
                                            className={`text-[10px] px-2 py-1 rounded transition-colors ${niche.is_active ? "bg-emerald-500/10 text-emerald-400" : "bg-white/5 text-stone-600"}`}
                                        >
                                            {niche.is_active ? "Active" : "Off"}
                                        </button>
                                        {!niche.is_builtin && (
                                            <button onClick={() => handleDeleteNiche(niche.id)} className="p-1 text-stone-700 hover:text-red-400 transition-colors">
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                        {/* Add niche */}
                        <div className="border border-dashed border-white/[0.08] rounded-lg p-4 space-y-3">
                            <p className="text-[10px] text-stone-600 font-semibold uppercase tracking-wider">New Niche</p>
                            <div className="grid grid-cols-2 gap-2">
                                <input type="text" placeholder="Name" value={newNiche.name} onChange={e => setNewNiche(n => ({ ...n, name: e.target.value }))}
                                    className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-stone-300 focus:outline-none focus:ring-1 focus:ring-stone-600/50 placeholder-stone-600" />
                                <input type="text" placeholder="Description" value={newNiche.description} onChange={e => setNewNiche(n => ({ ...n, description: e.target.value }))}
                                    className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-stone-300 focus:outline-none focus:ring-1 focus:ring-stone-600/50 placeholder-stone-600" />
                                <input type="text" placeholder="Keywords (comma-sep)" value={newNiche.google_trends_keywords} onChange={e => setNewNiche(n => ({ ...n, google_trends_keywords: e.target.value }))}
                                    className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-stone-300 focus:outline-none focus:ring-1 focus:ring-stone-600/50 placeholder-stone-600" />
                                <input type="text" placeholder="Subreddits (comma-sep)" value={newNiche.subreddits} onChange={e => setNewNiche(n => ({ ...n, subreddits: e.target.value }))}
                                    className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-stone-300 focus:outline-none focus:ring-1 focus:ring-stone-600/50 placeholder-stone-600" />
                            </div>
                            <div className="flex items-center gap-3">
                                <input type="color" value={newNiche.color} onChange={e => setNewNiche(n => ({ ...n, color: e.target.value }))}
                                    className="w-8 h-8 rounded border border-white/10 cursor-pointer bg-transparent" />
                                <button onClick={handleAddNiche} disabled={addingNiche || !newNiche.name.trim()}
                                    className="ml-auto flex items-center gap-1.5 px-4 py-2 bg-stone-700 text-white rounded-lg text-xs font-medium hover:bg-stone-700 disabled:opacity-50 transition-colors">
                                    <Plus className="w-3.5 h-3.5" /> {addingNiche ? "Adding..." : "Add Niche"}
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* Keywords */}
                    <div className="bg-stone-900/40 backdrop-blur-sm border border-white/[0.06] rounded-xl p-5">
                        <h3 className="text-sm font-semibold text-stone-300 flex items-center gap-2 mb-4">
                            <Hash className="w-4 h-4 text-purple-400" /> Keyword Tracker
                            <span className="text-[10px] text-stone-600 font-normal ml-1">({keywords.length})</span>
                        </h3>
                        <div className="flex gap-2 mb-3">
                            <input type="text" placeholder="Track a keyword..." value={newKeyword}
                                onChange={e => setNewKeyword(e.target.value)}
                                onKeyDown={e => e.key === "Enter" && handleAddKeyword()}
                                className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-stone-300 focus:outline-none focus:ring-1 focus:ring-stone-600/50 placeholder-stone-600" />
                            <button onClick={handleAddKeyword} disabled={!newKeyword.trim()}
                                className="flex items-center gap-1.5 px-3 py-2 bg-stone-700 text-white rounded-lg text-xs font-medium hover:bg-stone-700 disabled:opacity-50 transition-colors">
                                <Plus className="w-3.5 h-3.5" /> Track
                            </button>
                        </div>
                        {keywords.length === 0 ? (
                            <p className="text-xs text-stone-700 text-center py-3">No keywords tracked yet</p>
                        ) : (
                            <div className="flex flex-wrap gap-2">
                                {keywords.map(kw => (
                                    <div key={kw.id} className="flex items-center gap-2 bg-white/[0.03] border border-white/[0.06] rounded-full px-3 py-1.5">
                                        <span className="text-xs text-stone-300">{kw.keyword}</span>
                                        <button onClick={() => handleDeleteKeyword(kw.id)} className="text-stone-700 hover:text-red-400 transition-colors">
                                            <X className="w-3 h-3" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* ── FOOTER ───────────────────────────────────────────────── */}
            {dashboard?.last_refreshed && (
                <div className="px-6 pb-6">
                    <p className="text-center text-[10px] text-stone-700">
                        Last scan {timeAgo(dashboard.last_refreshed)} · Auto-refreshes every 30 min
                    </p>
                </div>
            )}
        </div>
    );
}
