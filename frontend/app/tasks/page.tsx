"use client";

import { useEffect, useState } from "react";
import {
    Plus, Trash2, X, FolderOpen, Loader2, GitBranch,
} from "lucide-react";
import { tasksApi, projectsApi, agentsApi, Task, Project, Agent, TaskStatus, TaskPriority } from "@/lib/api";

const COLUMNS: { status: TaskStatus; label: string; color: string }[] = [
    { status: "backlog",     label: "Backlog",      color: "bg-stone-100 text-stone-600" },
    { status: "todo",        label: "To Do",        color: "bg-blue-50 text-blue-600" },
    { status: "in_progress", label: "In Progress",  color: "bg-amber-50 text-amber-600" },
    { status: "review",      label: "Review",       color: "bg-purple-50 text-purple-600" },
    { status: "done",        label: "Done",         color: "bg-green-50 text-green-600" },
];

const PRIORITY_COLORS: Record<TaskPriority, string> = {
    critical: "bg-red-100 text-red-700",
    high:     "bg-orange-100 text-orange-700",
    medium:   "bg-yellow-100 text-yellow-700",
    low:      "bg-stone-100 text-stone-500",
};

function priorityDot(p: TaskPriority) {
    const colors: Record<TaskPriority, string> = {
        critical: "bg-red-500",
        high:     "bg-orange-400",
        medium:   "bg-yellow-400",
        low:      "bg-stone-300",
    };
    return <span className={`inline-block w-2 h-2 rounded-full ${colors[p]} mr-1`} />;
}

interface TaskModalProps {
    task?: Task | null;
    projects: Project[];
    agents: Agent[];
    onClose: () => void;
    onSave: (data: Partial<Task>) => Promise<void>;
}

function TaskModal({ task, projects, agents, onClose, onSave }: TaskModalProps) {
    const [title, setTitle] = useState(task?.title ?? "");
    const [description, setDescription] = useState(task?.description ?? "");
    const [status, setStatus] = useState<TaskStatus>(task?.status ?? "todo");
    const [priority, setPriority] = useState<TaskPriority>(task?.priority ?? "medium");
    const [projectId, setProjectId] = useState(task?.project_id ?? "");
    const [assigneeAgentId, setAssigneeAgentId] = useState(task?.assignee_agent_id ?? "");
    const [notes, setNotes] = useState(task?.notes ?? "");
    const [saving, setSaving] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setSaving(true);
        try {
            await onSave({
                title,
                description: description || undefined,
                status,
                priority,
                project_id: projectId || undefined,
                assignee_agent_id: assigneeAgentId || undefined,
                notes: notes || undefined,
            });
            onClose();
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-stone-900">
                        {task ? "Edit Task" : "New Task"}
                    </h2>
                    <button onClick={onClose} className="p-1 rounded hover:bg-stone-100 text-stone-400">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Title *</label>
                        <input
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={title}
                            onChange={e => setTitle(e.target.value)}
                            required
                            placeholder="Task title..."
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Description</label>
                        <textarea
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 h-20 resize-none"
                            value={description}
                            onChange={e => setDescription(e.target.value)}
                            placeholder="What needs to be done..."
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1">Status</label>
                            <select
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={status}
                                onChange={e => setStatus(e.target.value as TaskStatus)}
                            >
                                {COLUMNS.map(c => <option key={c.status} value={c.status}>{c.label}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1">Priority</label>
                            <select
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={priority}
                                onChange={e => setPriority(e.target.value as TaskPriority)}
                            >
                                {(["critical", "high", "medium", "low"] as TaskPriority[]).map(p =>
                                    <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
                                )}
                            </select>
                        </div>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Project</label>
                        <select
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={projectId}
                            onChange={e => setProjectId(e.target.value)}
                        >
                            <option value="">No project</option>
                            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Assign to Agent</label>
                        <select
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                            value={assigneeAgentId}
                            onChange={e => setAssigneeAgentId(e.target.value)}
                        >
                            <option value="">Unassigned</option>
                            {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Notes</label>
                        <textarea
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 h-16 resize-none"
                            value={notes}
                            onChange={e => setNotes(e.target.value)}
                            placeholder="Additional notes..."
                        />
                    </div>
                    <div className="flex gap-2 justify-end pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-sm rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={saving || !title.trim()}
                            className="px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-700 disabled:opacity-50 flex items-center gap-2"
                        >
                            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                            {task ? "Save Changes" : "Create Task"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

interface DecomposeModalProps {
    task: Task;
    agents: Agent[];
    onClose: () => void;
    onDone: (subtasks: Task[]) => void;
}

function DecomposeModal({ task, agents, onClose, onDone }: DecomposeModalProps) {
    const [guidance, setGuidance] = useState("");
    const [agentId, setAgentId] = useState("");
    const [maxSubtasks, setMaxSubtasks] = useState(5);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function handleDecompose() {
        setLoading(true);
        setError(null);
        try {
            const subtasks = await tasksApi.decompose(task.id, {
                guidance: guidance || undefined,
                agent_id: agentId || undefined,
                max_subtasks: maxSubtasks,
            });
            onDone(subtasks);
            onClose();
        } catch (e: any) {
            setError(e?.message || "Decomposition failed");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-lg font-semibold text-stone-900 flex items-center gap-2">
                        <GitBranch className="w-5 h-5 text-stone-700" /> Decompose Task
                    </h2>
                    <button onClick={onClose} className="p-1 rounded hover:bg-stone-100 text-stone-400">
                        <X className="w-5 h-5" />
                    </button>
                </div>
                <p className="text-sm text-stone-500 mb-4">
                    Break <span className="font-medium text-stone-700">&ldquo;{task.title}&rdquo;</span> into subtasks using AI.
                </p>
                <div className="space-y-3">
                    <div>
                        <label className="block text-xs font-medium text-stone-600 mb-1">Guidance (optional)</label>
                        <textarea
                            className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600 h-20 resize-none"
                            placeholder="e.g. Focus on backend first, split by feature..."
                            value={guidance}
                            onChange={e => setGuidance(e.target.value)}
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1">Use Agent&apos;s LLM</label>
                            <select
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={agentId}
                                onChange={e => setAgentId(e.target.value)}
                            >
                                <option value="">Default provider</option>
                                {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-stone-600 mb-1">Max subtasks</label>
                            <input
                                type="number"
                                min={1}
                                max={20}
                                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                value={maxSubtasks}
                                onChange={e => setMaxSubtasks(Number(e.target.value))}
                            />
                        </div>
                    </div>
                    {error && <p className="text-xs text-red-500">{error}</p>}
                    <div className="flex gap-2 justify-end pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-sm rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50"
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleDecompose}
                            disabled={loading}
                            className="px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-700 disabled:opacity-50 flex items-center gap-2"
                        >
                            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <GitBranch className="w-4 h-4" />}
                            {loading ? "Decomposing..." : "Decompose"}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

interface TaskCardProps {
    task: Task;
    agents: Agent[];
    projects: Project[];
    onEdit: (t: Task) => void;
    onDelete: (id: string) => void;
    onStatusChange: (id: string, status: TaskStatus) => void;
    onDecompose: (t: Task) => void;
}

function TaskCard({ task, agents, projects, onEdit, onDelete, onStatusChange, onDecompose }: TaskCardProps) {
    const agent = agents.find(a => a.id === task.assignee_agent_id);
    const project = projects.find(p => p.id === task.project_id);

    return (
        <div
            className="bg-white rounded-lg border border-stone-200 p-3 shadow-sm hover:shadow cursor-pointer group"
            onClick={() => onEdit(task)}
        >
            <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium text-stone-800 leading-tight">{task.title}</p>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all flex-shrink-0">
                    {!task.parent_task_id && (
                        <button
                            title="Decompose into subtasks"
                            onClick={e => { e.stopPropagation(); onDecompose(task); }}
                            className="p-1 rounded hover:bg-stone-100 text-stone-400 hover:text-stone-700"
                        >
                            <GitBranch className="w-3.5 h-3.5" />
                        </button>
                    )}
                    <button
                        onClick={e => { e.stopPropagation(); onDelete(task.id); }}
                        className="p-1 rounded hover:bg-red-50 text-stone-400 hover:text-red-500"
                    >
                        <Trash2 className="w-3.5 h-3.5" />
                    </button>
                </div>
            </div>
            {task.description && (
                <p className="text-xs text-stone-500 mt-1 line-clamp-2">{task.description}</p>
            )}
            <div className="flex items-center gap-2 mt-2 flex-wrap">
                <span className={`inline-flex items-center text-xs px-1.5 py-0.5 rounded ${PRIORITY_COLORS[task.priority]}`}>
                    {priorityDot(task.priority)}{task.priority}
                </span>
                {project && (
                    <span className="inline-flex items-center gap-1 text-xs text-stone-500">
                        <FolderOpen className="w-3 h-3" />{project.name}
                    </span>
                )}
            </div>
            {agent && (
                <div className="mt-2 flex items-center gap-1.5">
                    <div className="w-5 h-5 rounded-full bg-stone-200 flex items-center justify-center">
                        <span className="text-xs font-bold text-stone-700">{agent.name[0]}</span>
                    </div>
                    <span className="text-xs text-stone-500">{agent.name}</span>
                </div>
            )}
            <div className="mt-2 flex gap-1" onClick={e => e.stopPropagation()}>
                {COLUMNS.map(col => (
                    <button
                        key={col.status}
                        title={col.label}
                        onClick={() => onStatusChange(task.id, col.status)}
                        className={`flex-1 h-1 rounded-full transition-colors ${task.status === col.status ? col.color.split(" ")[0] : "bg-stone-100 hover:bg-stone-200"}`}
                    />
                ))}
            </div>
        </div>
    );
}

export default function TasksPage() {
    const [tasks, setTasks] = useState<Task[]>([]);
    const [projects, setProjects] = useState<Project[]>([]);
    const [agents, setAgents] = useState<Agent[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedProject, setSelectedProject] = useState<string>("");
    const [editingTask, setEditingTask] = useState<Task | null | undefined>(undefined); // undefined = closed
    const [decomposingTask, setDecomposingTask] = useState<Task | null>(null);
    const [showNewProject, setShowNewProject] = useState(false);
    const [newProjectName, setNewProjectName] = useState("");

    async function load(projectId?: string) {
        const [t, p, a] = await Promise.all([
            tasksApi.list(projectId ? { project_id: projectId } : {}),
            projectsApi.list(),
            agentsApi.list(),
        ]);
        setTasks(t);
        setProjects(p);
        setAgents(a);
    }

    useEffect(() => {
        load(selectedProject || undefined).finally(() => setLoading(false));
    }, [selectedProject]);

    async function handleSaveTask(data: Partial<Task>) {
        if (editingTask?.id) {
            const updated = await tasksApi.update(editingTask.id, data);
            setTasks(prev => prev.map(t => t.id === updated.id ? updated : t));
        } else {
            const created = await tasksApi.create({
                ...data,
                project_id: selectedProject || data.project_id,
            });
            setTasks(prev => [created, ...prev]);
        }
    }

    async function handleDeleteTask(id: string) {
        if (!confirm("Delete this task?")) return;
        await tasksApi.delete(id);
        setTasks(prev => prev.filter(t => t.id !== id));
    }

    async function handleStatusChange(id: string, status: TaskStatus) {
        const updated = await tasksApi.update(id, { status });
        setTasks(prev => prev.map(t => t.id === updated.id ? updated : t));
    }

    async function handleCreateProject() {
        if (!newProjectName.trim()) return;
        const p = await projectsApi.create({ name: newProjectName.trim() });
        setProjects(prev => [...prev, p]);
        setNewProjectName("");
        setShowNewProject(false);
        setSelectedProject(p.id);
    }

    const tasksByStatus = (status: TaskStatus) => tasks.filter(t => t.status === status);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <Loader2 className="w-6 h-6 animate-spin text-stone-600" />
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full">
            {/* Header */}
            <div className="px-6 py-4 border-b border-stone-200 bg-white flex items-center justify-between gap-4">
                <div>
                    <h1 className="text-xl font-semibold text-stone-900">Tasks</h1>
                    <p className="text-sm text-stone-500">Manage and track work across agents and humans</p>
                </div>
                <div className="flex items-center gap-2">
                    {/* Project filter */}
                    <select
                        className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                        value={selectedProject}
                        onChange={e => setSelectedProject(e.target.value)}
                    >
                        <option value="">All projects</option>
                        {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                    {/* New project */}
                    {showNewProject ? (
                        <div className="flex items-center gap-2">
                            <input
                                autoFocus
                                className="border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-600"
                                placeholder="Project name..."
                                value={newProjectName}
                                onChange={e => setNewProjectName(e.target.value)}
                                onKeyDown={e => { if (e.key === "Enter") handleCreateProject(); if (e.key === "Escape") setShowNewProject(false); }}
                            />
                            <button onClick={handleCreateProject} className="px-3 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-700">Add</button>
                            <button onClick={() => setShowNewProject(false)} className="p-2 rounded-lg border border-stone-200 hover:bg-stone-50"><X className="w-4 h-4" /></button>
                        </div>
                    ) : (
                        <button
                            onClick={() => setShowNewProject(true)}
                            className="px-3 py-2 text-sm rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50 flex items-center gap-2"
                        >
                            <FolderOpen className="w-4 h-4" /> New Project
                        </button>
                    )}
                    <button
                        onClick={() => setEditingTask(null)}
                        className="px-4 py-2 text-sm rounded-lg bg-stone-700 text-white hover:bg-stone-700 flex items-center gap-2"
                    >
                        <Plus className="w-4 h-4" /> New Task
                    </button>
                </div>
            </div>

            {/* Kanban Board */}
            <div className="flex-1 overflow-x-auto p-6">
                <div className="flex gap-4 h-full min-w-max">
                    {COLUMNS.map(col => {
                        const colTasks = tasksByStatus(col.status);
                        return (
                            <div key={col.status} className="flex flex-col w-72 flex-shrink-0">
                                {/* Column header */}
                                <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-2">
                                        <span className={`text-xs font-semibold px-2 py-1 rounded-full ${col.color}`}>
                                            {col.label}
                                        </span>
                                        <span className="text-xs text-stone-400 font-medium">{colTasks.length}</span>
                                    </div>
                                    <button
                                        onClick={() => setEditingTask(null)}
                                        className="p-1 rounded hover:bg-stone-200 text-stone-400"
                                        title="Add task"
                                    >
                                        <Plus className="w-4 h-4" />
                                    </button>
                                </div>
                                {/* Task cards */}
                                <div className="flex-1 space-y-2 overflow-y-auto pr-1">
                                    {colTasks.length === 0 ? (
                                        <div className="border-2 border-dashed border-stone-200 rounded-lg p-4 text-center text-xs text-stone-400">
                                            No tasks
                                        </div>
                                    ) : (
                                        colTasks.map(task => (
                                            <TaskCard
                                                key={task.id}
                                                task={task}
                                                agents={agents}
                                                projects={projects}
                                                onEdit={t => setEditingTask(t)}
                                                onDelete={handleDeleteTask}
                                                onStatusChange={handleStatusChange}
                                                onDecompose={t => setDecomposingTask(t)}
                                            />
                                        ))
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Task Modal */}
            {editingTask !== undefined && (
                <TaskModal
                    task={editingTask}
                    projects={projects}
                    agents={agents}
                    onClose={() => setEditingTask(undefined)}
                    onSave={handleSaveTask}
                />
            )}

            {/* Decompose Modal */}
            {decomposingTask && (
                <DecomposeModal
                    task={decomposingTask}
                    agents={agents}
                    onClose={() => setDecomposingTask(null)}
                    onDone={subtasks => setTasks(prev => [...prev, ...subtasks])}
                />
            )}
        </div>
    );
}
