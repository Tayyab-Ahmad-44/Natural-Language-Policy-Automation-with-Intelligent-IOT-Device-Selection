"use client";
import { useState, useEffect } from 'react';
import api, { Task, Policy, PolicyConflict } from '@/lib/api';
import { Plus, ChevronDown, ChevronRight, Trash2, Loader2, AlertTriangle, X } from 'lucide-react';
import VoiceButton from '@/components/VoiceButton';
import ConflictCard from '@/components/ConflictCard';

function getPolicyActions(policy: Policy): Array<{ id: string; device: string; capability: string; args: Record<string, unknown> }> {
    const plan = policy.execution_plan;
    if (!plan) return [];

    // New DAG format
    if (!Array.isArray(plan) && typeof plan === 'object' && 'nodes' in plan && Array.isArray(plan.nodes)) {
        return plan.nodes
            .filter((node) => node && typeof node === 'object')
            .map((node) => {
                const action = node as Record<string, unknown>;
                return {
                    id: String(action.id ?? `${action.device}-${action.capability}`),
                    device: String(action.device ?? 'unknown-device'),
                    capability: String(action.capability ?? 'unknown-capability'),
                    args: typeof action.args === 'object' && action.args !== null ? action.args as Record<string, unknown> : {},
                };
            });
    }

    // Legacy flat action list
    if (Array.isArray(plan)) {
        return plan
            .filter((action) => action && typeof action === 'object')
            .map((action, idx) => {
                const legacyAction = action as Record<string, unknown>;
                return {
                    id: String(legacyAction.id ?? `${legacyAction.device}-${legacyAction.capability}-${idx}`),
                    device: String(legacyAction.device ?? 'unknown-device'),
                    capability: String(legacyAction.capability ?? 'unknown-capability'),
                    args: typeof legacyAction.args === 'object' && legacyAction.args !== null ? legacyAction.args as Record<string, unknown> : {},
                };
            });
    }

    return [];
}

export default function TasksPage() {
    const [tasks, setTasks] = useState<Task[]>([]);
    const [newTaskName, setNewTaskName] = useState('');
    const [newTaskDesc, setNewTaskDesc] = useState('');
    const [loading, setLoading] = useState(false);
    const [expandedTasks, setExpandedTasks] = useState<number[]>([]);
    const [taskConflicts, setTaskConflicts] = useState<PolicyConflict[]>([]);

    useEffect(() => {
        fetchTasks();
    }, []);

    const fetchTasks = async () => {
        try {
            const res = await api.get('/tasks/');
            setTasks(res.data);
        } catch (error) {
            console.error("Failed to fetch tasks", error);
        }
    };

    const handleCreateTask = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setTaskConflicts([]);
        try {
            const res = await api.post('/tasks/', { name: newTaskName, description: newTaskDesc });
            setNewTaskName('');
            setNewTaskDesc('');
            setTaskConflicts(res.data?.conflicts ?? []);
            fetchTasks();
        } catch (error) {
            console.error("Failed to create task", error);
            alert("Failed to create task. Ensure backend is running.");
        } finally {
            setLoading(false);
        }
    };

    const toggleExpand = (taskId: number) => {
        if (expandedTasks.includes(taskId)) {
            setExpandedTasks(expandedTasks.filter(id => id !== taskId));
        } else {
            setExpandedTasks([...expandedTasks, taskId]);
        }
    };

    const handleDeleteTask = async (taskId: number) => {
        if (!confirm('Are you sure? This will delete the task and all associated policies.')) return;
        try {
            await api.delete(`/tasks/${taskId}`);
            fetchTasks();
        } catch (error) {
            console.error("Failed to delete task", error);
        }
    };

    return (
        <div className="space-y-6">
            <div className="md:flex md:items-center md:justify-between">
                <div className="flex-1 min-w-0">
                    <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
                        Task Management
                    </h2>
                </div>
            </div>

            <div className="bg-white shadow sm:rounded-lg p-6">
                <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">Define New Task</h3>
                <form onSubmit={handleCreateTask} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700">Task Name</label>
                        <input
                            type="text"
                            required
                            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                            placeholder="e.g. Secure House"
                            value={newTaskName}
                            onChange={(e) => setNewTaskName(e.target.value)}
                        />
                    </div>
                    <div>
                        <div className="flex items-center justify-between mb-1">
                            <label className="block text-sm font-medium text-gray-700">Description (Natural Language)</label>
                            <VoiceButton
                                onTranscript={(text) => setNewTaskDesc(prev => prev ? `${prev} ${text}` : text)}
                                disabled={loading}
                            />
                        </div>
                        <textarea
                            required
                            rows={3}
                            className="block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                            placeholder="e.g. Lock all doors and turn off lights at 11pm"
                            value={newTaskDesc}
                            onChange={(e) => setNewTaskDesc(e.target.value)}
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={loading}
                        className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none disabled:opacity-50"
                    >
                        {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
                        {loading ? 'Generating Policies...' : 'Create Task'}
                    </button>
                </form>
            </div>

            {taskConflicts.length > 0 && (
                <div className="bg-white shadow sm:rounded-lg p-6 border border-amber-300">
                    <div className="flex items-start justify-between mb-3">
                        <h3 className="text-lg leading-6 font-medium text-amber-800 flex items-center gap-2">
                            <AlertTriangle className="w-5 h-5" />
                            {taskConflicts.length} potential conflict{taskConflicts.length === 1 ? '' : 's'} in the new task
                        </h3>
                        <button onClick={() => setTaskConflicts([])} className="text-gray-400 hover:text-gray-600">
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                    <p className="text-sm text-gray-500 mb-3">
                        The generated policies were saved, but some overlap with existing ones (or each other).
                        Review them on the <span className="font-medium">Policies</span> page and delete or adjust any you don&apos;t want.
                    </p>
                    <div className="space-y-2">
                        {taskConflicts.map((c, i) => <ConflictCard key={i} conflict={c} />)}
                    </div>
                </div>
            )}

            <div className="bg-white shadow overflow-hidden sm:rounded-md">
                <div className="px-4 py-5 sm:px-6 border-b border-gray-200">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">Active Tasks</h3>
                </div>
                <ul className="divide-y divide-gray-200">
                    {tasks.map((task) => (
                        <li key={task.id} className="bg-white">
                            <div className="px-4 py-4 sm:px-6 hover:bg-gray-50 cursor-pointer" onClick={() => toggleExpand(task.id)}>
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        {expandedTasks.includes(task.id) ? <ChevronDown className="w-5 h-5 text-gray-400" /> : <ChevronRight className="w-5 h-5 text-gray-400" />}
                                        <div>
                                            <p className="text-sm font-medium text-indigo-600 truncate">{task.name}</p>
                                            <p className="text-sm text-gray-500">{task.description}</p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <span className="text-xs text-gray-500">{task.policies?.length || 0} policies</span>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleDeleteTask(task.id);
                                            }}
                                            className="text-red-600 hover:text-red-900"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            </div>
                            {expandedTasks.includes(task.id) && (
                                <div className="bg-gray-50 px-4 py-4 sm:px-6 border-t border-gray-200">
                                    <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Generated Policies</h4>
                                    <ul className="space-y-3">
                                        {task.policies?.map((policy) => (
                                            <li key={policy.id} className="bg-white p-3 rounded border border-gray-200 shadow-sm">
                                                <div className="flex justify-between items-start">
                                                    <div>
                                                        <p className="text-sm font-medium text-gray-900">{policy.original_text}</p>
                                                        <p className="text-xs text-gray-500 mt-1">Time: {policy.start_time} - {policy.end_time}</p>
                                                    </div>
                                                </div>
                                                <div className="mt-2 space-y-1">
                                                    {getPolicyActions(policy).map((action) => (
                                                        <div key={action.id} className="text-xs text-gray-600 flex gap-2">
                                                            <span className="font-semibold">{action.device}</span>
                                                            <span>&rarr;</span>
                                                            <span>{action.capability}</span>
                                                            <span className="font-mono text-gray-400">{JSON.stringify(action.args)}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </li>
                                        ))}
                                        {(!task.policies || task.policies.length === 0) && (
                                            <p className="text-sm text-gray-500 italic">No policies generated.</p>
                                        )}
                                    </ul>
                                </div>
                            )}
                        </li>
                    ))}
                    {tasks.length === 0 && !loading && (
                        <li className="px-4 py-8 text-center text-gray-500">No tasks defined.</li>
                    )}
                </ul>
            </div>
        </div>
    );
}
