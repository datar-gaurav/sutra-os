"use client";

import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { socialPulseApi, llmsApi, type SocialPulseItem, type PulseNiche, type SocialPulseTheme } from "@/lib/api";

// ── Model helpers ─────────────────────────────────────────────────────────────

const PROVIDER_MODELS: Record<string, { model: string; label: string }[]> = {
  anthropic:   [{ model: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" }, { model: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" }],
  openai:      [{ model: "gpt-4o-mini", label: "GPT-4o Mini" }, { model: "gpt-4o", label: "GPT-4o" }],
  google:      [{ model: "gemini-2.5-flash", label: "Gemini 2.5 Flash" }, { model: "gemini-1.5-flash", label: "Gemini 1.5 Flash" }],
  groq:        [{ model: "moonshotai/kimi-k2-instruct", label: "Kimi K2 (Groq)" }, { model: "llama-3.1-8b-instant", label: "Llama 3.1 8B (Groq)" }],
  ollama:      [{ model: "llama3.2", label: "Llama 3.2 (Ollama)" }, { model: "mistral", label: "Mistral (Ollama)" }],
  openrouter:  [{ model: "openai/gpt-4o-mini", label: "GPT-4o Mini (OpenRouter)" }],
};

type ModelOption = { provider: string; model: string; label: string };

async function loadModelOptions(): Promise<ModelOption[]> {
  try {
    // Try the social-pulse models endpoint first (env-key based)
    const direct = await socialPulseApi.models().catch(() => []);
    if (direct.length > 0) return direct;
    // Fall back to configured LLM providers from the database
    const providers = await llmsApi.list().catch(() => []);
    const opts: ModelOption[] = [];
    providers.filter(p => p.is_enabled && p.has_api_key).forEach(p => {
      const models = PROVIDER_MODELS[p.provider_type] || [];
      models.forEach(m => opts.push({ provider: p.provider_type, model: m.model, label: `${m.label} · ${p.name}` }));
    });
    return opts;
  } catch {
    return [];
  }
}

// ── Types ──────────────────────────────────────────────────────────────────────

type SourceKey = "google" | "youtube" | "reddit" | "hn";

interface TermTrend {
  id: string;
  source: SourceKey;
  niche: string;
  nicheId: string | null;
  score: number;
  title: string;
  meta: string;
  stats: string;
  age: string;
  url: string | null;
  sentiment: string;
}

interface SourceMeta {
  label: string;
  short: string;
  glyph: string;
  count: number;
}

// ── Constants ──────────────────────────────────────────────────────────────────

const SOURCES: Record<SourceKey, SourceMeta> = {
  google:  { label: "Google Trends", short: "GOOG", glyph: "◐", count: 0 },
  youtube: { label: "YouTube",       short: "YT",   glyph: "▶", count: 0 },
  reddit:  { label: "Reddit",        short: "RDDT", glyph: "◆", count: 0 },
  hn:      { label: "Hacker News",   short: "HN",   glyph: "⚡", count: 0 },
};

const SOURCE_KEYS: SourceKey[] = ["google", "youtube", "reddit", "hn"];

// ── Helpers ────────────────────────────────────────────────────────────────────

function scoreHeat(score: number): string {
  if (score >= 78) return "var(--hot)";
  if (score >= 65) return "var(--warm)";
  if (score >= 50) return "var(--mid)";
  return "var(--cool)";
}

function timeAgo(isoString: string | null): string {
  if (!isoString) return "—";
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

function platformToSource(platform: string): SourceKey {
  if (platform === "google_trends") return "google";
  if (platform === "hackernews") return "hn";
  if (platform === "reddit") return "reddit";
  if (platform === "youtube") return "youtube";
  return "google";
}

function buildMeta(item: SocialPulseItem): string {
  const p = item.platform;
  if (p === "reddit") {
    const match = item.description?.match(/r\/\w+/);
    if (match) return match[0];
    return item.tags?.find(t => t.startsWith("r/")) || item.category || "Reddit";
  }
  if (p === "hackernews") {
    const rank = item.metrics?.rank;
    return rank ? `HN #${rank}` : "Hacker News";
  }
  if (p === "google_trends") {
    return `Google Trends · ${item.region || "US"}`;
  }
  if (p === "youtube") {
    return item.tags?.[0] || "YouTube";
  }
  return item.category || p || "";
}

function buildStats(item: SocialPulseItem): string {
  const m = item.metrics || {};
  const parts: string[] = [];
  if (m.score) parts.push(`${m.score} pts`);
  if (m.views) parts.push(`${formatNum(m.views)} views`);
  if (m.likes) parts.push(`${formatNum(m.likes)} ↑`);
  if (m.comments) parts.push(`${formatNum(m.comments)} 💬`);
  return parts.join(" · ") || item.category || "";
}

function formatNum(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function mapItem(item: SocialPulseItem, niches: PulseNiche[]): TermTrend {
  const niche = niches.find(n => n.id === item.niche_id);
  return {
    id: item.id,
    source: platformToSource(item.platform),
    niche: niche?.name || item.category || "General",
    nicheId: item.niche_id,
    score: Math.round(item.virality_score),
    title: item.title,
    meta: buildMeta(item),
    stats: buildStats(item),
    age: timeAgo(item.fetched_at),
    url: item.url,
    sentiment: item.sentiment || "neutral",
  };
}

// ── Sparkline ──────────────────────────────────────────────────────────────────

function mulberry32(a: number) {
  return function () {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function trendHistory(trend: TermTrend): number[] {
  const seed = trend.id.split("").reduce((a, c) => a + c.charCodeAt(0), 17) | 0;
  const rng = mulberry32(seed);
  const N = 14;
  const pts: number[] = [];
  let v = Math.max(15, trend.score - 30 + (rng() * 20 - 10));
  for (let i = 0; i < N - 1; i++) {
    const target = v + (trend.score - v) * (i / (N - 2)) * 0.65;
    v = target + (rng() - 0.5) * 18;
    pts.push(Math.max(0, Math.min(100, v)));
  }
  pts.push(trend.score);
  return pts;
}

function Sparkline({ points, color, width = 60, height = 22 }: { points: number[]; color: string; width?: number; height?: number }) {
  if (!points || points.length === 0) return null;
  const xy = (v: number, i: number): [number, number] => [
    (i / (points.length - 1)) * width,
    height - ((v / 100) * (height - 2)) - 1,
  ];
  const line = points.map((v, i) => {
    const [x, y] = xy(v, i);
    return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const [lastX, lastY] = xy(points[points.length - 1], points.length - 1);
  const [firstX] = xy(points[0], 0);
  const area =
    `M ${firstX} ${height} ` +
    points.map((v, i) => { const [x, y] = xy(v, i); return `L ${x.toFixed(1)} ${y.toFixed(1)}`; }).join(" ") +
    ` L ${lastX} ${height} Z`;
  return (
    <svg width={width} height={height} style={{ display: "block" }} aria-hidden>
      <path d={area} fill={color} fillOpacity={0.14} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.25" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lastX} cy={lastY} r="1.75" fill={color} />
    </svg>
  );
}

// ── ScoreBar ───────────────────────────────────────────────────────────────────

function ScoreBar({ score, width = 110 }: { score: number; width?: number }) {
  const pct = Math.max(6, Math.min(100, score));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ width, height: 8, background: "var(--track)", borderRadius: 2, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, width: pct + "%", background: scoreHeat(score) }} />
        <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(90deg, transparent calc(50% - 0.5px), rgba(0,0,0,.18) calc(50% - 0.5px), rgba(0,0,0,.18) calc(50% + 0.5px), transparent calc(50% + 0.5px)), linear-gradient(90deg, transparent calc(78% - 0.5px), rgba(0,0,0,.18) calc(78% - 0.5px), rgba(0,0,0,.18) calc(78% + 0.5px), transparent calc(78% + 0.5px))" }} />
      </div>
      <span style={{ fontVariantNumeric: "tabular-nums", fontSize: 11, fontWeight: 600, color: "var(--ink)" }}>{score}</span>
    </div>
  );
}

// ── SourceTag ──────────────────────────────────────────────────────────────────

function SourceTag({ src, dim = false }: { src: SourceKey; dim?: boolean }) {
  const s = SOURCES[src];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 6px", border: "1px solid var(--rule)", borderRadius: 4, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase", color: dim ? "var(--mute)" : `var(--src-${src})`, background: "var(--soft)" }}>
      <span aria-hidden style={{ fontSize: 9 }}>{s.glyph}</span>{s.short}
    </span>
  );
}

// ── Stat ───────────────────────────────────────────────────────────────────────

function Stat({ n, label, hot, mute }: { n: number | string; label: string; hot?: boolean; mute?: boolean }) {
  return (
    <span style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
      <span style={{ fontSize: 18, fontWeight: 600, fontVariantNumeric: "tabular-nums", color: hot ? "var(--accent)" : mute ? "var(--mute)" : "var(--ink)" }}>{n}</span>
      <span style={{ fontSize: 11, color: "var(--mute)" }}>{label}</span>
    </span>
  );
}

// ── Panel ──────────────────────────────────────────────────────────────────────

function Panel({ title, hint, action, onAction, children }: {
  title: string; hint?: string; action?: string; onAction?: () => void; children: React.ReactNode;
}) {
  return (
    <section style={{ marginBottom: 14 }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, fontSize: 11, fontWeight: 600, color: "var(--ink)", paddingBottom: 6, borderBottom: "1px solid var(--rule)", marginBottom: 6 }}>
        <span>{title}</span>
        {hint && <span style={{ color: "var(--mute)", fontWeight: 400 }}>{hint}</span>}
        {action && (
          <button onClick={onAction} style={{ ...S.btn, padding: "2px 6px", fontSize: 10, cursor: "pointer" }}>
            ⟲ {action}
          </button>
        )}
      </header>
      <div>{children}</div>
    </section>
  );
}

// ── CommandPalette ─────────────────────────────────────────────────────────────

interface Command {
  group: string;
  icon?: string;
  label: string;
  hint?: string;
  shortcut?: string;
  run: () => void;
}

function CommandPalette({ open, onClose, commands }: { open: boolean; onClose: () => void; commands: Command[] }) {
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) { setQ(""); setIdx(0); setTimeout(() => inputRef.current?.focus(), 10); }
  }, [open]);

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return commands;
    return commands.filter(c => (c.label + " " + (c.hint || "") + " " + (c.group || "")).toLowerCase().includes(t));
  }, [q, commands]);

  useEffect(() => { if (idx >= filtered.length) setIdx(0); }, [filtered.length, idx]);

  if (!open) return null;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx(i => Math.min(filtered.length - 1, i + 1)); return; }
    if (e.key === "ArrowUp") { e.preventDefault(); setIdx(i => Math.max(0, i - 1)); return; }
    if (e.key === "Enter") { e.preventDefault(); const c = filtered[idx]; if (c) { c.run(); onClose(); } return; }
  };

  const groups: Record<string, { c: Command; i: number }[]> = {};
  filtered.forEach((c, i) => {
    const g = c.group || "Actions";
    if (!groups[g]) groups[g] = [];
    groups[g].push({ c, i });
  });

  return (
    <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(9,9,11,.42)", backdropFilter: "blur(2px)", display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: "11vh", zIndex: 50 }}>
      <div onClick={e => e.stopPropagation()} onKeyDown={onKey} style={{ width: 540, background: "var(--paper-2)", border: "1px solid var(--rule)", borderRadius: 12, boxShadow: "0 24px 60px -12px rgba(0,0,0,.35), 0 0 0 1px rgba(255,255,255,.04)", overflow: "hidden", fontFamily: "var(--mono)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "12px 14px", borderBottom: "1px solid var(--rule)" }}>
          <span style={{ color: "var(--mute)", fontSize: 14 }}>⌘</span>
          <input
            ref={inputRef} value={q} onChange={e => { setQ(e.target.value); setIdx(0); }}
            placeholder="Type a command, niche, source, or trend…"
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", color: "var(--ink)", fontFamily: "var(--mono)", fontSize: 14, padding: 0 }}
          />
          <span style={{ fontSize: 10, color: "var(--mute)" }}>esc</span>
        </div>
        <div style={{ maxHeight: 380, overflow: "auto", padding: "6px 0" }}>
          {Object.keys(groups).map(g => (
            <div key={g}>
              <div style={{ padding: "8px 14px 4px", fontSize: 10, color: "var(--mute)", fontWeight: 500, letterSpacing: ".04em" }}>{g}</div>
              {groups[g].map(({ c, i }) => (
                <div key={i} onMouseEnter={() => setIdx(i)} onClick={() => { c.run(); onClose(); }}
                  style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px", cursor: "pointer", background: idx === i ? "rgba(239,68,68,.08)" : "transparent", borderLeft: idx === i ? "2px solid var(--accent)" : "2px solid transparent" }}>
                  <span style={{ width: 16, color: idx === i ? "var(--accent)" : "var(--mute)", fontSize: 13 }}>{c.icon || "›"}</span>
                  <span style={{ flex: 1, fontSize: 13, color: "var(--ink)" }}>{c.label}</span>
                  {c.hint && <span style={{ fontSize: 11, color: "var(--mute)" }}>{c.hint}</span>}
                  {c.shortcut && <kbd style={S.kbd}>{c.shortcut}</kbd>}
                </div>
              ))}
            </div>
          ))}
          {filtered.length === 0 && <div style={{ padding: "18px 14px", color: "var(--mute)", fontSize: 12 }}>No commands match &quot;{q}&quot;</div>}
        </div>
        <div style={{ display: "flex", gap: 14, padding: "8px 14px", borderTop: "1px solid var(--rule)", background: "var(--soft)", fontSize: 10.5, color: "var(--mute)" }}>
          <span><kbd style={S.kbd}>↑↓</kbd> navigate</span>
          <span><kbd style={S.kbd}>↵</kbd> select</span>
          <span><kbd style={S.kbd}>esc</kbd> close</span>
          <span style={{ marginLeft: "auto" }}>{filtered.length} result{filtered.length === 1 ? "" : "s"}</span>
        </div>
      </div>
    </div>
  );
}

// ── HelpModal ──────────────────────────────────────────────────────────────────

function HelpModal({ onClose }: { onClose: () => void }) {
  const shortcuts = [
    ["j / ↓", "Next row"], ["k / ↑", "Previous row"],
    ["g", "Jump to top"], ["Shift+G", "Jump to bottom"],
    ["q", "Queue / unqueue"], ["d", "Draft in your voice"],
    ["o / ↵", "Open source"], ["/", "Focus keyword input"],
    ["⌘K", "Command palette"], ["?", "Toggle this help"],
    ["r", "Refresh sources"], ["esc", "Close overlay"],
  ];
  return (
    <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(9,9,11,.42)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 40 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: "var(--paper-2)", border: "1px solid var(--rule)", borderRadius: 12, padding: 22, width: 480, boxShadow: "0 24px 60px -12px rgba(0,0,0,.35)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>Keyboard shortcuts</span>
          <button onClick={onClose} style={S.act}>esc</button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 24px", fontSize: 12 }}>
          {shortcuts.map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px dashed var(--rule)", paddingBottom: 6 }}>
              <kbd style={S.kbd}>{k}</kbd>
              <span style={{ color: "var(--mute)" }}>{v}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Style constants ────────────────────────────────────────────────────────────

const S = {
  btn: { background: "transparent", border: "1px solid var(--rule)", color: "var(--ink)", fontFamily: "var(--mono)", fontSize: 11, padding: "4px 8px", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4, borderRadius: 6 } as React.CSSProperties,
  act: { background: "transparent", border: "1px solid var(--rule)", color: "var(--ink)", fontFamily: "var(--mono)", fontSize: 10.5, padding: "2px 6px", cursor: "pointer", borderRadius: 4 } as React.CSSProperties,
  kbd: { background: "var(--track)", border: "1px solid var(--rule)", borderBottomWidth: 2, padding: "0 5px", borderRadius: 3, fontSize: 10, fontFamily: "var(--code)", color: "var(--ink)" } as React.CSSProperties,
  input: { background: "transparent", border: "1px solid var(--rule)", color: "var(--ink)", fontFamily: "var(--mono)", fontSize: 11, padding: "4px 8px", width: 140, outline: "none", borderRadius: 6 } as React.CSSProperties,
  select: { background: "transparent", border: "1px solid var(--rule)", color: "var(--ink)", fontFamily: "var(--mono)", fontSize: 11, padding: "4px 6px", borderRadius: 6 } as React.CSSProperties,
  cmdBtn: { background: "var(--soft)", border: "1px solid var(--rule)", color: "var(--ink)", fontFamily: "var(--mono)", fontSize: 11, padding: "4px 8px", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 8, borderRadius: 6, minWidth: 180, justifyContent: "space-between" } as React.CSSProperties,
  srcBtn: { background: "transparent", border: "1px solid var(--rule)", fontFamily: "var(--mono)", fontSize: 11, padding: "3px 8px", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6, borderRadius: 6 } as React.CSSProperties,
  chip: { background: "transparent", border: "1px solid var(--rule)", color: "var(--ink)", fontFamily: "var(--mono)", fontSize: 10.5, padding: "3px 7px", cursor: "pointer", textTransform: "lowercase" as const, letterSpacing: ".02em", borderRadius: 6 } as React.CSSProperties,
};

// ── CSS tokens (injected once) ─────────────────────────────────────────────────

const TOKEN_STYLE = `
  .sp-terminal {
    --paper:   #fafafa;
    --paper-2: #ffffff;
    --soft:    #f4f4f5;
    --track:   #e4e4e7;
    --rule:    #e4e4e7;
    --ink:     #09090b;
    --mute:    #71717a;
    --accent:  #ef4444;
    --hot:     #ef4444;
    --warm:    #f97316;
    --mid:     #eab308;
    --cool:    #84cc16;
    --src-google:  #3b82f6;
    --src-youtube: #ef4444;
    --src-reddit:  #f97316;
    --src-hn:      #f59e0b;
    --mono: 'Geist', ui-sans-serif, system-ui, -apple-system, sans-serif;
    --code: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  .sp-terminal button { all: unset; box-sizing: border-box; }
  .sp-terminal select { box-sizing: border-box; appearance: auto; }
  .sp-terminal textarea { box-sizing: border-box; }
  .sp-terminal * { box-sizing: border-box; }
`;

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function SocialPulsePage() {
  const [trends, setTrends] = useState<TermTrend[]>([]);
  const [themes, setThemes] = useState<SocialPulseTheme[]>([]);
  const [loadingThemes, setLoadingThemes] = useState(false);
  const [sourceCounts, setSourceCounts] = useState<Record<SourceKey, number>>({ google: 0, youtube: 0, reddit: 0, hn: 0 });
  const [brokenSources, setBrokenSources] = useState<Set<SourceKey>>(new Set());
  const [totalTracking, setTotalTracking] = useState(0);
  const [viralCount, setViralCount] = useState(0);
  const [keywordCount, setKeywordCount] = useState(0);
  const [trackedKeywords, setTrackedKeywords] = useState<{ id: string; keyword: string }[]>([]);
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [region, setRegion] = useState("US");

  const [niche, setNiche] = useState("All Niches");
  const [activeSources, setActiveSources] = useState<Set<SourceKey>>(new Set(SOURCE_KEYS));
  const [queued, setQueued] = useState<Set<string>>(() => {
    if (typeof window === "undefined") return new Set();
    try { return new Set(JSON.parse(localStorage.getItem("sp_queued") || "[]")); } catch { return new Set(); }
  });
  const [focusIdx, setFocusIdx] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [draftContent, setDraftContent] = useState("");
  const [generatingDraft, setGeneratingDraft] = useState(false);
  const [availableModels, setAvailableModels] = useState<{ provider: string; model: string; label: string }[]>([]);
  const [selectedModelKey, setSelectedModelKey] = useState("");
  const [minScore, setMinScore] = useState(60);

  const feedRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // ── Derived ──────────────────────────────────────────────────────────────────

  const nicheNames = useMemo(() => {
    const names = new Set<string>();
    trends.forEach(t => { if (t.niche) names.add(t.niche); });
    return ["All Niches", ...Array.from(names).sort()];
  }, [trends]);

  const filtered = useMemo(() => {
    return trends
      .filter(t => activeSources.has(t.source) && t.score >= minScore && (niche === "All Niches" || t.niche === niche))
      .sort((a, b) => b.score - a.score);
  }, [trends, activeSources, niche, minScore]);

  const heatmap = useMemo(() => {
    const buckets = new Array(20).fill(0);
    trends.forEach(t => { const i = Math.min(19, Math.floor(t.score / 5)); buckets[i]++; });
    const max = Math.max(...buckets, 1);
    return buckets.map(b => b / max);
  }, [trends]);

  const sources = useMemo(() => {
    const s: Record<string, SourceMeta> = {};
    SOURCE_KEYS.forEach(k => { s[k] = { ...SOURCES[k], count: sourceCounts[k] }; });
    return s as Record<SourceKey, SourceMeta>;
  }, [sourceCounts]);

  // ── Persist queued ───────────────────────────────────────────────────────────

  useEffect(() => {
    localStorage.setItem("sp_queued", JSON.stringify([...queued]));
  }, [queued]);

  // ── Load data ────────────────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [dash, nicheList, statusMap, modelList, kwList] = await Promise.all([
        socialPulseApi.dashboard(),
        socialPulseApi.niches.list().catch(() => [] as PulseNiche[]),
        socialPulseApi.status().catch(() => ({} as Record<string, { ok: boolean }>)),
        loadModelOptions(),
        socialPulseApi.keywords.list().catch(() => [] as { id: string; keyword: string }[]),
      ]);

      if (modelList.length > 0) {
        setAvailableModels(modelList);
        setSelectedModelKey(prev => prev || `${modelList[0].provider}::${modelList[0].model}`);
      }

      // Detect broken sources from status response
      const broken = new Set<SourceKey>();
      Object.entries(statusMap).forEach(([platform, s]) => {
        if (!s.ok) broken.add(platformToSource(platform));
      });
      setBrokenSources(broken);

      setTotalTracking(dash.total_trending);
      setViralCount(dash.viral_count);
      setKeywordCount(dash.keyword_count);
      setLastSync(dash.last_refreshed);
      setTrackedKeywords(kwList);

      // by_platform items lack platform/metrics/tags — inject platform from the map key
      const seenIds = new Set<string>();
      const allItems: SocialPulseItem[] = [];

      Object.entries(dash.by_platform).forEach(([platform, items]) => {
        items.forEach(item => {
          if (!seenIds.has(item.id)) {
            seenIds.add(item.id);
            allItems.push({ ...item, platform } as SocialPulseItem);
          }
        });
      });
      // top_viral has full fields — add any not already included
      dash.top_viral.forEach(item => {
        if (!seenIds.has(item.id)) {
          seenIds.add(item.id);
          allItems.push(item);
        }
      });

      const counts: Record<SourceKey, number> = { google: 0, youtube: 0, reddit: 0, hn: 0 };
      allItems.forEach(item => {
        const key = platformToSource(item.platform);
        counts[key] = (counts[key] || 0) + 1;
      });

      setSourceCounts(counts);
      setTrends(allItems.map(item => mapItem(item, nicheList)));
    } catch (err) {
      console.error("Social pulse load failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Refresh: ingest from external sources, then reload DB ────────────────────

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await socialPulseApi.refresh(region);
      // Give backend a moment to ingest, then reload
      setTimeout(() => loadData(), 2000);
    } catch (err) {
      console.error("Refresh failed:", err);
      loadData();
    } finally {
      setRefreshing(false);
    }
  }, [region, loadData]);

  useEffect(() => { loadData(); }, [loadData]);

  // ── Add tracked keyword ───────────────────────────────────────────────────────

  const [addingKeyword, setAddingKeyword] = useState(false);

  const handleAddKeyword = useCallback(async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter") return;
    const input = e.currentTarget;
    const kw = input.value.trim().replace(/^#+\s*/, "");
    if (!kw || addingKeyword) return;
    setAddingKeyword(true);
    try {
      const added = await socialPulseApi.keywords.add(kw);
      setKeywordCount(c => c + 1);
      setTrackedKeywords(prev => [...prev, { id: added.id, keyword: added.keyword }]);
      input.value = "";
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Failed to add keyword: ${msg}`);
    } finally {
      setAddingKeyword(false);
    }
  }, [addingKeyword]);

  const removeKeyword = useCallback(async (id: string) => {
    try {
      await socialPulseApi.keywords.delete(id);
      setTrackedKeywords(prev => prev.filter(k => k.id !== id));
      setKeywordCount(c => Math.max(0, c - 1));
    } catch (err) {
      console.error("Failed to remove keyword:", err);
    }
  }, []);

  // ── Generate AI draft for focused trend ─────────────────────────────────────

  const generateDraft = useCallback(async () => {
    const t = filtered[focusIdx];
    if (!t || !selectedModelKey || generatingDraft) return;
    const [provider, model] = selectedModelKey.split("::");
    setGeneratingDraft(true);
    try {
      const queuedTitles = [...queued].map(id => trends.find(x => x.id === id)?.title).filter(Boolean) as string[];
      const result = await socialPulseApi.insights({
        provider,
        model,
        queued_titles: queuedTitles,
      });
      setDraftContent(result.insights || "No insights generated.");
    } catch (err) {
      console.error("Draft generation failed:", err);
      setDraftContent("Failed to generate draft. Check your LLM configuration.");
    } finally {
      setGeneratingDraft(false);
    }
  }, [filtered, focusIdx, selectedModelKey, generatingDraft, queued, trends]);

  // ── Generate themes via LLM ──────────────────────────────────────────────────

  const generateThemes = useCallback(async () => {
    if (loadingThemes) return;
    const modelKey = selectedModelKey || (availableModels[0] ? `${availableModels[0].provider}::${availableModels[0].model}` : "");
    if (!modelKey) {
      alert("No LLM configured. Add a provider in Settings first.");
      return;
    }
    const [provider, model] = modelKey.split("::");
    setLoadingThemes(true);
    try {
      const result = await socialPulseApi.themes({ provider, model });
      setThemes(result);
    } catch (err) {
      console.error("Theme generation failed:", err);
    } finally {
      setLoadingThemes(false);
    }
  }, [selectedModelKey, availableModels, loadingThemes]);

  // ── Inject CSS tokens, clean up on unmount to prevent leaking to other pages ─

  useEffect(() => {
    const style = document.createElement("style");
    style.setAttribute("data-id", "sp-terminal-tokens");
    style.textContent = TOKEN_STYLE;
    document.head.appendChild(style);
    return () => { document.head.removeChild(style); };
  }, []);

  // ── Reload models when tab regains focus (e.g. returning from Settings) ─────

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        loadModelOptions().then(list => {
          if (list.length > 0) {
            setAvailableModels(list);
            setSelectedModelKey(prev => prev || `${list[0].provider}::${list[0].model}`);
          }
        }).catch(() => {});
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  // ── Keep focusIdx in range ───────────────────────────────────────────────────

  useEffect(() => {
    if (focusIdx >= filtered.length) setFocusIdx(Math.max(0, filtered.length - 1));
  }, [filtered.length]);

  // ── Auto-scroll focused row ──────────────────────────────────────────────────

  useEffect(() => {
    const feed = feedRef.current; if (!feed) return;
    const row = feed.querySelector(`[data-row="${focusIdx}"]`) as HTMLElement | null;
    if (!row) return;
    const r = row.getBoundingClientRect(); const f = feed.getBoundingClientRect();
    if (r.top < f.top + 40) feed.scrollTop -= (f.top + 40 - r.top);
    else if (r.bottom > f.bottom - 12) feed.scrollTop += (r.bottom - (f.bottom - 12));
  }, [focusIdx]);

  // ── Update draft when focused trend changes ──────────────────────────────────

  useEffect(() => {
    const t = filtered[focusIdx];
    if (t) {
      setDraftContent(`> ${t.title}\n\nTrending on ${sources[t.source].label}${t.meta ? ` · ${t.meta}` : ""}.\n\nDraft your take here…`);
    }
  }, [focusIdx, filtered]);

  // ── Actions ──────────────────────────────────────────────────────────────────

  const toggleSource = useCallback((k: SourceKey) => {
    setActiveSources(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n; });
  }, []);

  const toggleQueue = useCallback((id: string) => {
    setQueued(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }, []);

  // ── Global keyboard handler ──────────────────────────────────────────────────

  useEffect(() => {
    const isTyping = (el: Element | null) =>
      el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || (el as HTMLElement).isContentEditable);

    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); setPaletteOpen(o => !o); return;
      }
      if (paletteOpen) return;
      if (isTyping(document.activeElement)) return;

      const t = filtered[focusIdx];
      switch (e.key) {
        case "j": case "ArrowDown": e.preventDefault(); setFocusIdx(i => Math.min(filtered.length - 1, i + 1)); break;
        case "k": case "ArrowUp":   e.preventDefault(); setFocusIdx(i => Math.max(0, i - 1)); break;
        case "g": e.preventDefault(); setFocusIdx(0); break;
        case "G": e.preventDefault(); setFocusIdx(filtered.length - 1); break;
        case "q": if (t) { e.preventDefault(); toggleQueue(t.id); } break;
        case "d": if (t) { e.preventDefault(); /* focus right rail */ } break;
        case "Enter": case "o": if (t?.url) { e.preventDefault(); window.open(t.url, "_blank"); } break;
        case "/": e.preventDefault(); searchRef.current?.focus(); break;
        case "?": e.preventDefault(); setShowHelp(s => !s); break;
        case "r": if (!e.metaKey && !e.ctrlKey) { e.preventDefault(); handleRefresh(); } break;
        case "Escape": setShowHelp(false); setPaletteOpen(false); break;
        default: break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [filtered, focusIdx, paletteOpen, queued, toggleQueue, loadData, handleRefresh]);

  // ── Command palette commands ─────────────────────────────────────────────────

  const commands = useMemo((): Command[] => {
    const cmds: Command[] = [
      { group: "Actions", icon: "⟲", label: "Refresh all sources", shortcut: "R", run: handleRefresh },
      { group: "Actions", icon: "#", label: "Add tracked keyword…", shortcut: "/", run: () => searchRef.current?.focus() },
      { group: "Actions", icon: "?", label: "Toggle keyboard shortcuts", shortcut: "?", run: () => setShowHelp(s => !s) },
    ];
    SOURCE_KEYS.forEach(k => {
      const on = activeSources.has(k);
      cmds.push({ group: "Sources", icon: on ? "◉" : "○", label: `${on ? "Hide" : "Show"} ${sources[k].label}`, hint: `${sources[k].count} items`, run: () => toggleSource(k) });
    });
    nicheNames.forEach(n => {
      cmds.push({ group: "Filter by niche", icon: "◇", label: n, hint: niche === n ? "active" : "", run: () => setNiche(n) });
    });
    filtered.slice(0, 12).forEach((t, i) => {
      cmds.push({ group: "Jump to trend", icon: "›", label: t.title.length > 64 ? t.title.slice(0, 62) + "…" : t.title, hint: `${sources[t.source].short} · ${t.score}`, run: () => setFocusIdx(i) });
    });
    return cmds;
  }, [activeSources, niche, nicheNames, filtered, sources, handleRefresh, toggleSource]);

  // ── Sync timestamp ───────────────────────────────────────────────────────────

  const syncLabel = useMemo(() => {
    if (!lastSync) return "—";
    const d = new Date(lastSync);
    return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }) + " UTC";
  }, [lastSync]);

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="sp-terminal" style={{ width: "100%", height: "100%", background: "var(--paper)", color: "var(--ink)", fontFamily: "var(--mono)", display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>

        {/* ── Header bar ─────────────────────────────────────────────────────── */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 16px", borderBottom: "1px solid var(--rule)", gap: 16, flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#22c55e", boxShadow: "0 0 0 2px rgba(34,197,94,.18)", flexShrink: 0 }} />
              <span style={{ fontWeight: 700, fontSize: 14, letterSpacing: "-.02em" }}>Social Pulse</span>
              <span style={{ fontSize: 12, color: "var(--mute)" }}>Mission Control</span>
            </div>
            <span style={{ width: 1, height: 14, background: "var(--rule)", flexShrink: 0 }} />
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--mute)" }}>
              <span>last sync</span>
              <span style={{ color: "var(--ink)", fontFamily: "var(--code)", fontVariantNumeric: "tabular-nums" }}>{syncLabel}</span>
              {!loading && <span style={{ color: "#22c55e" }}>● live</span>}
              {loading && <span style={{ color: "var(--mute)" }}>● syncing…</span>}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 18, fontSize: 11 }}>
            <Stat n={totalTracking} label="tracking" />
            <Stat n={viralCount} label="viral · score>70" hot />
            <Stat n={nicheNames.length - 1} label="niches active" />
            <Stat n={keywordCount} label="keywords" mute />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button onClick={() => setPaletteOpen(true)} style={S.cmdBtn}>
              <span style={{ color: "var(--mute)" }}>Search or run…</span>
              <kbd style={S.kbd}>⌘K</kbd>
            </button>
            <input ref={searchRef} placeholder="# add keyword… ↵" style={{ ...S.input, opacity: addingKeyword ? 0.5 : 1 }} onKeyDown={handleAddKeyword} disabled={addingKeyword} />
            <select
              value={region} onChange={e => setRegion(e.target.value)}
              style={S.select}
            >
              <option>US</option><option>GB</option><option>IN</option>
            </select>
            <button onClick={handleRefresh} style={S.btn} disabled={loading || refreshing}>
              ⟲ {refreshing ? "fetching…" : loading ? "loading…" : "refresh"}
            </button>
          </div>
        </div>

        {/* ── Filter bar ─────────────────────────────────────────────────────── */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 16px", borderBottom: "1px solid var(--rule)", gap: 12, fontSize: 11, flexShrink: 0, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 500, color: "var(--mute)" }}>Sources</span>
            {SOURCE_KEYS.map(k => {
              const s = sources[k]; const on = activeSources.has(k); const broken = brokenSources.has(k);
              return (
                <button key={k} onClick={() => toggleSource(k)} style={{ ...S.srcBtn, opacity: on ? 1 : 0.45, borderColor: on ? `var(--src-${k})` : "var(--rule)", color: on ? `var(--src-${k})` : "var(--mute)" }}>
                  <span aria-hidden>{s.glyph}</span>
                  <span>{s.label}</span>
                  <span style={{ color: "var(--mute)", fontVariantNumeric: "tabular-nums" }}>{s.count}</span>
                  {broken && <span style={{ color: "var(--accent)", fontSize: 9 }}>✕ KEY</span>}
                </button>
              );
            })}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
            {nicheNames.map(n => (
              <button key={n} onClick={() => setNiche(n)} style={{ ...S.chip, background: niche === n ? "var(--ink)" : "transparent", color: niche === n ? "var(--paper)" : "var(--ink)", borderColor: niche === n ? "var(--ink)" : "var(--rule)" }}>
                {n.toLowerCase()}
              </button>
            ))}
          </div>

          {/* Min score filter */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 500, color: "var(--mute)" }}>min score</span>
            {[0, 50, 60, 70, 80].map(s => (
              <button key={s} onClick={() => setMinScore(s)} style={{ ...S.chip, background: minScore === s ? "var(--ink)" : "transparent", color: minScore === s ? "var(--paper)" : "var(--ink)", borderColor: minScore === s ? "var(--ink)" : "var(--rule)", cursor: "pointer" }}>
                {s === 0 ? "all" : s + "+"}
              </button>
            ))}
          </div>

          {/* Model selector — shared by Themes scan + Draft generate */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
            <span style={{ fontSize: 11, fontWeight: 500, color: "var(--mute)" }}>AI model</span>
            {availableModels.length > 0 ? (
              <select
                value={selectedModelKey}
                onChange={e => setSelectedModelKey(e.target.value)}
                style={{ ...S.select, fontSize: 10.5 }}
              >
                {availableModels.map(m => (
                  <option key={`${m.provider}::${m.model}`} value={`${m.provider}::${m.model}`}>
                    {m.label}
                  </option>
                ))}
              </select>
            ) : (
              <span style={{ fontSize: 10.5, color: "var(--mute)", fontStyle: "italic" }}>no models loaded</span>
            )}
            <button
              onClick={async () => {
                const list = await loadModelOptions();
                if (list.length > 0) {
                  setAvailableModels(list);
                  setSelectedModelKey(prev => prev || `${list[0].provider}::${list[0].model}`);
                }
              }}
              style={{ ...S.act, cursor: "pointer", fontSize: 10, padding: "2px 5px" }}
              title="Reload model list"
            >⟲</button>
          </div>
        </div>

        {/* ── Main grid ──────────────────────────────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 320px", flex: 1, minHeight: 0 }}>

          {/* Left rail */}
          <aside style={{ borderRight: "1px solid var(--rule)", overflow: "auto", padding: "10px 12px" }}>
            <Panel title="Platform mix" hint="last 24h">
              {SOURCE_KEYS.map(k => {
                const s = sources[k];
                const total = SOURCE_KEYS.reduce((a, kk) => a + sources[kk].count, 0);
                const pct = total ? s.count / total : 0;
                return (
                  <div key={k} style={{ display: "grid", gridTemplateColumns: "56px 1fr 28px", alignItems: "center", gap: 8, padding: "5px 0", fontSize: 11 }}>
                    <span style={{ color: `var(--src-${k})`, letterSpacing: ".06em" }}>{s.short}</span>
                    <div style={{ height: 6, background: "var(--track)", position: "relative", borderRadius: 2 }}>
                      <div style={{ position: "absolute", inset: 0, width: (pct * 100) + "%", background: `var(--src-${k})`, opacity: .7, borderRadius: 2 }} />
                    </div>
                    <span style={{ fontVariantNumeric: "tabular-nums", textAlign: "right", color: "var(--mute)" }}>{s.count}</span>
                  </div>
                );
              })}
            </Panel>

            <Panel title="Score distribution" hint="0 → 100">
              <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 56 }}>
                {heatmap.map((v, i) => (
                  <div key={i} style={{ flex: 1, height: Math.max(2, v * 54), background: scoreHeat(i * 5 + 5), opacity: 0.85, borderRadius: "1px 1px 0 0" }} />
                ))}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--mute)", marginTop: 4 }}>
                <span>0</span><span>50</span><span>viral ▸</span>
              </div>
            </Panel>

            <Panel
              title="Prominent themes"
              action={loadingThemes ? "scanning…" : "scan"}
              onAction={generateThemes}
            >
              {loadingThemes && (
                <div style={{ padding: "10px 0", fontSize: 10.5, color: "var(--mute)" }}>Clustering trends…</div>
              )}
              {!loadingThemes && themes.length > 0 && themes.map((th, i) => (
                <div key={i} style={{ borderTop: "1px dashed var(--rule)", padding: "8px 0" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
                    <span style={{ fontSize: 11, fontWeight: 600 }}>{th.theme}</span>
                    <span style={{ fontSize: 10, color: scoreHeat(th.virality_score), fontVariantNumeric: "tabular-nums" }}>{Math.round(th.virality_score)}</span>
                  </div>
                  <p style={{ fontSize: 10, color: "var(--mute)", margin: "3px 0 0", lineHeight: 1.4 }}>{th.description}</p>
                </div>
              ))}
              {!loadingThemes && themes.length === 0 && (
                <div style={{ padding: "10px 0", fontSize: 10.5, color: "var(--mute)", lineHeight: 1.5 }}>
                  {availableModels.length > 0
                    ? <>Click <span style={{ color: "var(--ink)" }}>⟲ scan</span> to cluster trends into cross-platform narratives.</>
                    : "Configure an LLM provider in Settings to generate themes."}
                </div>
              )}
            </Panel>

            <Panel title="Tracked keywords" hint={`${trackedKeywords.length}`}>
              {trackedKeywords.length === 0 && (
                <div style={{ padding: "10px 0", fontSize: 10.5, color: "var(--mute)", lineHeight: 1.5 }}>
                  Type a keyword in the top bar and press <span style={{ color: "var(--ink)" }}>↵</span> to track it.
                </div>
              )}
              {trackedKeywords.map(kw => (
                <div key={kw.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px dashed var(--rule)", padding: "5px 0", gap: 6 }}>
                  <span style={{ fontSize: 10.5, fontVariantNumeric: "tabular-nums", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}># {kw.keyword}</span>
                  <button
                    onClick={() => removeKeyword(kw.id)}
                    title="Remove keyword"
                    style={{ all: "unset", cursor: "pointer", fontSize: 10, color: "var(--mute)", flexShrink: 0, padding: "0 2px" }}
                  >✕</button>
                </div>
              ))}
            </Panel>
          </aside>

          {/* Center feed */}
          <main ref={feedRef} style={{ overflow: "auto", minHeight: 0 }} role="grid" aria-label="Trend feed">
            {/* Sticky column header */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", fontSize: 10.5, fontWeight: 500, color: "var(--mute)", borderBottom: "1px solid var(--rule)", position: "sticky", top: 0, background: "var(--paper)", zIndex: 1 }}>
              <span style={{ width: 130 }}>Score / heat</span>
              <span style={{ width: 90 }}>Trend (12h)</span>
              <span style={{ width: 78 }}>Source</span>
              <span style={{ width: 78 }}>Age</span>
              <span style={{ flex: 1 }}>Headline</span>
              <span style={{ width: 100 }}>Niche</span>
              <span style={{ width: 140, textAlign: "right" }}>Actions</span>
            </div>

            {loading && trends.length === 0 && (
              <div style={{ padding: "40px 14px", textAlign: "center", color: "var(--mute)", fontSize: 12 }}>
                Loading trends…
              </div>
            )}

            {!loading && filtered.length === 0 && (
              <div style={{ padding: "40px 14px", textAlign: "center", color: "var(--mute)", fontSize: 12 }}>
                No trends match this filter.
              </div>
            )}

            {filtered.map((t, i) => {
              const focused = i === focusIdx;
              const history = trendHistory(t);
              const delta = Math.round(history[history.length - 1] - history[0]);
              return (
                <div
                  key={t.id}
                  data-row={i}
                  role="row"
                  aria-selected={focused}
                  onClick={() => setFocusIdx(i)}
                  style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "9px 14px",
                    borderBottom: "1px solid var(--rule)", minHeight: 44, cursor: "pointer",
                    background: focused ? "rgba(239,68,68,.07)" : (i % 2 ? "transparent" : "rgba(0,0,0,.015)"),
                    boxShadow: focused ? "inset 2px 0 0 var(--accent)" : "none",
                    transition: "background .08s ease",
                  }}
                >
                  <div style={{ width: 130 }}><ScoreBar score={t.score} /></div>
                  <div style={{ width: 90, display: "flex", alignItems: "center", gap: 6 }}>
                    <Sparkline points={history} color={scoreHeat(t.score)} />
                    <span style={{ fontSize: 10, fontFamily: "var(--code)", color: delta >= 0 ? "#16a34a" : "#dc2626", fontVariantNumeric: "tabular-nums" }}>{delta >= 0 ? "+" : ""}{delta}</span>
                  </div>
                  <div style={{ width: 78 }}><SourceTag src={t.source} /></div>
                  <div style={{ width: 78, fontSize: 11, color: "var(--mute)", fontFamily: "var(--code)", fontVariantNumeric: "tabular-nums" }}>{t.age} ago</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 500, lineHeight: 1.35, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.title}</div>
                    <div style={{ fontSize: 10.5, color: "var(--mute)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.meta}{t.stats ? ` · ${t.stats}` : ""}</div>
                  </div>
                  <div style={{ width: 100, fontSize: 10, color: "var(--mute)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.niche.toLowerCase()}</div>
                  <div style={{ width: 140, display: "flex", gap: 4, justifyContent: "flex-end" }}>
                    {t.url && (
                      <button
                        onClick={e => { e.stopPropagation(); window.open(t.url!, "_blank"); }}
                        style={S.act} title="Open source (o)"
                      >↗</button>
                    )}
                    <button style={S.act} title="Draft in your voice (d)" onClick={e => { e.stopPropagation(); setFocusIdx(i); }}>✎ draft</button>
                    <button
                      onClick={e => { e.stopPropagation(); toggleQueue(t.id); }}
                      style={{ ...S.act, background: queued.has(t.id) ? "var(--ink)" : "transparent", color: queued.has(t.id) ? "var(--paper)" : "var(--ink)", borderColor: queued.has(t.id) ? "var(--ink)" : "var(--rule)" }}
                      title="Queue (q)"
                    >{queued.has(t.id) ? "✓ queued" : "+ queue"}</button>
                  </div>
                </div>
              );
            })}

            {/* Feed footer */}
            <div style={{ padding: "10px 14px", fontSize: 10.5, color: "var(--mute)", display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--rule)" }}>
              <span aria-live="polite">{filtered.length} of {trends.length} · row {Math.min(focusIdx + 1, filtered.length)}</span>
              <span style={{ display: "flex", gap: 8 }}>
                <span><kbd style={S.kbd}>j</kbd><kbd style={S.kbd}>k</kbd> nav</span>
                <span><kbd style={S.kbd}>q</kbd> queue</span>
                <span><kbd style={S.kbd}>d</kbd> draft</span>
                <span><kbd style={S.kbd}>/</kbd> search</span>
                <span><kbd style={S.kbd}>⌘K</kbd> commands</span>
                <span><kbd style={S.kbd}>?</kbd> help</span>
              </span>
            </div>
          </main>

          {/* Right rail */}
          <aside style={{ borderLeft: "1px solid var(--rule)", overflow: "auto", padding: "10px 12px", background: "rgba(0,0,0,.012)" }}>
            <Panel title="Content queue" hint={`${queued.size} topic${queued.size === 1 ? "" : "s"}`}>
              {[...queued].map(id => {
                const t = trends.find(x => x.id === id);
                if (!t) return null;
                return (
                  <div key={id} style={{ borderTop: "1px dashed var(--rule)", padding: "8px 0", display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <span style={{ fontSize: 10, color: scoreHeat(t.score), fontWeight: 600, fontVariantNumeric: "tabular-nums", minWidth: 18, fontFamily: "var(--code)" }}>{t.score}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 11.5, fontWeight: 500, lineHeight: 1.3, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" } as React.CSSProperties}>{t.title}</div>
                      <div style={{ fontSize: 10, color: "var(--mute)", marginTop: 2 }}><SourceTag src={t.source} dim /></div>
                    </div>
                    <button onClick={() => toggleQueue(id)} style={{ ...S.act, fontSize: 10 }}>✕</button>
                  </div>
                );
              })}
              {queued.size === 0 && (
                <div style={{ fontSize: 11, color: "var(--mute)", padding: "10px 0" }}>
                  nothing queued. press <kbd style={S.kbd}>q</kbd> on any row.
                </div>
              )}
            </Panel>

            <Panel title="Draft in your voice" hint={selectedModelKey ? selectedModelKey.split("::")[1]?.split("-").slice(0,2).join("-") : "no LLM"}>
              <textarea
                readOnly={generatingDraft}
                value={generatingDraft ? "Generating…" : draftContent}
                onChange={e => setDraftContent(e.target.value)}
                style={{ width: "100%", background: "var(--soft)", border: "1px solid var(--rule)", color: "var(--ink)", fontFamily: "var(--code)", fontSize: 11.5, padding: 10, resize: "none", height: 148, lineHeight: 1.5, outline: "none", borderRadius: 6, opacity: generatingDraft ? 0.6 : 1 }}
              />
              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <button
                  onClick={generateDraft}
                  disabled={generatingDraft || availableModels.length === 0 || filtered.length === 0}
                  style={{ ...S.btn, flex: 1, justifyContent: "center", opacity: (generatingDraft || availableModels.length === 0) ? 0.5 : 1 }}
                >
                  {generatingDraft ? "…generating" : "✎ regenerate"}
                </button>
                <button style={{ ...S.btn, background: "var(--ink)", color: "var(--paper)", borderColor: "var(--ink)" }}>↗ open editor</button>
              </div>
            </Panel>
          </aside>
        </div>

        {/* ── Help modal ─────────────────────────────────────────────────────── */}
        {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}

        {/* ── Command palette ─────────────────────────────────────────────────── */}
        <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
    </div>
  );
}
