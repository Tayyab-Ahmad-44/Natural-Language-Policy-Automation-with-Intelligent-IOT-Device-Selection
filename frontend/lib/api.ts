import axios from 'axios';

const api = axios.create({
    baseURL: 'http://localhost:8000/api',
});

export interface Capability {
    id?: number;
    name: string;
    url: string;
    method: string;
    input_schema: any;
}

export interface Device {
    id: number;
    name: string;
    type: string;
    capabilities: Capability[];
}

export interface Policy {
    id: number;
    name: string;
    original_text: string;
    start_time: string;
    end_time: string;
    is_active: boolean;
    execution_plan: any[];
    task_id?: number;
}

export interface Task {
    id: number;
    name: string;
    description: string;
    created_at: string;
    policies: Policy[];
}

export default api;
