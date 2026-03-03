"use client";
import { useState, useEffect } from 'react';
import api, { Policy } from '@/lib/api';
import { Clock } from 'lucide-react';

function getPolicyDeviceNames(policy: Policy): string[] {
    const plan = policy.execution_plan;
    if (!plan) return [];

    // New DAG format
    if (!Array.isArray(plan) && typeof plan === 'object' && 'nodes' in plan && Array.isArray(plan.nodes)) {
        const names = plan.nodes
            .map((node) => node?.device)
            .filter((name): name is string => typeof name === 'string' && name.trim().length > 0);
        return Array.from(new Set(names));
    }

    // Legacy flat list format
    if (Array.isArray(plan)) {
        const names = plan
            .map((action) => action?.device)
            .filter((name): name is string => typeof name === 'string' && name.trim().length > 0);
        return Array.from(new Set(names));
    }

    return [];
}

export default function SchedulePage() {
    const [policies, setPolicies] = useState<Policy[]>([]);

    useEffect(() => {
        const fetchPolicies = async () => {
            try {
                const res = await api.get('/policies/');
                setPolicies(res.data);
            } catch (error) {
                console.error("Failed to fetch policies", error);
            }
        };
        fetchPolicies();
    }, []);

    // Sort policies by start time
    const sortedPolicies = [...policies].sort((a, b) => a.start_time.localeCompare(b.start_time));

    return (
        <div className="space-y-6">
            <div className="md:flex md:items-center md:justify-between">
                <div className="flex-1 min-w-0">
                    <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
                        Schedule Dashboard
                    </h2>
                </div>
            </div>

            <div className="bg-white shadow overflow-hidden sm:rounded-lg">
                <div className="px-4 py-5 sm:px-6">
                    <h3 className="text-lg leading-6 font-medium text-gray-900">Daily Schedule</h3>
                    <p className="mt-1 max-w-2xl text-sm text-gray-500">Timeline of active automation policies.</p>
                </div>
                <div className="border-t border-gray-200">
                    <dl>
                        {sortedPolicies.map((policy, index) => (
                            <div key={policy.id} className={`${index % 2 === 0 ? 'bg-gray-50' : 'bg-white'} px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6`}>
                                <dt className="text-sm font-medium text-gray-500 flex items-center">
                                    <Clock className="w-5 h-5 mr-2 text-indigo-500" />
                                    {policy.start_time} - {policy.end_time}
                                </dt>
                                <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                                    <div className="font-bold text-lg">{policy.name}</div>
                                    <div className="text-gray-600 mb-2">{policy.original_text}</div>
                                    <div className="flex flex-wrap gap-2">
                                        {getPolicyDeviceNames(policy).map((deviceName) => (
                                            <span key={deviceName} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                                                {deviceName}
                                            </span>
                                        ))}
                                    </div>
                                </dd>
                            </div>
                        ))}
                        {sortedPolicies.length === 0 && (
                            <div className="px-4 py-12 text-center text-gray-500">
                                No scheduled policies found.
                            </div>
                        )}
                    </dl>
                </div>
            </div>
        </div>
    );
}
