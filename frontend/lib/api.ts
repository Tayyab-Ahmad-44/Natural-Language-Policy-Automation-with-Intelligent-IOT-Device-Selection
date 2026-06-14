import axios from 'axios';

const api = axios.create({
    baseURL: 'http://localhost:8000/api',
});

// ─── Device / Capability ──────────────────────────────────────────

export interface Capability {
    id?: number;
    name: string;
    url: string;
    method: string;
    input_schema: unknown;
}

export interface Device {
    id: number;
    name: string;
    type: string;
    capabilities: Capability[];
}

// ─── DAG Types ────────────────────────────────────────────────────

export interface ExecutionCondition {
    type: 'on_success' | 'on_failure' | 'on_value' | 'all' | 'any';
    source_node_id?: string;
    field?: string;
    operator?: '>' | '<' | '==' | '!=' | '>=' | '<=' | 'contains';
    value?: unknown;
    conditions?: ExecutionCondition[];
}

export interface ExecutionNode {
    id: string;
    device: string;
    capability: string;
    args: Record<string, unknown>;
    dependencies: string[];
    condition?: ExecutionCondition | null;
    on_failure: 'halt_branch' | 'skip_dependents' | 'ignore';
}

export interface ExecutionDAG {
    nodes: ExecutionNode[];
}

export interface DAGValidation {
    valid: boolean;
    errors: string[];
}

export interface PolicyPreviewResponse {
    execution_dag: ExecutionDAG;
    time_window: { from_time: string; to_time: string };
    validation: DAGValidation;
    levels: string[][];
}

// ─── Policy ───────────────────────────────────────────────────────

export interface Policy {
    id: number;
    name: string;
    original_text: string;
    start_time: string;
    end_time: string;
    is_active: boolean;
    repeat_interval_seconds?: number | null;
    last_executed_at?: string | null;
    execution_plan: ExecutionDAG | Record<string, unknown>[];  // DAG format or legacy flat list
    task_id?: number;
}

// ─── Task ─────────────────────────────────────────────────────────

export interface Task {
    id: number;
    name: string;
    description: string;
    created_at: string;
    policies: Policy[];
}

// ─── Execution Tracking ──────────────────────────────────────────

export interface ExecutionStep {
    id: number;
    run_id: number;
    node_id: string;
    device_name: string;
    capability_name: string;
    args: Record<string, unknown>;
    status: 'pending' | 'running' | 'success' | 'failed' | 'skipped' | 'condition_not_met';
    started_at?: string;
    completed_at?: string;
    response_data?: Record<string, unknown>;
    error_message?: string;
    http_status_code?: number;
}

export interface ExecutionRun {
    id: number;
    policy_id: number;
    policy_name: string;
    status: 'pending' | 'running' | 'completed' | 'partial_failure' | 'failed';
    triggered_by: 'scheduler' | 'manual';
    started_at?: string;
    completed_at?: string;
    summary?: {
        total: number;
        success: number;
        failed: number;
        skipped: number;
        condition_not_met: number;
    };
}

export interface ExecutionRunDetail extends ExecutionRun {
    steps: ExecutionStep[];
    execution_dag?: ExecutionDAG;
}

// ─── Sensor Readings ─────────────────────────────────────────────

export interface SensorReadingResponse {
    id: number;
    device_id: number;
    device_name: string;
    capability_name: string;
    data: unknown;
    received_at: string;
}

// ─── API Functions ───────────────────────────────────────────────

export async function previewPolicy(name: string, original_text: string): Promise<PolicyPreviewResponse> {
    const resp = await api.post('/policies/preview', { name, original_text });
    return resp.data;
}

export async function executePolicy(policyId: number): Promise<ExecutionRunDetail> {
    const resp = await api.post(`/policies/${policyId}/execute`);
    return resp.data;
}

export async function getExecutions(policyId?: number): Promise<ExecutionRun[]> {
    const params = policyId ? { policy_id: policyId } : {};
    const resp = await api.get('/executions/', { params });
    return resp.data;
}

export async function getExecutionDetail(runId: number): Promise<ExecutionRunDetail> {
    const resp = await api.get(`/executions/${runId}`);
    return resp.data;
}

export function streamExecution(runId: number): EventSource {
    return new EventSource(`http://localhost:8000/api/executions/${runId}/stream`);
}

export function streamPolicyExecution(policyId: number): EventSource {
    // Note: SSE POST isn't standard with EventSource. For live execute, use the
    // non-streaming endpoint and then poll, or use fetch with ReadableStream.
    return new EventSource(`http://localhost:8000/api/executions/${policyId}/stream`);
}

export default api;
