"use client";
import { useState, useEffect } from 'react';
import api, { Policy } from '@/lib/api';
import { Plus, Check, AlertCircle } from 'lucide-react';

export default function PoliciesPage() {
    const [policies, setPolicies] = useState<Policy[]>([]);
    const [policyInput, setPolicyInput] = useState('');
    const [policyName, setPolicyName] = useState('');
    const [preview, setPreview] = useState<any>(null);
    const [loading, setLoading] = useState(false);

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
            await api.post('/policies/', { name: policyName, original_text: policyInput });
            setPolicyName('');
            setPolicyInput('');
            setPreview(null);
            fetchPolicies();
        } catch (error) {
            console.error("Failed to create policy", error);
        } finally {
            setLoading(false);
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
                            <label className="block text-sm font-medium text-gray-700">Natural Language Rule</label>
                            <textarea
                                rows={4}
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                                placeholder="e.g. If someone enters Room2 from 10pm to 5am, ring the alarm of that room"
                                value={policyInput}
                                onChange={(e) => setPolicyInput(e.target.value)}
                            />
                        </div>
                        <div className="flex gap-3">
                            <button
                                onClick={handlePreview}
                                disabled={loading}
                                className="flex-1 inline-flex justify-center items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none"
                            >
                                {loading ? 'Processing...' : 'Preview Interpretation'}
                            </button>
                            {preview && (
                                <button
                                    onClick={handleCreate}
                                    disabled={loading || !policyName}
                                    className="flex-1 inline-flex justify-center items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none"
                                >
                                    <Plus className="w-4 h-4 mr-2" />
                                    Save Policy
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                <div className="bg-white shadow sm:rounded-lg p-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">Interpretation Preview</h3>
                    {preview ? (
                        <div className="bg-green-50 border border-green-200 rounded-md p-4">
                            <div className="flex">
                                <div className="flex-shrink-0">
                                    <Check className="h-5 w-5 text-green-400" />
                                </div>
                                <div className="ml-3 w-full">
                                    <h3 className="text-sm font-medium text-green-800">Successfully parsed</h3>
                                    <div className="mt-2 text-sm text-green-700">
                                        <p><strong>Time Window:</strong> {preview.time_window.from_time} - {preview.time_window.to_time}</p>
                                        <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-green-800">Execution Plan</p>
                                        <div className="mt-1 space-y-2">
                                            {preview.execution_plan.map((action: any, idx: number) => (
                                                <div key={idx} className="bg-white p-2 rounded border border-green-200 shadow-sm">
                                                    <div className="flex justify-between">
                                                        <span className="font-bold text-indigo-600">{action.device}</span>
                                                        <span className="text-gray-500 text-xs">{action.capability}</span>
                                                    </div>
                                                    <div className="mt-1 text-xs text-gray-600 font-mono">
                                                        {JSON.stringify(action.args)}
                                                    </div>
                                                </div>
                                            ))}
                                            {preview.execution_plan.length === 0 && (
                                                <p className="text-gray-500 italic">No actions inferred.</p>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="text-center py-12 text-gray-500 bg-gray-50 rounded-md border-2 border-dashed border-gray-200">
                            <AlertCircle className="mx-auto h-8 w-8 text-gray-400" />
                            <p className="mt-2">Enter a policy and click Preview to see how the AI interprets it.</p>
                        </div>
                    )}
                </div>
            </div>

            <div className="bg-white shadow overflow-hidden sm:rounded-md mt-6">
                <div className="px-4 py-5 sm:px-6 border-b border-gray-200">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">Active Policies</h3>
                </div>
                <ul className="divide-y divide-gray-200">
                    {policies.map((policy) => (
                        <li key={policy.id} className="px-4 py-4 sm:px-6 hover:bg-gray-50">
                            <div className="flex items-center justify-between">
                                <div className="flex flex-col">
                                    <p className="text-sm font-medium text-indigo-600 truncate">{policy.name}</p>
                                    <p className="text-sm text-gray-500">{policy.original_text}</p>
                                </div>
                                <div className="flex items-center gap-4">
                                    <div className="flex flex-col items-end">
                                        <p className="text-sm text-gray-900 font-bold">{policy.start_time} - {policy.end_time}</p>
                                        <p className="text-xs text-gray-500">{policy.execution_plan?.length || 0} actions</p>
                                    </div>
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
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    );
}
