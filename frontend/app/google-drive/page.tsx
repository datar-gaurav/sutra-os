"use client";

import { useEffect, useState } from "react";
import {
    HardDrive, Plus, RefreshCw, Trash2, CheckCircle, XCircle,
    ExternalLink, Loader2, AlertCircle, FolderOpen, ChevronDown, ChevronUp,
} from "lucide-react";
import { googleDriveApi, Integration } from "@/lib/api";

const TOOLS = [
    { id: "gdrive_search_files",   label: "Search Files" },
    { id: "gdrive_read_file",      label: "Read File" },
    { id: "gdrive_upload_file",    label: "Upload File" },
    { id: "gdrive_create_document",label: "Create Document" },
    { id: "gdrive_list_folder",    label: "List Folder" },
    { id: "gdrive_create_folder",  label: "Create Folder" },
    { id: "gdrive_move_file",      label: "Move File" },
];

export default function GoogleDrivePage() {
    const [configs, setConfigs] = useState<Integration[]>([]);
    const [loading, setLoading] = useState(true);
    const [testing, setTesting] = useState<string | null>(null);
    const [testResults, setTestResults] = useState<Record<string, { ok: boolean; detail: string }>>({});
    const [disconnecting, setDisconnecting] = useState<string | null>(null);
    const [editingFolder, setEditingFolder] = useState<string | null>(null);
    const [folderInput, setFolderInput] = useState("");
    const [savingFolder, setSavingFolder] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showTools, setShowTools] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const data = await googleDriveApi.list();
            setConfigs(data);
        } catch (e: any) {
            setError(e.message || "Failed to load Google Drive connections");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); }, []);

    const handleConnect = () => { window.location.href = googleDriveApi.connectUrl(); };

    const handleTest = async (id: string) => {
        setTesting(id);
        try {
            const result = await googleDriveApi.test(id);
            setTestResults(prev => ({ ...prev, [id]: result }));
        } catch {
            setTestResults(prev => ({ ...prev, [id]: { ok: false, detail: "Connection test failed" } }));
        } finally {
            setTesting(null);
        }
    };

    const handleDisconnect = async (id: string) => {
        if (!confirm("Disconnect this Google Drive account? Agents using Drive tools will lose access.")) return;
        setDisconnecting(id);
        try {
            await googleDriveApi.disconnect(id);
            setConfigs(prev => prev.filter(c => c.id !== id));
            const next = { ...testResults };
            delete next[id];
            setTestResults(next);
        } catch (e: any) {
            setError(e.message || "Failed to disconnect");
        } finally {
            setDisconnecting(null);
        }
    };

    const handleSaveFolder = async (id: string) => {
        setSavingFolder(true);
        try {
            const cfg = configs.find(c => c.id === id);
            const updated = await googleDriveApi.update(id, {
                ...cfg?.extra_config,
                default_folder_id: folderInput.trim(),
            });
            setConfigs(prev => prev.map(c => c.id === id ? updated : c));
            setEditingFolder(null);
        } catch (e: any) {
            setError(e.message || "Failed to save folder");
        } finally {
            setSavingFolder(false);
        }
    };

    return (
        <div className="p-6 max-w-2xl mx-auto space-y-5">

            {/* ── Page header ─────────────────────────────────────────────── */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-stone-900">Google Drive</h1>
                    <p className="text-sm text-stone-500 mt-0.5">
                        Connect Google Drive so agents can read, write, and organise files.
                    </p>
                </div>
                <button
                    onClick={handleConnect}
                    className="flex items-center gap-2 px-4 py-2 bg-stone-700 hover:bg-stone-700 text-white text-sm font-medium rounded-xl shadow-sm transition-colors"
                >
                    <Plus className="w-4 h-4" />
                    Connect Account
                </button>
            </div>

            {/* ── Error banner ────────────────────────────────────────────── */}
            {error && (
                <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    {error}
                    <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600">✕</button>
                </div>
            )}

            {/* ── Connected accounts ──────────────────────────────────────── */}
            {loading ? (
                <div className="flex items-center justify-center py-20 text-stone-400">
                    <Loader2 className="w-5 h-5 animate-spin mr-2" />
                    Loading…
                </div>
            ) : configs.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 bg-white border border-dashed border-stone-300 rounded-2xl text-stone-400">
                    <HardDrive className="w-10 h-10 mb-3 opacity-30" />
                    <p className="text-sm font-medium text-stone-500">No Google Drive accounts connected</p>
                    <p className="text-xs text-stone-400 mt-1 mb-5">Connect an account so agents can access your files.</p>
                    <button
                        onClick={handleConnect}
                        className="flex items-center gap-2 px-4 py-2 bg-stone-700 hover:bg-stone-700 text-white text-sm font-medium rounded-xl transition-colors"
                    >
                        <Plus className="w-4 h-4" /> Connect Google Drive
                    </button>
                </div>
            ) : (
                <div className="space-y-3">
                    {configs.map(cfg => {
                        const email = cfg.extra_config?.google_email;
                        const folderId = cfg.extra_config?.default_folder_id;
                        const testResult = testResults[cfg.id];
                        const isEditing = editingFolder === cfg.id;

                        return (
                            <div key={cfg.id} className="bg-white border border-stone-200 rounded-2xl shadow-sm overflow-hidden">
                                {/* Account row */}
                                <div className="flex items-center gap-4 p-4">
                                    <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-center shrink-0">
                                        <HardDrive className="w-5 h-5 text-blue-600" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-semibold text-stone-800 truncate">{email || cfg.name}</p>
                                        <p className="text-xs text-stone-400">
                                            {cfg.agent_id ? "Agent-specific" : "System-wide"} ·{" "}
                                            Connected {new Date(cfg.created_at).toLocaleDateString()}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0">
                                        <button
                                            onClick={() => handleTest(cfg.id)}
                                            disabled={testing === cfg.id}
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-stone-600 bg-stone-100 hover:bg-stone-200 rounded-lg transition-colors disabled:opacity-50"
                                        >
                                            {testing === cfg.id
                                                ? <Loader2 className="w-3 h-3 animate-spin" />
                                                : <RefreshCw className="w-3 h-3" />}
                                            Test
                                        </button>
                                        <button
                                            onClick={() => handleDisconnect(cfg.id)}
                                            disabled={disconnecting === cfg.id}
                                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors disabled:opacity-50"
                                        >
                                            {disconnecting === cfg.id
                                                ? <Loader2 className="w-3 h-3 animate-spin" />
                                                : <Trash2 className="w-3 h-3" />}
                                            Disconnect
                                        </button>
                                    </div>
                                </div>

                                {/* Test result */}
                                {testResult && (
                                    <div className={`flex items-center gap-2 mx-4 mb-3 px-3 py-2 rounded-lg text-xs ${testResult.ok ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                                        {testResult.ok
                                            ? <CheckCircle className="w-3.5 h-3.5 shrink-0" />
                                            : <XCircle className="w-3.5 h-3.5 shrink-0" />}
                                        {testResult.detail}
                                    </div>
                                )}

                                {/* Default folder */}
                                <div className="border-t border-stone-100 px-4 py-3">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="flex items-center gap-1.5 text-xs font-medium text-stone-500">
                                            <FolderOpen className="w-3.5 h-3.5" />
                                            Default Folder
                                        </span>
                                        {!isEditing && (
                                            <button
                                                onClick={() => { setEditingFolder(cfg.id); setFolderInput(folderId || ""); }}
                                                className="text-xs text-stone-700 hover:text-stone-700 font-medium"
                                            >
                                                {folderId ? "Change" : "Set folder"}
                                            </button>
                                        )}
                                    </div>

                                    {isEditing ? (
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                value={folderInput}
                                                onChange={e => setFolderInput(e.target.value)}
                                                placeholder="Folder ID — leave empty for My Drive root"
                                                className="flex-1 px-3 py-1.5 bg-white border border-stone-300 rounded-lg text-sm text-stone-900 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-600 focus:border-transparent"
                                            />
                                            <button
                                                onClick={() => handleSaveFolder(cfg.id)}
                                                disabled={savingFolder}
                                                className="px-3 py-1.5 bg-stone-700 hover:bg-stone-700 text-white text-xs font-medium rounded-lg disabled:opacity-50"
                                            >
                                                {savingFolder ? <Loader2 className="w-3 h-3 animate-spin" /> : "Save"}
                                            </button>
                                            <button
                                                onClick={() => setEditingFolder(null)}
                                                className="px-3 py-1.5 bg-stone-100 hover:bg-stone-200 text-stone-600 text-xs rounded-lg"
                                            >
                                                Cancel
                                            </button>
                                        </div>
                                    ) : folderId ? (
                                        <div className="flex items-center gap-2">
                                            <code className="text-xs bg-stone-50 border border-stone-200 text-stone-600 px-2 py-1 rounded font-mono">{folderId}</code>
                                            <a
                                                href={`https://drive.google.com/drive/folders/${folderId}`}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="text-stone-400 hover:text-stone-700"
                                            >
                                                <ExternalLink className="w-3.5 h-3.5" />
                                            </a>
                                        </div>
                                    ) : (
                                        <p className="text-xs text-stone-400">Not set — agents default to My Drive root.</p>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* ── Available tools (collapsible) ───────────────────────────── */}
            <div className="bg-white border border-stone-200 rounded-2xl shadow-sm overflow-hidden">
                <button
                    onClick={() => setShowTools(v => !v)}
                    className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-stone-700 hover:bg-stone-50 transition-colors"
                >
                    <span>Available agent tools ({TOOLS.length})</span>
                    {showTools ? <ChevronUp className="w-4 h-4 text-stone-400" /> : <ChevronDown className="w-4 h-4 text-stone-400" />}
                </button>
                {showTools && (
                    <div className="border-t border-stone-100 px-4 py-3">
                        <div className="flex flex-wrap gap-2 mb-2">
                            {TOOLS.map(t => (
                                <span key={t.id} className="px-2.5 py-1 bg-stone-100 text-stone-600 text-xs font-mono rounded-lg">
                                    {t.id}
                                </span>
                            ))}
                        </div>
                        <p className="text-xs text-stone-400">Enable these on any agent via the agent editor → Tools tab.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
