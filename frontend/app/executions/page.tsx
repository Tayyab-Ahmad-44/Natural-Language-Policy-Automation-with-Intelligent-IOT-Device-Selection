"use client";
import { useState, useEffect, useCallback } from "react";
import {
    ExecutionRun,
    ExecutionRunDetail,
    getExecutions,
    getExecutionDetail,
} from "@/lib/api";
import {
    ArrowLeft,
    RefreshCw,
    CheckCircle2,
    XCircle,
    Clock,
    AlertTriangle,
    Loader2,
} from "lucide-react";
import dynamic from "next/dynamic";

const DAGView = dynamic(() => import("@/components/DAGView"), { ssr: false });

// ─── Status badge helpers ──────────────────────────────────────

const statusColor: Record<string, string> = {
    pending: "bg-gray-100 text-gray-700",
    running: "bg-blue-100 text-blue-700",
    completed: "bg-green-100 text-green-700",
    partial_failure: "bg-yellow-100 text-yellow-700",
    failed: "bg-red-100 text-red-700",
};

const StatusIcon = ({ status }: { status: string }) => {
    switch (status) {
        case "completed":
            return <CheckCircle2 className="w-4 h-4 text-green-500" />;
        case "failed":
            return <XCircle className="w-4 h-4 text-red-500" />;
        case "partial_failure":
            return <AlertTriangle className="w-4 h-4 text-yellow-500" />;
        case "running":
            return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
        default:
            return <Clock className="w-4 h-4 text-gray-400" />;
    }
};

function formatDate(iso?: string) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
}

function duration(start?: string, end?: string) {
    if (!start) return "—";
    const s = new Date(start).getTime();
    const e = end ? new Date(end).getTime() : Date.now();
    const ms = e - s;
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
}

// ─── Component ────────────────────────────────────────────────

export default function ExecutionsPage() {
    const [runs, setRuns] = useState<ExecutionRun[]>([]);
    const [selectedRun, setSelectedRun] = useState<ExecutionRunDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [detailLoading, setDetailLoading] = useState(false);

    const fetchRuns = useCallback(async () => {
        try {
            const data = await getExecutions();
            // Sort newest first
            data.sort(
                (a, b) =>
                    new Date(b.started_at || "").getTime() -
                    new Date(a.started_at || "").getTime()
            );
            setRuns(data);
        } catch (err) {
            console.error("Failed to fetch executions", err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchRuns();
    }, [fetchRuns]);

    // Auto-refresh every 5s while any run is still "running"
    useEffect(() => {
        const hasRunning = runs.some((r) => r.status === "running");
        if (!hasRunning) return;
        const iv = setInterval(fetchRuns, 5000);
        return () => clearInterval(iv);
    }, [runs, fetchRuns]);

    const openDetail = async (runId: number) => {
        setDetailLoading(true);
        try {
            const detail = await getExecutionDetail(runId);
            setSelectedRun(detail);
        } catch (err) {
            console.error("Failed to fetch run detail", err);
        } finally {
            setDetailLoading(false);
        }
    };

    // ─── Detail View ──────────────────────────────────────────
    if (selectedRun) {
        return (
            <div className="space-y-6">
                {/* Header */}
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => setSelectedRun(null)}
                        className="inline-flex items-center px-3 py-2 text-sm text-gray-600 hover:text-gray-900 border border-gray-300 rounded-md cursor-pointer"
                    >
                        <ArrowLeft className="w-4 h-4 mr-1" /> Back
                    </button>
                    <div>
                        <h2 className="text-2xl font-bold text-gray-900">
                            Execution Run #{selectedRun.id}
                        </h2>
                        <p className="text-sm text-gray-500">
                            Policy: <span className="font-medium text-gray-700">{selectedRun.policy_name}</span>
                            &nbsp;·&nbsp;Triggered by {selectedRun.triggered_by}
                        </p>
                    </div>
                </div>

                {/* Stats row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-4">
                    <Stat label="Status" value={selectedRun.status} color={statusColor[selectedRun.status]} />
                    <Stat label="Started" value={formatDate(selectedRun.started_at)} />
                    <Stat label="Duration" value={duration(selectedRun.started_at, selectedRun.completed_at)} />
                    {selectedRun.summary && (
                        <>
                            <Stat label="Success" value={`${selectedRun.summary.success}`} color="bg-green-50 text-green-700" />
                            <Stat label="Failed" value={`${selectedRun.summary.failed}`} color={selectedRun.summary.failed > 0 ? "bg-red-50 text-red-700" : undefined} />
                            <Stat label="Skipped" value={`${selectedRun.summary.skipped + selectedRun.summary.condition_not_met}`} />
                        </>
                    )}
                </div>

                {/* DAG with execution overlay */}
                {selectedRun.execution_dag && (
                    <div className="bg-white shadow sm:rounded-lg p-4">
                        <h3 className="text-sm font-medium text-gray-700 mb-3">Execution Graph</h3>
                        <DAGView
                            dag={selectedRun.execution_dag}
                            steps={selectedRun.steps}
                            height="500px"
                        />
                    </div>
                )}

                {/* Steps table */}
                <div className="bg-white shadow overflow-hidden sm:rounded-lg">
                    <div className="px-4 py-4 border-b border-gray-200">
                        <h3 className="text-sm font-medium text-gray-700">Step Details</h3>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 text-sm">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-4 py-2 text-left font-medium text-gray-500">Node</th>
                                    <th className="px-4 py-2 text-left font-medium text-gray-500">Device</th>
                                    <th className="px-4 py-2 text-left font-medium text-gray-500">Capability</th>
                                    <th className="px-4 py-2 text-left font-medium text-gray-500">Status</th>
                                    <th className="px-4 py-2 text-left font-medium text-gray-500">HTTP</th>
                                    <th className="px-4 py-2 text-left font-medium text-gray-500">Duration</th>
                                    <th className="px-4 py-2 text-left font-medium text-gray-500">Response / Error</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                                {selectedRun.steps.map((step) => (
                                    <tr key={step.id} className="hover:bg-gray-50">
                                        <td className="px-4 py-2 font-mono text-xs">{step.node_id}</td>
                                        <td className="px-4 py-2">{step.device_name}</td>
                                        <td className="px-4 py-2">{step.capability_name}</td>
                                        <td className="px-4 py-2">
                                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${stepStatusColor(step.status)}`}>
                                                <StatusIcon status={step.status} />
                                                {step.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-2 font-mono text-xs">{step.http_status_code ?? "—"}</td>
                                        <td className="px-4 py-2 text-xs">{duration(step.started_at, step.completed_at)}</td>
                                        <td className="px-4 py-2 text-xs max-w-xs truncate">
                                            {step.error_message ? (
                                                <span className="text-red-600">{step.error_message}</span>
                                            ) : step.response_data ? (
                                                <span className="text-gray-600 font-mono">{JSON.stringify(step.response_data).slice(0, 120)}</span>
                                            ) : "—"}
                                        </td>
                                    </tr>
                                ))}
                                {selectedRun.steps.length === 0 && (
                                    <tr>
                                        <td colSpan={7} className="px-4 py-6 text-center text-gray-500">
                                            No steps recorded yet.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        );
    }

    // ─── List View ────────────────────────────────────────────
    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-900">Execution History</h2>
                <button
                    onClick={() => {
                        setLoading(true);
                        fetchRuns();
                    }}
                    className="inline-flex items-center px-3 py-2 text-sm border border-gray-300 rounded-md text-gray-600 hover:text-gray-900 cursor-pointer"
                >
                    <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </button>
            </div>

            <div className="bg-white shadow overflow-hidden sm:rounded-lg">
                {loading && runs.length === 0 ? (
                    <div className="flex justify-center items-center py-20 text-gray-400">
                        <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading...
                    </div>
                ) : runs.length === 0 ? (
                    <div className="text-center py-20 text-gray-500">
                        <Clock className="mx-auto h-10 w-10 text-gray-300 mb-3" />
                        <p className="font-medium">No executions yet</p>
                        <p className="text-sm mt-1">Execute a policy from the Policies page to see results here.</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 text-sm">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-4 py-3 text-left font-medium text-gray-500">Run</th>
                                    <th className="px-4 py-3 text-left font-medium text-gray-500">Policy</th>
                                    <th className="px-4 py-3 text-left font-medium text-gray-500">Status</th>
                                    <th className="px-4 py-3 text-left font-medium text-gray-500">Trigger</th>
                                    <th className="px-4 py-3 text-left font-medium text-gray-500">Started</th>
                                    <th className="px-4 py-3 text-left font-medium text-gray-500">Duration</th>
                                    <th className="px-4 py-3 text-left font-medium text-gray-500">Results</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                                {runs.map((run) => (
                                    <tr
                                        key={run.id}
                                        onClick={() => openDetail(run.id)}
                                        className="hover:bg-indigo-50 cursor-pointer transition-colors"
                                    >
                                        <td className="px-4 py-3 font-mono text-xs text-gray-600">#{run.id}</td>
                                        <td className="px-4 py-3 font-medium text-indigo-600">{run.policy_name}</td>
                                        <td className="px-4 py-3">
                                            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${statusColor[run.status] || "bg-gray-100 text-gray-700"}`}>
                                                <StatusIcon status={run.status} />
                                                {run.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-gray-500 capitalize">{run.triggered_by}</td>
                                        <td className="px-4 py-3 text-gray-500">{formatDate(run.started_at)}</td>
                                        <td className="px-4 py-3 text-gray-500">{duration(run.started_at, run.completed_at)}</td>
                                        <td className="px-4 py-3">
                                            {run.summary ? (
                                                <div className="flex gap-2 text-xs">
                                                    <span className="text-green-600 font-medium">{run.summary.success} ok</span>
                                                    {run.summary.failed > 0 && (
                                                        <span className="text-red-600 font-medium">{run.summary.failed} fail</span>
                                                    )}
                                                    {(run.summary.skipped + run.summary.condition_not_met) > 0 && (
                                                        <span className="text-gray-400">{run.summary.skipped + run.summary.condition_not_met} skip</span>
                                                    )}
                                                </div>
                                            ) : (
                                                <span className="text-gray-400 text-xs">—</span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Loading overlay for detail fetch */}
            {detailLoading && (
                <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg px-6 py-4 shadow-lg flex items-center gap-3">
                        <Loader2 className="w-5 h-5 animate-spin text-indigo-600" />
                        <span className="text-sm text-gray-700">Loading execution details...</span>
                    </div>
                </div>
            )}
        </div>
    );
}

// ─── Helper sub-components ────────────────────────────────────

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
    return (
        <div className={`rounded-lg px-4 py-3 ${color ?? "bg-gray-50 text-gray-700"}`}>
            <p className="text-xs uppercase tracking-wide opacity-70">{label}</p>
            <p className="text-lg font-semibold mt-0.5 capitalize">{value}</p>
        </div>
    );
}

function stepStatusColor(status: string): string {
    switch (status) {
        case "success":
            return "bg-green-100 text-green-700";
        case "failed":
            return "bg-red-100 text-red-700";
        case "running":
            return "bg-blue-100 text-blue-700";
        case "skipped":
            return "bg-gray-100 text-gray-500";
        case "condition_not_met":
            return "bg-orange-100 text-orange-700";
        default:
            return "bg-gray-100 text-gray-700";
    }
}
