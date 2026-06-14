"use client";
import { useState, useEffect } from 'react';
import api, { Policy, PolicyPreviewResponse, ExecutionRunDetail, ExecutionStep, getExecutionDetail } from '@/lib/api';
import { Plus, Check, AlertCircle, Play, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import dynamic from 'next/dynamic';
import VoiceButton from '@/components/VoiceButton';

const DAGView = dynamic(() => import('@/components/DAGView'), { ssr: false });

// Helper to count nodes in a DAG or legacy flat plan
function countActions(plan: unknown): number {
    if (!plan) return 0;
    if (typeof plan === 'object' && !Array.isArray(plan) && 'nodes' in plan) {
        const maybeDag = plan as { nodes?: unknown };
        if (Array.isArray(maybeDag.nodes)) return maybeDag.nodes.length;
    }
    if (Array.isArray(plan)) return plan.length;
    return 0;
}

export default function PoliciesPage() {
    const [policies, setPolicies] = useState<Policy[]>([]);
    const [policyInput, setPolicyInput] = useState('');
    const [policyName, setPolicyName] = useState('');
    const [repeatInterval, setRepeatInterval] = useState('');
    const [preview, setPreview] = useState<PolicyPreviewResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [executing, setExecuting] = useState<number | null>(null);
    const [executionResult, setExecutionResult] = useState<ExecutionRunDetail | null>(null);
    const [liveSteps, setLiveSteps] = useState<Record<string, Partial<ExecutionStep>>>({});
    const [expandedPolicy, setExpandedPolicy] = useState<number | null>(null);

    useEffect(() => {
        fetchPolicies();
    }, []);

    const fetchPolicies = async () => {
        try {
            const res = await api.get('/policies/');
            setPolicies(res.data);
        } catch (error) {
            console.error("Failed to fetch policies", error);
        }
    };

    const handlePreview = async () => {
        if (!policyInput) return;
        setLoading(true);
        setPreview(null);
        try {
            const res = await api.post('/policies/preview', { name: "preview", original_text: policyInput });
            setPreview(res.data);
        } catch (error) {
            console.error("Failed to preview policy", error);
            alert("Failed to interpret policy. Make sure backend is running and LLM key is valid.");
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async () => {
        if (!policyName || !policyInput) return;
        setLoading(true);
        try {
            const intervalVal = repeatInterval.trim() !== '' ? parseInt(repeatInterval, 10) : null;
            await api.post('/policies/', {
                name: policyName,
                original_text: policyInput,
                repeat_interval_seconds: intervalVal,
            });
            setPolicyName('');
            setPolicyInput('');
            setRepeatInterval('');
            setPreview(null);
            fetchPolicies();
        } catch (error) {
            console.error("Failed to create policy", error);
        } finally {
            setLoading(false);
        }
    };

    const handleExecute = async (policyId: number) => {
        setExecuting(policyId);
        setExecutionResult(null);
        setLiveSteps({});
        setExpandedPolicy(policyId);

        try {
            const response = await fetch(
                `http://localhost:8000/api/policies/${policyId}/execute/stream`,
                { method: 'POST' }
            );
            if (!response.body) throw new Error('No response body');

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() ?? '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const evt = JSON.parse(line.slice(6));
                        if (evt.type === 'node_completed') {
                            setLiveSteps(prev => ({
                                ...prev,
                                [evt.node_id]: {
                                    node_id: evt.node_id,
                                    status: evt.status,
                                    response_data: evt.response_data ?? undefined,
                                    error_message: evt.error ?? undefined,
                                    http_status_code: evt.http_status_code ?? undefined,
                                } as ExecutionStep,
                            }));
                        } else if (evt.type === 'run_completed' || evt.type === 'run_failed') {
                            const detail = await getExecutionDetail(evt.run_id);
                            setExecutionResult(detail);
                        }
                    } catch { /* ignore parse errors */ }
                }
            }
        } catch (error) {
            console.error("Failed to execute policy", error);
            alert("Execution failed. Check if mock device server is running.");
        } finally {
            setExecuting(null);
        }
    };

    return (
        <div className="space-y-6">
            <div className="md:flex md:items-center md:justify-between">
                <div className="flex-1 min-w-0">
                    <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
                        Policy Definitions
                    </h2>
                </div>
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                {/* ─── Create Panel ──────────────────────────── */}
                <div className="bg-white shadow sm:rounded-lg p-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">Create New Policy</h3>
                    <div className="space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700">Policy Name</label>
                            <input
                                type="text"
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                                placeholder="e.g. Night Security"
                                value={policyName}
                                onChange={(e) => setPolicyName(e.target.value)}
                            />
                        </div>
                        <div>
                            <div className="flex items-center justify-between mb-1">
                                <label className="block text-sm font-medium text-gray-700">Natural Language Rule</label>
                                <VoiceButton
                                    onTranscript={(text) => setPolicyInput(prev => prev ? `${prev} ${text}` : text)}
                                    disabled={loading}
                                />
                            </div>
                            <textarea
                                rows={4}
                                className="block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                                placeholder="e.g. If someone enters Room2 from 10pm to 5am, ring the alarm of that room"
                                value={policyInput}
                                onChange={(e) => setPolicyInput(e.target.value)}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700">
                                Repeat Interval (seconds)
                                <span className="ml-1 text-xs font-normal text-gray-400">— leave empty to run once per window</span>
                            </label>
                            <input
                                type="number"
                                min={1}
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                                placeholder="e.g. 60"
                                value={repeatInterval}
                                onChange={(e) => setRepeatInterval(e.target.value)}
                            />
                        </div>
                        <div className="flex gap-3">
                            <button
                                onClick={handlePreview}
                                disabled={loading}
                                className="flex-1 inline-flex justify-center items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none cursor-pointer"
                            >
                                {loading ? 'Processing...' : 'Preview Interpretation'}
                            </button>
                            {preview && (
                                <button
                                    onClick={handleCreate}
                                    disabled={loading || !policyName}
                                    className="flex-1 inline-flex justify-center items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none cursor-pointer"
                                >
                                    <Plus className="w-4 h-4 mr-2" />
                                    Save Policy
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                {/* ─── Preview Panel ─────────────────────────── */}
                <div className="bg-white shadow sm:rounded-lg p-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">Interpretation Preview</h3>
                    {preview ? (
                        <div className="space-y-4">
                            {/* Validation badge */}
                            <div className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium ${preview.validation.valid
                                    ? "bg-green-50 text-green-700 border border-green-200"
                                    : "bg-red-50 text-red-700 border border-red-200"
                                }`}>
                                {preview.validation.valid ? (
                                    <><Check className="w-4 h-4" /> DAG is valid</>
                                ) : (
                                    <><AlertCircle className="w-4 h-4" /> {preview.validation.errors.join(", ")}</>
                                )}
                            </div>

                            {/* Time window */}
                            <div className="text-sm text-gray-600">
                                <strong>Time Window:</strong> {preview.time_window.from_time} - {preview.time_window.to_time}
                            </div>

                            {/* Stats */}
                            <div className="flex gap-3 text-xs">
                                <span className="bg-indigo-50 text-indigo-700 px-2 py-1 rounded font-medium">
                                    {preview.execution_dag.nodes.length} nodes
                                </span>
                                <span className="bg-gray-50 text-gray-700 px-2 py-1 rounded font-medium">
                                    {preview.levels.length} levels
                                </span>
                                <span className="bg-blue-50 text-blue-700 px-2 py-1 rounded font-medium">
                                    {preview.execution_dag.nodes.filter(n => n.dependencies.length === 0).length} parallel roots
                                </span>
                            </div>

                            {/* DAG Visualization */}
                            {preview.execution_dag.nodes.length > 0 && (
                                <DAGView dag={preview.execution_dag} height="400px" />
                            )}

                            {preview.execution_dag.nodes.length === 0 && (
                                <p className="text-gray-500 italic text-sm">No actions inferred from this policy.</p>
                            )}
                        </div>
                    ) : (
                        <div className="text-center py-12 text-gray-500 bg-gray-50 rounded-md border-2 border-dashed border-gray-200">
                            <AlertCircle className="mx-auto h-8 w-8 text-gray-400" />
                            <p className="mt-2">Enter a policy and click Preview to see the execution DAG.</p>
                        </div>
                    )}
                </div>
            </div>

            {/* ─── Active Policies List ──────────────────── */}
            <div className="bg-white shadow overflow-hidden sm:rounded-md mt-6">
                <div className="px-4 py-5 sm:px-6 border-b border-gray-200">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">Active Policies</h3>
                </div>
                <ul className="divide-y divide-gray-200">
                    {policies.map((policy) => {
                        const isExpanded = expandedPolicy === policy.id;
                        const dag = policy.execution_plan && typeof policy.execution_plan === 'object' && 'nodes' in policy.execution_plan
                            ? policy.execution_plan
                            : null;

                        return (
                            <li key={policy.id} className="px-4 py-4 sm:px-6">
                                <div className="flex items-center justify-between">
                                    <div className="flex flex-col flex-1 min-w-0 mr-4">
                                        <p className="text-sm font-medium text-indigo-600 truncate">{policy.name}</p>
                                        <p className="text-sm text-gray-500 truncate">{policy.original_text}</p>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <div className="flex flex-col items-end">
                                            <p className="text-sm text-gray-900 font-bold">{policy.start_time} - {policy.end_time}</p>
                                            <p className="text-xs text-gray-500">{countActions(policy.execution_plan)} actions</p>
                                            <p className="text-xs text-indigo-500 font-medium">
                                                {policy.repeat_interval_seconds
                                                    ? `every ${policy.repeat_interval_seconds}s`
                                                    : 'once per window'}
                                            </p>
                                            {policy.last_executed_at && (
                                                <p className="text-xs text-gray-400">
                                                    last run {new Date(policy.last_executed_at).toLocaleTimeString()}
                                                </p>
                                            )}
                                        </div>
                                        <button
                                            onClick={() => handleExecute(policy.id)}
                                            disabled={executing === policy.id}
                                            className="inline-flex items-center px-3 py-1.5 border border-green-300 text-sm font-medium rounded-md text-green-700 bg-green-50 hover:bg-green-100 focus:outline-none cursor-pointer disabled:opacity-50"
                                            title="Execute now"
                                        >
                                            <Play className="w-3.5 h-3.5 mr-1" />
                                            {executing === policy.id ? "Running..." : "Execute"}
                                        </button>
                                        {dag && (
                                            <button
                                                onClick={() => setExpandedPolicy(isExpanded ? null : policy.id)}
                                                className="text-gray-400 hover:text-gray-600 cursor-pointer"
                                                title="Toggle DAG view"
                                            >
                                                {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                                            </button>
                                        )}
                                        <button
                                            onClick={async () => {
                                                if (confirm('Are you sure you want to delete this policy?')) {
                                                    try {
                                                        await api.delete(`/policies/${policy.id}`);
                                                        fetchPolicies();
                                                    } catch (error) {
                                                        console.error("Failed to delete policy", error);
                                                    }
                                                }
                                            }}
                                            className="text-red-600 hover:text-red-900 text-sm font-medium cursor-pointer"
                                        >
                                            Delete
                                        </button>
                                    </div>
                                </div>

                                {/* Expanded DAG view with live / completed execution results */}
                                {isExpanded && dag && (
                                    <div className="mt-4">
                                        {executing === policy.id ? (
                                            // ── Streaming live ──────────────────────────────
                                            <div className="space-y-3">
                                                <div className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium bg-blue-50 text-blue-700">
                                                    <Loader2 className="w-4 h-4 animate-spin" />
                                                    Executing — nodes update as they complete
                                                </div>
                                                <DAGView
                                                    dag={dag}
                                                    steps={Object.values(liveSteps) as ExecutionStep[]}
                                                    height="400px"
                                                />
                                            </div>
                                        ) : executionResult && executionResult.policy_id === policy.id ? (
                                            // ── Completed ───────────────────────────────────
                                            <div className="space-y-3">
                                                <div className={`flex items-center gap-2 px-3 py-2 rounded text-sm font-medium ${
                                                    executionResult.status === "completed" ? "bg-green-50 text-green-700" :
                                                    executionResult.status === "failed"    ? "bg-red-50 text-red-700" :
                                                                                             "bg-yellow-50 text-yellow-700"
                                                }`}>
                                                    Run #{executionResult.id}: {executionResult.status}
                                                    {executionResult.summary && (
                                                        <span className="ml-2 text-xs opacity-75">
                                                            ({executionResult.summary.success}/{executionResult.summary.total} succeeded)
                                                        </span>
                                                    )}
                                                </div>
                                                <DAGView
                                                    dag={executionResult.execution_dag || dag}
                                                    steps={executionResult.steps}
                                                    height="400px"
                                                />
                                            </div>
                                        ) : (
                                            <DAGView dag={dag} height="350px" />
                                        )}
                                    </div>
                                )}
                            </li>
                        );
                    })}
                    {policies.length === 0 && (
                        <li className="px-4 py-8 text-center text-gray-500 text-sm">No policies yet. Create one above.</li>
                    )}
                </ul>
            </div>
        </div>
    );
}
