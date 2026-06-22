import { PolicyConflict } from '@/lib/api';
import { AlertTriangle, Lightbulb } from 'lucide-react';

const CONFLICT_STYLE: Record<string, string> = {
    high: 'border-red-300 bg-red-50',
    medium: 'border-amber-300 bg-amber-50',
    low: 'border-yellow-200 bg-yellow-50',
};

export default function ConflictCard({ conflict }: { conflict: PolicyConflict }) {
    const style = CONFLICT_STYLE[conflict.severity] ?? CONFLICT_STYLE.medium;
    return (
        <div className={`rounded-md border p-3 text-sm ${style}`}>
            <div className="flex items-center gap-2 font-medium text-gray-800 flex-wrap">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <span className="capitalize">{conflict.type}</span>
                <span className="text-xs px-1.5 py-0.5 rounded bg-white/70 border border-gray-300 capitalize">
                    {conflict.severity}
                </span>
                <span className="text-gray-500 font-normal truncate">
                    vs <span className="font-medium">{conflict.policy_name}</span>
                    {conflict.existing_window?.from_time &&
                        ` (${conflict.existing_window.from_time}–${conflict.existing_window.to_time})`}
                </span>
            </div>
            {conflict.new_policy_name && (
                <p className="mt-1 text-xs text-gray-500">New policy: {conflict.new_policy_name}</p>
            )}
            {conflict.explanation && <p className="mt-1 text-gray-700">{conflict.explanation}</p>}
            {conflict.shared_devices.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                    {conflict.shared_devices.map((d, i) => (
                        <span key={i} className="text-xs px-1.5 py-0.5 rounded bg-white/70 border border-gray-300">{d}</span>
                    ))}
                </div>
            )}
            {conflict.suggestion && (
                <p className="mt-2 text-xs text-gray-600 flex items-start gap-1">
                    <Lightbulb className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-amber-500" />
                    <span><span className="font-medium">Suggestion:</span> {conflict.suggestion}</span>
                </p>
            )}
        </div>
    );
}
