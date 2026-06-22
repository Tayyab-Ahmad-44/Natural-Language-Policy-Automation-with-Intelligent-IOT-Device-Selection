"use client";
import { useEffect, useRef, useState } from 'react';
import { getVlmSamples, testVlm, VlmSample, VlmResult } from '@/lib/api';
import { Camera, Loader2, Upload, CheckCircle2, XCircle } from 'lucide-react';

type Source = 'upload' | 'sample' | 'url';

export default function VlmTestPanel() {
    const [open, setOpen] = useState(false);

    const [source, setSource] = useState<Source>('sample');
    const [file, setFile] = useState<File | null>(null);
    const [samples, setSamples] = useState<VlmSample[]>([]);
    const [selectedSample, setSelectedSample] = useState('');
    const [url, setUrl] = useState('');
    const [urlIsVideo, setUrlIsVideo] = useState(false);

    const [prompt, setPrompt] = useState('Detect whether smoke or fire is visible');
    const [labels, setLabels] = useState('fire, smoke');
    const [provider, setProvider] = useState('');

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<VlmResult | null>(null);

    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (!open) return;
        getVlmSamples()
            .then((s) => {
                setSamples(s);
                if (s.length > 0 && !selectedSample) setSelectedSample(s[0].name);
            })
            .catch(() => setSamples([]));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    const handleRun = async () => {
        setError(null);
        setResult(null);

        const form = new FormData();
        if (source === 'upload') {
            if (!file) { setError('Choose an image or video file to upload.'); return; }
            form.append('file', file);
        } else if (source === 'sample') {
            if (!selectedSample) { setError('Pick a bundled sample.'); return; }
            form.append('sample', selectedSample);
        } else {
            if (!url.trim()) { setError('Enter an image or video URL.'); return; }
            form.append(urlIsVideo ? 'video_url' : 'image_url', url.trim());
        }
        form.append('prompt', prompt);
        if (labels.trim()) form.append('labels', labels);
        if (provider) form.append('provider', provider);

        setLoading(true);
        try {
            const res = await testVlm(form);
            setResult(res);
        } catch (e: unknown) {
            const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
            setError(detail || 'VLM analysis failed.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="bg-white shadow sm:rounded-lg p-6">
            <button
                type="button"
                onClick={() => setOpen(!open)}
                className="flex items-center gap-2 text-lg leading-6 font-medium text-gray-900 w-full text-left"
            >
                <Camera className="w-5 h-5 text-indigo-600" />
                Test Camera VLM
                <span className="ml-auto text-sm text-gray-400">{open ? 'Hide' : 'Show'}</span>
            </button>

            {open && (
                <div className="mt-4 space-y-4">
                    <p className="text-sm text-gray-500">
                        Feed an image or video to the vision model and see the structured detection
                        result — the same JSON a <span className="font-medium">VLM</span> capability
                        produces during policy execution.
                    </p>

                    {/* Source selector */}
                    <div className="flex gap-2 border-b border-gray-200">
                        {(['sample', 'upload', 'url'] as Source[]).map((s) => (
                            <button
                                key={s}
                                type="button"
                                onClick={() => setSource(s)}
                                className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px capitalize ${source === s
                                    ? 'border-indigo-600 text-indigo-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                            >
                                {s === 'sample' ? 'Bundled sample' : s === 'upload' ? 'Upload file' : 'From URL'}
                            </button>
                        ))}
                    </div>

                    {source === 'sample' && (
                        <div>
                            <label className="block text-sm font-medium text-gray-700">test_media sample</label>
                            <select
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 sm:text-sm text-black"
                                value={selectedSample}
                                onChange={(e) => setSelectedSample(e.target.value)}
                            >
                                {samples.length === 0 && <option value="">No samples found</option>}
                                {samples.map((s) => (
                                    <option key={s.name} value={s.name}>{s.name} ({s.type})</option>
                                ))}
                            </select>
                        </div>
                    )}

                    {source === 'upload' && (
                        <div>
                            <label className="block text-sm font-medium text-gray-700">Image or video file</label>
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="image/*,video/*"
                                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                                className="hidden"
                            />
                            <button
                                type="button"
                                onClick={() => fileInputRef.current?.click()}
                                className="mt-1 inline-flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
                            >
                                <Upload className="w-4 h-4" />
                                {file ? file.name : 'Choose file…'}
                            </button>
                        </div>
                    )}

                    {source === 'url' && (
                        <div className="space-y-2">
                            <label className="block text-sm font-medium text-gray-700">Image or video URL</label>
                            <input
                                type="url"
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 sm:text-sm text-black"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                placeholder="https://…/frame.jpg"
                            />
                            <label className="inline-flex items-center gap-2 text-sm text-gray-600">
                                <input type="checkbox" checked={urlIsVideo} onChange={(e) => setUrlIsVideo(e.target.checked)} />
                                This URL is a video (sample frames)
                            </label>
                        </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="md:col-span-2">
                            <label className="block text-sm font-medium text-gray-700">Prompt</label>
                            <input
                                type="text"
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 sm:text-sm text-black"
                                value={prompt}
                                onChange={(e) => setPrompt(e.target.value)}
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700">Provider</label>
                            <select
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 sm:text-sm text-black"
                                value={provider}
                                onChange={(e) => setProvider(e.target.value)}
                            >
                                <option value="">Default (server)</option>
                                <option value="gemini">Gemini</option>
                                <option value="groq">Groq</option>
                            </select>
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700">Target labels (optional, comma-separated)</label>
                        <input
                            type="text"
                            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 sm:text-sm text-black"
                            value={labels}
                            onChange={(e) => setLabels(e.target.value)}
                            placeholder="fire, smoke, person"
                        />
                    </div>

                    <button
                        type="button"
                        onClick={handleRun}
                        disabled={loading}
                        className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60"
                    >
                        {loading
                            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Analyzing…</>
                            : <><Camera className="w-4 h-4 mr-2" /> Run Analysis</>}
                    </button>

                    {error && (
                        <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">{error}</div>
                    )}

                    {result && (
                        <div className="rounded-md border border-gray-200 p-4 space-y-3">
                            <div className="flex items-center gap-3">
                                {result.detected
                                    ? <CheckCircle2 className="w-6 h-6 text-green-600" />
                                    : <XCircle className="w-6 h-6 text-gray-400" />}
                                <span className={`font-semibold ${result.detected ? 'text-green-700' : 'text-gray-600'}`}>
                                    {result.detected ? 'Detected' : 'Not detected'}
                                </span>
                                <span className="ml-auto text-sm text-gray-500">
                                    confidence {(result.confidence * 100).toFixed(0)}%
                                </span>
                            </div>
                            {result.summary && <p className="text-sm text-gray-700">{result.summary}</p>}
                            {result.labels.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                    {result.labels.map((l, i) => (
                                        <span key={i} className="px-2 py-0.5 rounded bg-indigo-100 text-indigo-700 text-xs">{l}</span>
                                    ))}
                                </div>
                            )}
                            <p className="text-xs text-gray-400">{result.provider} · {result.model}</p>
                            <details className="text-xs text-gray-500">
                                <summary className="cursor-pointer select-none">Raw JSON</summary>
                                <pre className="mt-2 bg-gray-900 text-gray-100 p-3 rounded-md overflow-x-auto max-h-72">
{JSON.stringify(result, null, 2)}
                                </pre>
                            </details>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
