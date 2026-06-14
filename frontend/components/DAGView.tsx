"use client";

import React, { useMemo } from "react";
import {
    ReactFlow,
    Background,
    Controls,
    Handle,
    Position,
    type Node,
    type Edge,
    type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";
import type { ExecutionDAG, ExecutionNode, ExecutionStep } from "@/lib/api";

// ─── Status colors ───────────────────────────────────────────────

const STATUS_COLORS: Record<string, { bg: string; border: string; text: string }> = {
    pending: { bg: "bg-gray-50", border: "border-gray-300", text: "text-gray-600" },
    running: { bg: "bg-blue-50", border: "border-blue-400", text: "text-blue-700" },
    success: { bg: "bg-green-50", border: "border-green-400", text: "text-green-700" },
    failed: { bg: "bg-red-50", border: "border-red-400", text: "text-red-700" },
    skipped: { bg: "bg-gray-100", border: "border-gray-300 border-dashed", text: "text-gray-400" },
    condition_not_met: { bg: "bg-orange-50", border: "border-orange-300", text: "text-orange-600" },
    default: { bg: "bg-white", border: "border-indigo-300", text: "text-gray-800" },
};

const FAILURE_BADGES: Record<string, { label: string; color: string }> = {
    halt_branch: { label: "HALT", color: "bg-red-100 text-red-700" },
    skip_dependents: { label: "SKIP", color: "bg-yellow-100 text-yellow-700" },
    ignore: { label: "IGN", color: "bg-gray-100 text-gray-500" },
};

function conditionLabel(condition: ExecutionNode["condition"]): string {
    if (!condition) return "";
    if (condition.type === "on_value") {
        return `if ${condition.field} ${condition.operator} ${String(condition.value)}`;
    }
    if (condition.type === "all" || condition.type === "any") {
        const parts = condition.conditions?.map(conditionLabel).filter(Boolean) || [];
        return `${condition.type.toUpperCase()}(${parts.join(", ")})`;
    }
    return condition.type.replace("_", " ");
}

// ─── Custom Node Component ──────────────────────────────────────

interface DeviceNodeData {
    dagNode: ExecutionNode;
    step?: ExecutionStep;
    [key: string]: unknown;
}

function DeviceActionNode({ data }: NodeProps<Node<DeviceNodeData>>) {
    const { dagNode, step } = data;
    const status = step?.status || "default";
    const colors = STATUS_COLORS[status] || STATUS_COLORS.default;
    const failureBadge = FAILURE_BADGES[dagNode.on_failure];

    const conditionText = conditionLabel(dagNode.condition);

    return (
        <div className={`px-4 py-3 rounded-xl border-2 shadow-sm min-w-[200px] ${colors.bg} ${colors.border}`}>
            <Handle type="target" position={Position.Top} className="!bg-indigo-400 !w-3 !h-3" />

            {/* Header */}
            <div className="flex items-center justify-between mb-1">
                <span className={`text-xs font-mono ${colors.text} opacity-60`}>{dagNode.id}</span>
                {failureBadge && (
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${failureBadge.color}`}>
                        {failureBadge.label}
                    </span>
                )}
            </div>

            {/* Device + Capability */}
            <div className={`font-semibold text-sm ${colors.text}`}>{dagNode.device}</div>
            <div className={`text-xs ${colors.text} opacity-80`}>{dagNode.capability}</div>

            {/* Args summary */}
            {Object.keys(dagNode.args).length > 0 && (
                <div className="mt-1.5 text-[11px] bg-white/60 rounded px-2 py-1 font-mono text-gray-600 max-w-[220px] truncate">
                    {Object.entries(dagNode.args)
                        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
                        .join(", ")}
                </div>
            )}

            {/* Condition badge */}
            {conditionText && (
                <div className="mt-1.5 text-[10px] bg-yellow-50 border border-yellow-200 rounded px-2 py-0.5 text-yellow-700">
                    {conditionText}
                </div>
            )}

            {/* Execution status */}
            {step && (
                <div className="mt-2 flex items-center gap-2">
                    <span className={`inline-block w-2 h-2 rounded-full ${status === "running" ? "bg-blue-500 animate-pulse" :
                            status === "success" ? "bg-green-500" :
                                status === "failed" ? "bg-red-500" :
                                    status === "skipped" ? "bg-gray-400" :
                                        status === "condition_not_met" ? "bg-orange-400" :
                                            "bg-gray-300"
                        }`} />
                    <span className={`text-[10px] font-medium uppercase ${colors.text}`}>{status.replace("_", " ")}</span>
                    {step.http_status_code && (
                        <span className="text-[10px] font-mono text-gray-400">HTTP {step.http_status_code}</span>
                    )}
                </div>
            )}

            {/* Error message */}
            {step?.error_message && (
                <div className="mt-1 text-[10px] text-red-600 bg-red-50 rounded px-2 py-0.5 truncate max-w-[220px]" title={step.error_message}>
                    {step.error_message}
                </div>
            )}

            <Handle type="source" position={Position.Bottom} className="!bg-indigo-400 !w-3 !h-3" />
        </div>
    );
}

// ─── Layout with dagre ──────────────────────────────────────────

const NODE_WIDTH = 240;
const NODE_HEIGHT = 140;

function getLayoutedElements(nodes: Node<DeviceNodeData>[], edges: Edge[], direction: "TB" | "LR" = "TB") {
    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: direction, ranksep: 80, nodesep: 40 });

    nodes.forEach((node) => {
        g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
    });

    edges.forEach((edge) => {
        g.setEdge(edge.source, edge.target);
    });

    dagre.layout(g);

    const layoutedNodes = nodes.map((node) => {
        const pos = g.node(node.id);
        return {
            ...node,
            position: {
                x: pos.x - NODE_WIDTH / 2,
                y: pos.y - NODE_HEIGHT / 2,
            },
        };
    });

    return { nodes: layoutedNodes, edges };
}

// ─── DAG → React Flow conversion ───────────────────────────────

function dagToFlow(
    dag: ExecutionDAG,
    steps?: ExecutionStep[]
): { nodes: Node<DeviceNodeData>[]; edges: Edge[] } {
    const stepMap = new Map<string, ExecutionStep>();
    if (steps) {
        steps.forEach((s) => stepMap.set(s.node_id, s));
    }

    const nodes: Node<DeviceNodeData>[] = dag.nodes.map((dagNode) => ({
        id: dagNode.id,
        type: "deviceAction",
        position: { x: 0, y: 0 }, // will be set by dagre
        data: {
            dagNode,
            step: stepMap.get(dagNode.id),
        },
    }));

    const edges: Edge[] = [];
    dag.nodes.forEach((dagNode) => {
        dagNode.dependencies.forEach((depId) => {
            const edgeId = `${depId}->${dagNode.id}`;

            // Label for condition edges
            let label = "";
            if (dagNode.condition?.type === "on_value" && dagNode.condition.source_node_id === depId) {
                label = `${dagNode.condition.field} ${dagNode.condition.operator} ${dagNode.condition.value}`;
            } else if (dagNode.condition?.type === "all" || dagNode.condition?.type === "any") {
                label = dagNode.condition.type.toUpperCase();
            } else if (dagNode.condition?.type === "on_failure") {
                label = "on failure";
            }

            edges.push({
                id: edgeId,
                source: depId,
                target: dagNode.id,
                label: label || undefined,
                animated: dagNode.condition?.type === "on_value" || dagNode.condition?.type === "all" || dagNode.condition?.type === "any",
                style: {
                    stroke: dagNode.condition?.type === "on_value" || dagNode.condition?.type === "all" || dagNode.condition?.type === "any" ? "#f59e0b" :
                        dagNode.condition?.type === "on_failure" ? "#ef4444" : "#6366f1",
                    strokeWidth: 2,
                },
                labelStyle: {
                    fontSize: 10,
                    fontWeight: 600,
                    fill: dagNode.condition?.type === "on_value" || dagNode.condition?.type === "all" || dagNode.condition?.type === "any" ? "#92400e" : "#4338ca",
                },
                labelBgStyle: {
                    fill: dagNode.condition?.type === "on_value" || dagNode.condition?.type === "all" || dagNode.condition?.type === "any" ? "#fef3c7" : "#eef2ff",
                    fillOpacity: 0.9,
                },
                labelBgPadding: [6, 3] as [number, number],
                labelBgBorderRadius: 4,
            });
        });
    });

    return getLayoutedElements(nodes, edges);
}

// ─── nodeTypes registration ──────────────────────────────────────

const nodeTypes = { deviceAction: DeviceActionNode };

// ─── Main Component ──────────────────────────────────────────────

interface DAGViewProps {
    dag: ExecutionDAG;
    steps?: ExecutionStep[];
    height?: string;
}

export default function DAGView({ dag, steps, height = "500px" }: DAGViewProps) {
    const { nodes, edges } = useMemo(() => dagToFlow(dag, steps), [dag, steps]);

    if (!dag.nodes || dag.nodes.length === 0) {
        return (
            <div className="flex items-center justify-center border-2 border-dashed border-gray-300 rounded-xl p-8 text-gray-400">
                No execution nodes in DAG
            </div>
        );
    }

    return (
        <div style={{ height }} className="border border-gray-200 rounded-xl overflow-hidden bg-gray-50">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                fitView
                attributionPosition="bottom-left"
                minZoom={0.3}
                maxZoom={1.5}
                nodesDraggable={true}
                nodesConnectable={false}
                proOptions={{ hideAttribution: true }}
            >
                <Background color="#e5e7eb" gap={20} />
                <Controls showInteractive={false} />
            </ReactFlow>
        </div>
    );
}
