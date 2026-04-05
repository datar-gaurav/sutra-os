"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useEffect, useRef, useCallback } from "react";
import {
    LayoutDashboard, Bot, MessageSquare, Settings, Activity, Zap, GitMerge,
    Menu, CalendarClock, Blocks, Brain, ScrollText, LogOut, KanbanSquare,
    MessagesSquare, ShieldCheck, Network, Target, DollarSign, BookOpen,
    Package, Mail, Webhook, BarChart3, ChevronDown, ChevronRight, Pencil, Sparkles, Link2, Hammer, TrendingUp,
    ExternalLink, HardDrive, Layers, Dna, Bell, FolderKanban, Gauge, ArrowUp, ArrowDown,
} from "lucide-react";
import { authStorage } from "@/lib/auth";
import { authApi, approvalsApi, alertsApi } from "@/lib/api";
import { wsClient } from "@/lib/ws";
import { DM_Sans } from "next/font/google";

const dmSans = DM_Sans({ subsets: ["latin"], weight: ["700", "900"] });

// ─── Nav structure ────────────────────────────────────────────────────────────

interface NavItem {
    href: string;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    openInNewWindow?: boolean;
}

interface NavGroup {
    id: string;
    defaultName: string;
    items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
    {
        id: "core",
        defaultName: "Home",
        items: [
            { href: "/", label: "Dashboard", icon: LayoutDashboard },
        ],
    },
    {
        id: "agents",
        defaultName: "Agents",
        items: [
            { href: "/analytics", label: "Analytics", icon: BarChart3 },
            { href: "/agents", label: "Agents", icon: Bot },
            { href: "/templates", label: "Templates", icon: Package },
            { href: "/skills", label: "Skills", icon: Sparkles },
            { href: "/chat", label: "Chat", icon: MessageSquare },
        ],
    },
    {
        id: "configuration",
        defaultName: "Configuration",
        items: [
            { href: "/settings", label: "APIs & Configurations", icon: Settings },
            { href: "/purposes", label: "LLM Purposes", icon: Layers },
            { href: "/email", label: "Email", icon: Mail },
            { href: "/google-drive", label: "Google Drive", icon: HardDrive },
            { href: "/integrations", label: "Integrations", icon: Link2 },
            { href: "/webhooks", label: "Webhooks", icon: Webhook },
            { href: "/rate-limits", label: "LLM Rate Limits", icon: Gauge },
        ],
    },
    {
        id: "automation",
        defaultName: "Automation",
        items: [
            { href: "/workflows", label: "Workflows", icon: GitMerge },
            { href: "/jobs", label: "Jobs", icon: CalendarClock },
            { href: "/batch-jobs", label: "Batch Jobs", icon: Layers },
            { href: "/triggers", label: "Triggers", icon: Zap },
            { href: "/mcp-servers", label: "MCP Servers", icon: Blocks },
        ],
    },
    {
        id: "collaboration",
        defaultName: "Collaboration",
        items: [
            { href: "/org", label: "Organization", icon: Network },
            { href: "/projects", label: "Projects", icon: FolderKanban },
            { href: "/goals", label: "Goals", icon: Target },
            { href: "/tasks", label: "Tasks", icon: KanbanSquare },
            { href: "/discussions", label: "Discussions", icon: MessagesSquare },
            { href: "/approvals", label: "Approvals", icon: ShieldCheck },
        ],
    },
    {
        id: "intelligence",
        defaultName: "Intelligence",
        items: [
            { href: "/social-pulse", label: "Social Pulse", icon: TrendingUp, openInNewWindow: true },
            { href: "/knowledge", label: "Knowledge", icon: BookOpen },
            { href: "/memory", label: "Memory", icon: Brain },
        ],
    },
    {
        id: "forge",
        defaultName: "Forge & Evolve",
        items: [
            { href: "/forge", label: "Forge", icon: Hammer },
            { href: "/evolve", label: "Evolve", icon: Dna },
        ],
    },
    {
        id: "monitoring",
        defaultName: "Monitoring",
        items: [
            { href: "/financials", label: "Financials", icon: DollarSign },
            { href: "/alerts", label: "Alerts", icon: Bell },
            { href: "/monitor", label: "Monitor", icon: Activity },
            { href: "/logs", label: "Logs", icon: ScrollText },
        ],
    },
];

const STORAGE_KEY = "sutra_sidebar_groups";
const NAV_ORDER_KEY = "sutra_sidebar_order";

interface GroupState {
    name: string;       // custom name
    collapsed: boolean;
}

function loadGroupState(): Record<string, GroupState> {
    if (typeof window === "undefined") return {};
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    } catch {
        return {};
    }
}

function saveGroupState(state: Record<string, GroupState>) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function loadNavOrder(): string[] | null {
    if (typeof window === "undefined") return null;
    try {
        const stored = localStorage.getItem(NAV_ORDER_KEY);
        return stored ? JSON.parse(stored) : null;
    } catch {
        return null;
    }
}

function saveNavOrder(order: string[]) {
    localStorage.setItem(NAV_ORDER_KEY, JSON.stringify(order));
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────

export function Sidebar() {
    const pathname = usePathname();
    const router = useRouter();
    const [isCollapsed, setIsCollapsed] = useState(false);
    const [pendingApprovals, setPendingApprovals] = useState(0);
    const [firingAlerts, setFiringAlerts] = useState(0);
    const [groupState, setGroupState] = useState<Record<string, GroupState>>({});
    const [navOrder, setNavOrder] = useState<string[]>([]);
    const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
    const [editingName, setEditingName] = useState("");
    const editRef = useRef<HTMLInputElement>(null);
    const user = authStorage.getUser();

    // Initialize navOrder on mount
    useEffect(() => {
        const storedOrder = loadNavOrder();
        if (storedOrder) {
            // Filter out any IDs that no longer exist, and add new IDs
            const currentIds = NAV_GROUPS.map(g => g.id);
            const filtered = storedOrder.filter(id => currentIds.includes(id));
            const newIds = currentIds.filter(id => !filtered.includes(id));
            setNavOrder([...filtered, ...newIds]);
        } else {
            setNavOrder(NAV_GROUPS.map(g => g.id));
        }
        setGroupState(loadGroupState());
    }, []);

    const orderedGroups = navOrder.length > 0 
        ? navOrder.map(id => NAV_GROUPS.find(g => g.id === id)!).filter(Boolean)
        : NAV_GROUPS;

    useEffect(() => {
        approvalsApi.pendingCount().then(d => setPendingApprovals(d.count)).catch(() => {});
        alertsApi.summary().then(d => setFiringAlerts(d.firing_count)).catch(() => {});
        const unsub = wsClient.on("approval_requested", () => setPendingApprovals(n => n + 1));
        const unsub2 = wsClient.on("approval_decided", () =>
            approvalsApi.pendingCount().then(d => setPendingApprovals(d.count)).catch(() => {})
        );
        const unsub3 = wsClient.on("alert_fired", () =>
            alertsApi.summary().then(d => setFiringAlerts(d.firing_count)).catch(() => {})
        );
        const unsub4 = wsClient.on("alert_resolved", () =>
            alertsApi.summary().then(d => setFiringAlerts(d.firing_count)).catch(() => {})
        );
        return () => { unsub(); unsub2(); unsub3(); unsub4(); };
    }, []);

    // Focus input when entering edit mode
    useEffect(() => {
        if (editingGroupId && editRef.current) {
            editRef.current.focus();
            editRef.current.select();
        }
    }, [editingGroupId]);

    function getGroupName(groupId: string, defaultName: string) {
        return groupState[groupId]?.name ?? defaultName;
    }

    function isGroupCollapsed(groupId: string) {
        return groupState[groupId]?.collapsed ?? false;
    }

    const toggleCollapse = useCallback((groupId: string, defaultName: string) => {
        setGroupState(prev => {
            const next = {
                ...prev,
                [groupId]: {
                    name: prev[groupId]?.name ?? defaultName,
                    collapsed: !(prev[groupId]?.collapsed ?? false),
                },
            };
            saveGroupState(next);
            return next;
        });
    }, []);

    function moveGroup(groupId: string, direction: 'up' | 'down') {
        setNavOrder(prev => {
            const index = prev.indexOf(groupId);
            if (index === -1) return prev;
            const newOrder = [...prev];
            if (direction === 'up' && index > 0) {
                [newOrder[index], newOrder[index - 1]] = [newOrder[index - 1], newOrder[index]];
            } else if (direction === 'down' && index < prev.length - 1) {
                [newOrder[index], newOrder[index + 1]] = [newOrder[index + 1], newOrder[index]];
            }
            saveNavOrder(newOrder);
            return newOrder;
        });
    }

    function startEditing(groupId: string, currentName: string) {
        setEditingGroupId(groupId);
        setEditingName(currentName);
    }

    function commitEdit(groupId: string, defaultName: string) {
        const trimmed = editingName.trim();
        setGroupState(prev => {
            const next = {
                ...prev,
                [groupId]: {
                    collapsed: prev[groupId]?.collapsed ?? false,
                    name: trimmed || defaultName,
                },
            };
            saveGroupState(next);
            return next;
        });
        setEditingGroupId(null);
    }

    function cancelEdit() {
        setEditingGroupId(null);
    }

    async function handleLogout() {
        const refreshToken = authStorage.getRefreshToken();
        if (refreshToken) {
            try { await authApi.logout(refreshToken); } catch { /* ignore */ }
        }
        authStorage.clear();
        router.replace("/login");
    }

    return (
        <aside className={`${isCollapsed ? "w-20" : "w-64"} transition-all duration-300 h-screen flex flex-col border-r border-stone-200/60 bg-[#FAF8F5] z-10`}>
            {/* Logo Header */}
            <div className={`p-4 flex items-center ${isCollapsed ? "justify-center" : "justify-between"}`}>
                {isCollapsed ? (
                    <button
                        onClick={() => setIsCollapsed(false)}
                        className="p-1 rounded-md hover:bg-stone-200 text-stone-500 transition-colors"
                    >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src="/logo.png" alt="Sutra" className="h-8 w-auto rounded" />
                    </button>
                ) : (
                    <>
                        <div className="flex items-center gap-1 min-w-0">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src="/logo.png" alt="Sutra" className="h-9 w-auto flex-shrink-0 rounded" />
                            <div className="flex items-center gap-2">
                                <span className={`text-[1.6rem] font-[800] text-[#1a1a1a] tracking-tight lowercase leading-none ${dmSans.className}`}>
                                    sutra<span className="text-[#9d5ae5]">.</span>
                                </span>
                                <span className="bg-[#9d5ae5]/15 text-[#5b21b6] text-[0.68rem] font-bold px-1.5 py-0.5 rounded-[4px] tracking-wide uppercase">
                                    BETA
                                </span>
                            </div>
                        </div>
                        <button
                            onClick={() => setIsCollapsed(true)}
                            className="p-2 rounded-md hover:bg-stone-200 text-stone-500 transition-colors flex-shrink-0"
                        >
                            <Menu className="w-5 h-5" />
                        </button>
                    </>
                )}
            </div>

            {/* Navigation */}
            <nav className="flex-1 px-2 py-2 overflow-y-auto custom-scrollbar space-y-0.5">
                {orderedGroups.map((group, index) => {
                    const collapsed = isGroupCollapsed(group.id);
                    const name = getGroupName(group.id, group.defaultName);
                    const isEditing = editingGroupId === group.id;
                    const hasActiveItem = group.items.some(
                        item => pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href))
                    );

                    return (
                        <div key={group.id}>
                            {/* Group header — hidden when sidebar is icon-only */}
                            {!isCollapsed && (
                                <div className="group/header flex items-center gap-1 px-2 pt-3 pb-1">
                                    {isEditing ? (
                                        <input
                                            ref={editRef}
                                            value={editingName}
                                            onChange={e => setEditingName(e.target.value)}
                                            onBlur={() => commitEdit(group.id, group.defaultName)}
                                            onKeyDown={e => {
                                                if (e.key === "Enter") commitEdit(group.id, group.defaultName);
                                                if (e.key === "Escape") cancelEdit();
                                            }}
                                            className="flex-1 text-[10px] font-bold uppercase tracking-widest text-stone-400 bg-transparent border-b border-brand-500 outline-none min-w-0 py-0"
                                        />
                                    ) : (
                                        <>
                                            <button
                                                onClick={() => toggleCollapse(group.id, group.defaultName)}
                                                className="flex items-center gap-1 flex-1 min-w-0 text-left"
                                                title={collapsed ? "Expand" : "Collapse"}
                                            >
                                                <span className={`text-[10px] font-bold uppercase tracking-widest truncate transition-colors ${hasActiveItem && collapsed ? "text-brand-600" : "text-stone-400 hover:text-stone-600"}`}>
                                                    {name}
                                                </span>
                                                {collapsed
                                                    ? <ChevronRight className="w-3 h-3 text-stone-300 flex-shrink-0" />
                                                    : <ChevronDown className="w-3 h-3 text-stone-300 flex-shrink-0" />
                                                }
                                            </button>
                                            <div className="flex opacity-0 group-hover/header:opacity-100 transition-all flex-shrink-0">
                                                <button
                                                    onClick={() => moveGroup(group.id, 'up')}
                                                    disabled={index === 0}
                                                    className="p-0.5 rounded text-stone-300 hover:text-stone-500 disabled:opacity-30 disabled:hover:text-stone-300"
                                                    title="Move Up"
                                                >
                                                    <ArrowUp className="w-2.5 h-2.5" />
                                                </button>
                                                <button
                                                    onClick={() => moveGroup(group.id, 'down')}
                                                    disabled={index === orderedGroups.length - 1}
                                                    className="p-0.5 rounded text-stone-300 hover:text-stone-500 disabled:opacity-30 disabled:hover:text-stone-300"
                                                    title="Move Down"
                                                >
                                                    <ArrowDown className="w-2.5 h-2.5" />
                                                </button>
                                                <button
                                                    onClick={() => startEditing(group.id, name)}
                                                    className="p-0.5 rounded text-stone-300 hover:text-stone-500 transition-all"
                                                    title="Rename section"
                                                >
                                                    <Pencil className="w-2.5 h-2.5" />
                                                </button>
                                            </div>
                                        </>
                                    )}
                                </div>
                            )}

                            {/* Items — hidden when group is collapsed (unless sidebar is icon-only) */}
                            {(!collapsed || isCollapsed) && (
                                <div className={isCollapsed ? "space-y-0.5 pb-2" : "space-y-0.5"}>
                                    {group.items.map((item) => {
                                        const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
                                        const badge = item.href === "/approvals" && pendingApprovals > 0
                                            ? pendingApprovals
                                            : item.href === "/alerts" && firingAlerts > 0
                                                ? firingAlerts
                                                : 0;

                                        // Items that open in a new window
                                        if (item.openInNewWindow) {
                                            return (
                                                <button
                                                    key={item.href}
                                                    onClick={() => window.open(item.href, "sutra_" + item.href.replace(/\//g, ""), "noopener")}
                                                    className={`flex items-center p-2 rounded-lg transition-colors group relative w-full text-left ${
                                                        "text-stone-600 hover:bg-stone-200 hover:text-stone-900"
                                                    } ${isCollapsed ? "justify-center" : "gap-3 px-3"}`}
                                                    title={`Open ${item.label} in new window`}
                                                >
                                                    <item.icon className="w-4 h-4 flex-shrink-0" />
                                                    {!isCollapsed && <span className="text-sm flex-1">{item.label}</span>}
                                                    {!isCollapsed && <ExternalLink className="w-3 h-3 text-stone-400 flex-shrink-0" />}
                                                </button>
                                            );
                                        }

                                        return (
                                            <Link
                                                key={item.href}
                                                href={item.href}
                                                className={`flex items-center p-2 rounded-lg transition-colors group relative ${
                                                    isActive
                                                        ? "bg-white text-stone-900 shadow-sm border border-stone-200/60 font-medium"
                                                        : "text-stone-600 hover:bg-stone-200 hover:text-stone-900"
                                                } ${isCollapsed ? "justify-center" : "gap-3 px-3"}`}
                                            >
                                                <div className="relative flex-shrink-0">
                                                    <item.icon className="w-4 h-4" />
                                                    {badge > 0 && isCollapsed && (
                                                        <span className="absolute -top-1 -right-1 bg-red-500 text-white text-[9px] font-bold w-4 h-4 rounded-full flex items-center justify-center">
                                                            {badge > 9 ? "9+" : badge}
                                                        </span>
                                                    )}
                                                </div>
                                                {!isCollapsed && <span className="text-sm flex-1">{item.label}</span>}
                                                {!isCollapsed && badge > 0 && (
                                                    <span className="bg-red-500 text-white text-xs font-bold px-1.5 py-0.5 rounded-full min-w-[20px] text-center">
                                                        {badge > 99 ? "99+" : badge}
                                                    </span>
                                                )}
                                                {isActive && !isCollapsed && (
                                                    <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-5 bg-stone-800 rounded-r-full" />
                                                )}
                                            </Link>
                                        );
                                    })}
                                </div>
                            )}

                            {/* Collapsed group: show a dot indicator if it has the active page */}
                            {collapsed && !isCollapsed && hasActiveItem && (
                                <div className="flex justify-center py-1">
                                    <div className="w-1 h-1 rounded-full bg-stone-600" />
                                </div>
                            )}
                        </div>
                    );
                })}
            </nav>

            {/* Footer */}
            <div className="p-4 border-t border-stone-200 space-y-2">
                <div className={`flex items-center gap-2 text-xs text-stone-500 ${isCollapsed ? "justify-center" : ""}`}>
                    <div className="status-dot status-dot-running w-2 h-2" />
                    {!isCollapsed && <span>System Online</span>}
                </div>
                {user && (
                    <div className={`flex items-center gap-2 ${isCollapsed ? "justify-center" : "justify-between"}`}>
                        {!isCollapsed && (
                            <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium text-stone-700 truncate">{user.username}</p>
                                <p className="text-xs text-stone-400 truncate capitalize">{user.role}</p>
                            </div>
                        )}
                        <button
                            onClick={handleLogout}
                            title="Sign out"
                            className="p-1.5 rounded-md hover:bg-stone-200 text-stone-400 hover:text-stone-600 transition-colors"
                        >
                            <LogOut className="w-4 h-4" />
                        </button>
                    </div>
                )}
            </div>
        </aside>
    );
}
