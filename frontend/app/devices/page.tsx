"use client";
import { useState, useEffect } from 'react';
import api, { Device, Capability, DeviceDraft, discoverDevices, bulkCreateDevices } from '@/lib/api';
import { Plus, Server, Trash2, Pencil, Radar, Loader2 } from 'lucide-react';

export default function DevicesPage() {
    const [devices, setDevices] = useState<Device[]>([]);
    const [newDeviceName, setNewDeviceName] = useState('');
    const [newDeviceType, setNewDeviceType] = useState('camera');
    const [loading, setLoading] = useState(true);

    // Registration mode: type it in by hand, or auto-discover from an endpoint
    const [mode, setMode] = useState<'manual' | 'discover'>('manual');

    // Auto-discovery state
    const [discoverEndpoint, setDiscoverEndpoint] = useState('');
    const [discoverHeaders, setDiscoverHeaders] = useState('');
    const [discovering, setDiscovering] = useState(false);
    const [discoverError, setDiscoverError] = useState<string | null>(null);
    const [discoverWarning, setDiscoverWarning] = useState<string | null>(null);
    const [discoveredDevices, setDiscoveredDevices] = useState<DeviceDraft[]>([]);
    const [rawSample, setRawSample] = useState<string | null>(null);
    const [importing, setImporting] = useState(false);

    // Capabilities state
    const [capabilities, setCapabilities] = useState<Capability[]>([]);
    const [newCapName, setNewCapName] = useState('');
    const [newCapUrl, setNewCapUrl] = useState('');
    const [newCapMethod, setNewCapMethod] = useState('GET');
    const [newCapSchema, setNewCapSchema] = useState('{}');

    // Edit state
    const [editingDevice, setEditingDevice] = useState<Device | null>(null);
    const [editDeviceName, setEditDeviceName] = useState('');
    const [editDeviceType, setEditDeviceType] = useState('camera');
    const [editCapabilities, setEditCapabilities] = useState<Capability[]>([]);
    const [editNewCapName, setEditNewCapName] = useState('');
    const [editNewCapUrl, setEditNewCapUrl] = useState('');
    const [editNewCapMethod, setEditNewCapMethod] = useState('GET');
    const [editNewCapSchema, setEditNewCapSchema] = useState('{}');

    useEffect(() => {
        fetchDevices();
    }, []);

    const fetchDevices = async () => {
        try {
            const res = await api.get('/devices/');
            setDevices(res.data);
        } catch (error) {
            console.error("Failed to fetch devices", error);
        } finally {
            setLoading(false);
        }
    };

    const addCapability = () => {
        try {
            const schema = JSON.parse(newCapSchema);
            setCapabilities([...capabilities, {
                name: newCapName,
                url: newCapUrl,
                method: newCapMethod,
                input_schema: schema
            }]);
            setNewCapName('');
            setNewCapUrl('');
            setNewCapSchema('{}');
        } catch {
            alert("Invalid JSON schema");
        }
    };

    const removeCapability = (index: number) => {
        const newCaps = [...capabilities];
        newCaps.splice(index, 1);
        setCapabilities(newCaps);
    };

    const handleAddDevice = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await api.post('/devices/', {
                name: newDeviceName,
                type: newDeviceType,
                capabilities: capabilities
            });
            setNewDeviceName('');
            setCapabilities([]);
            fetchDevices();
        } catch (error) {
            console.error("Failed to add device", error);
            alert("Failed to add device. Name might be duplicate.");
        }
    };

    const handleDiscover = async (e: React.FormEvent) => {
        e.preventDefault();
        setDiscoverError(null);
        setDiscoverWarning(null);
        setDiscoveredDevices([]);
        setRawSample(null);

        // Optional headers are entered as JSON; ignore if blank, reject if malformed.
        let headers: Record<string, string> | undefined;
        if (discoverHeaders.trim()) {
            try {
                headers = JSON.parse(discoverHeaders);
            } catch {
                setDiscoverError('Headers must be valid JSON, e.g. {"Authorization": "Bearer ..."}');
                return;
            }
        }

        setDiscovering(true);
        try {
            const res = await discoverDevices(discoverEndpoint.trim(), headers);
            setDiscoveredDevices(res.devices);
            setRawSample(res.raw_sample ?? null);
            setDiscoverWarning(res.warning ?? null);
        } catch (error: unknown) {
            const detail =
                (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
            setDiscoverError(detail || 'Failed to fetch or analyze the endpoint.');
        } finally {
            setDiscovering(false);
        }
    };

    const removeDiscoveredDevice = (index: number) => {
        setDiscoveredDevices(discoveredDevices.filter((_, i) => i !== index));
    };

    const handleImportDiscovered = async () => {
        if (discoveredDevices.length === 0) return;
        setImporting(true);
        try {
            const res = await bulkCreateDevices(discoveredDevices);
            let message = `Imported ${res.created.length} device(s).`;
            if (res.skipped.length > 0) {
                message += ` Skipped ${res.skipped.length} already-existing: ${res.skipped.join(', ')}.`;
            }
            alert(message);
            setDiscoveredDevices([]);
            setRawSample(null);
            setDiscoverEndpoint('');
            setDiscoverHeaders('');
            fetchDevices();
        } catch (error) {
            console.error('Failed to import devices', error);
            alert('Failed to import devices.');
        } finally {
            setImporting(false);
        }
    };

    const handleEditClick = (device: Device) => {
        setEditingDevice(device);
        setEditDeviceName(device.name);
        setEditDeviceType(device.type);
        setEditCapabilities([...(device.capabilities || [])]);
    };

    const handleUpdateDevice = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!editingDevice) return;
        
        // Parse any stringified schemas back into JSON objects before sending to API
        const parsedCapabilities = editCapabilities.map(cap => {
            let schema = cap.input_schema;
            if (typeof schema === 'string') {
                try {
                    schema = JSON.parse(schema);
                } catch (err) {
                    console.warn(`Could not parse JSON schema for capability ${cap.name}:`, err);
                }
            }
            return { ...cap, input_schema: schema };
        });

        try {
            await api.put(`/devices/${editingDevice.id}`, {
                name: editDeviceName,
                type: editDeviceType,
                capabilities: parsedCapabilities
            });
            setEditingDevice(null);
            fetchDevices();
        } catch (error) {
            console.error("Failed to update device", error);
            alert("Failed to update device.");
        }
    };

    const addEditCapability = () => {
        try {
            const schema = JSON.parse(editNewCapSchema);
            setEditCapabilities([...editCapabilities, {
                name: editNewCapName,
                url: editNewCapUrl,
                method: editNewCapMethod,
                input_schema: schema
            }]);
            setEditNewCapName('');
            setEditNewCapUrl('');
            setEditNewCapSchema('{}');
        } catch {
            alert("Invalid JSON schema");
        }
    };

    const removeEditCapability = (index: number) => {
        const newCaps = [...editCapabilities];
        newCaps.splice(index, 1);
        setEditCapabilities(newCaps);
    };

    const handleEditCapabilityChange = (index: number, field: keyof Capability, value: string) => {
        const newCaps = [...editCapabilities];
        if (field === 'input_schema') {
            try {
                // If it's valid JSON, update it. If not, we still update the string for typing, 
                // but we need to represent the schema as string in state if we want to allow 
                // temporary invalid typing. Given the API expects an object, we will parse it.
                // For a robust implementation, we should probably keep raw strings in state
                // and parse on save, but for simplicity here we try to parse it.
                const schema = JSON.parse(value);
                newCaps[index] = { ...newCaps[index], [field]: schema };
            } catch {
                // To allow user to type and have intermediate invalid JSON, we really should 
                // not throw an alert on every keystroke. 
                // Best to ignore and only validate on Add/Save, but to keep capability.input_schema
                // generic, we simply won't update state if it's invalid during edit.
                // Alternative: just store it as string and we parse it during PUT. 
                // But the backend expects 'any' object.
                console.warn("Invalid JSON during edit");
                // For seamless editing, we need a separate state, but we will assume user
                // will paste correct JSON.
            }
        } else {
            newCaps[index] = { ...newCaps[index], [field]: value };
        }
        setEditCapabilities(newCaps);
    };

    return (
        <div className="space-y-6">
            <div className="md:flex md:items-center md:justify-between">
                <div className="flex-1 min-w-0">
                    <h2 className="text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
                        Device Management
                    </h2>
                </div>
            </div>

            <div className="bg-white shadow sm:rounded-lg p-6">
                <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">Register New Device</h3>

                {/* Mode selector: register by hand, or auto-discover from an endpoint */}
                <div className="flex gap-2 mb-6 border-b border-gray-200">
                    <button
                        type="button"
                        onClick={() => setMode('manual')}
                        className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${mode === 'manual'
                            ? 'border-indigo-600 text-indigo-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                    >
                        <Pencil className="w-4 h-4" /> Manual
                    </button>
                    <button
                        type="button"
                        onClick={() => setMode('discover')}
                        className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-px ${mode === 'discover'
                            ? 'border-indigo-600 text-indigo-600'
                            : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                    >
                        <Radar className="w-4 h-4" /> Auto-Discover from Endpoint
                    </button>
                </div>

                {mode === 'manual' && (
                <form onSubmit={handleAddDevice} className="space-y-4">
                    <div className="flex gap-4">
                        <div className="flex-1">
                            <label htmlFor="name" className="block text-sm font-medium text-gray-700">Device Name</label>
                            <input
                                type="text"
                                id="name"
                                required
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                                value={newDeviceName}
                                onChange={(e) => setNewDeviceName(e.target.value)}
                                placeholder="e.g. Living Room Camera"
                            />
                        </div>
                        <div className="w-48">
                            <label htmlFor="type" className="block text-sm font-medium text-gray-700">Type</label>
                            <input
                                list="device-types"
                                id="type"
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                                value={newDeviceType}
                                onChange={(e) => setNewDeviceType(e.target.value)}
                                placeholder="Select or type..."
                            />
                            <datalist id="device-types">
                                <option value="Camera" />
                                <option value="Alarm" />
                                <option value="Lock" />
                                <option value="Light" />
                                <option value="Sensor" />
                                <option value="Thermostat" />
                                <option value="Speaker" />
                                <option value="Appliance" />
                            </datalist>
                        </div>
                    </div>

                    {/* Capabilities Section */}
                    <div className="border-t pt-4">
                        <h4 className="text-md font-medium text-gray-900 mb-2">Capabilities</h4>
                        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end bg-gray-50 p-4 rounded-md">
                            <div className="md:col-span-1">
                                <label className="block text-xs font-medium text-gray-500">Name</label>
                                <input
                                    type="text"
                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                    value={newCapName}
                                    onChange={(e) => setNewCapName(e.target.value)}
                                    placeholder="Rotate"
                                />
                            </div>
                            <div className="md:col-span-1">
                                <label className="block text-xs font-medium text-gray-500">URL</label>
                                <input
                                    type="text"
                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                    value={newCapUrl}
                                    onChange={(e) => setNewCapUrl(e.target.value)}
                                    placeholder="http://..."
                                />
                            </div>
                            <div className="md:col-span-1">
                                <label className="block text-xs font-medium text-gray-500">Method</label>
                                <select
                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                    value={newCapMethod}
                                    onChange={(e) => setNewCapMethod(e.target.value)}
                                >
                                    <option>GET</option>
                                    <option>POST</option>
                                    <option>PUT</option>
                                    <option>SSE</option>
                                    <option>VLM</option>
                                </select>
                            </div>
                            <div className="md:col-span-1">
                                <label className="block text-xs font-medium text-gray-500">Input Schema (JSON)</label>
                                <input
                                    type="text"
                                    className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                    value={newCapSchema}
                                    onChange={(e) => setNewCapSchema(e.target.value)}
                                    placeholder="{}"
                                />
                            </div>
                            <div className="md:col-span-1">
                                <button
                                    type="button"
                                    onClick={addCapability}
                                    className="w-full inline-flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-indigo-700 bg-indigo-100 hover:bg-indigo-200"
                                >
                                    Add Cap
                                </button>
                            </div>
                        </div>

                        {/* List of added capabilities */}
                        <div className="mt-2 space-y-2">
                            {capabilities.map((cap, idx) => (
                                <div key={idx} className="flex items-center justify-between bg-gray-100 p-2 rounded text-sm">
                                    <span className="font-medium text-gray-700">{cap.name}</span>
                                    <span className="text-gray-500 truncate max-w-xs">{cap.url}</span>
                                    <span className="text-gray-500">{cap.method}</span>
                                    <button type="button" onClick={() => removeCapability(idx)} className="text-red-500 hover:text-red-700">
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="pt-4">
                        <button
                            type="submit"
                            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                        >
                            <Plus className="w-4 h-4 mr-2" />
                            Create Device
                        </button>
                    </div>
                </form>
                )}

                {mode === 'discover' && (
                <div className="space-y-4">
                    <p className="text-sm text-gray-500">
                        Provide an endpoint that returns your device catalog. We&apos;ll send a GET request,
                        let the LLM analyze whatever structure comes back, and map it into this system&apos;s
                        format. You can review everything before it&apos;s saved.
                    </p>
                    <form onSubmit={handleDiscover} className="space-y-4">
                        <div>
                            <label htmlFor="endpoint" className="block text-sm font-medium text-gray-700">Catalog Endpoint URL</label>
                            <input
                                type="url"
                                id="endpoint"
                                required
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                                value={discoverEndpoint}
                                onChange={(e) => setDiscoverEndpoint(e.target.value)}
                                placeholder="https://my-gateway.local/api/devices"
                            />
                        </div>
                        <div>
                            <label htmlFor="headers" className="block text-sm font-medium text-gray-700">
                                Headers (optional, JSON)
                            </label>
                            <input
                                type="text"
                                id="headers"
                                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black font-mono"
                                value={discoverHeaders}
                                onChange={(e) => setDiscoverHeaders(e.target.value)}
                                placeholder='{"Authorization": "Bearer ..."}'
                            />
                        </div>
                        <button
                            type="submit"
                            disabled={discovering}
                            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-60"
                        >
                            {discovering
                                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Fetching & Analyzing…</>
                                : <><Radar className="w-4 h-4 mr-2" /> Fetch &amp; Analyze</>}
                        </button>
                    </form>

                    {discoverError && (
                        <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                            {discoverError}
                        </div>
                    )}
                    {discoverWarning && (
                        <div className="rounded-md bg-yellow-50 border border-yellow-200 p-3 text-sm text-yellow-800">
                            {discoverWarning}
                        </div>
                    )}

                    {discoveredDevices.length > 0 && (
                        <div className="border-t pt-4 space-y-3">
                            <div className="flex items-center justify-between">
                                <h4 className="text-md font-medium text-gray-900">
                                    Preview — {discoveredDevices.length} device(s) detected
                                </h4>
                                <button
                                    type="button"
                                    onClick={handleImportDiscovered}
                                    disabled={importing}
                                    className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-60"
                                >
                                    {importing
                                        ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Importing…</>
                                        : <><Plus className="w-4 h-4 mr-2" /> Import {discoveredDevices.length} Device(s)</>}
                                </button>
                            </div>
                            <div className="space-y-2">
                                {discoveredDevices.map((d, idx) => (
                                    <div key={idx} className="bg-gray-50 border border-gray-200 rounded-md p-3">
                                        <div className="flex items-start justify-between">
                                            <div>
                                                <p className="font-medium text-gray-900">{d.name}</p>
                                                <p className="text-xs text-gray-500">{d.type}</p>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => removeDiscoveredDevice(idx)}
                                                className="text-red-500 hover:text-red-700"
                                                title="Exclude from import"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                        <ul className="mt-2 space-y-1">
                                            {d.capabilities.map((c, ci) => (
                                                <li key={ci} className="text-xs text-gray-600 flex items-center gap-2 flex-wrap">
                                                    <span className="font-medium text-gray-700">{c.name}</span>
                                                    <span className="px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700">{c.method}</span>
                                                    <span className="text-gray-400 truncate">{c.url}</span>
                                                </li>
                                            ))}
                                            {d.capabilities.length === 0 && (
                                                <li className="text-xs text-gray-400">No capabilities detected.</li>
                                            )}
                                        </ul>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {rawSample && (
                        <details className="text-xs text-gray-500">
                            <summary className="cursor-pointer select-none">View raw endpoint response</summary>
                            <pre className="mt-2 bg-gray-900 text-gray-100 p-3 rounded-md overflow-x-auto max-h-60">{rawSample}</pre>
                        </details>
                    )}
                </div>
                )}
            </div>

            <div className="bg-white shadow overflow-hidden sm:rounded-md">
                <ul className="divide-y divide-gray-200">
                    {devices.map((device) => (
                        <li key={device.id}>
                            <div className="px-4 py-4 flex items-center sm:px-6">
                                <div className="min-w-0 flex-1 sm:flex sm:items-center sm:justify-between">
                                    <div className="flex items-center">
                                        <div className="flex-shrink-0">
                                            <Server className="h-6 w-6 text-gray-400" />
                                        </div>
                                        <div className="ml-4 truncate">
                                            <div className="flex text-sm">
                                                <p className="font-medium text-indigo-600 truncate">{device.name}</p>
                                                <p className="ml-1 flex-shrink-0 font-normal text-gray-500">
                                                    in {device.type}
                                                </p>
                                            </div>
                                            <div className="text-xs text-gray-400 mt-1">
                                                Capabilities: {device.capabilities?.map(c => c.name).join(', ') || 'None'}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div className="ml-5 flex-shrink-0 flex items-center gap-4">
                                    <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
                                        Active
                                    </span>
                                    <button
                                        onClick={() => handleEditClick(device)}
                                        className="text-indigo-600 hover:text-indigo-900 text-sm font-medium cursor-pointer"
                                    >
                                        Edit
                                    </button>
                                    <button
                                        onClick={async () => {
                                            if (confirm('Are you sure you want to delete this device?')) {
                                                try {
                                                    await api.delete(`/devices/${device.id}`);
                                                    fetchDevices();
                                                } catch (error) {
                                                    console.error("Failed to delete device", error);
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
                    {devices.length === 0 && !loading && (
                        <li className="px-4 py-8 text-center text-gray-500">No devices registered yet.</li>
                    )}
                </ul>
            </div>

            {/* Edit Device Modal */}
            {editingDevice && (
                <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full flex items-center justify-center z-50">
                    <div className="relative bg-white p-6 rounded-md shadow-xl max-w-3xl w-full mx-4 max-h-[90vh] overflow-y-auto">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-medium text-gray-900">Edit Device: {editingDevice.name}</h3>
                            <button onClick={() => setEditingDevice(null)} className="text-gray-400 hover:text-gray-500">
                                <span className="sr-only">Close</span>
                                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>
                        <form onSubmit={handleUpdateDevice} className="space-y-4">
                            <div className="flex gap-4">
                                <div className="flex-1">
                                    <label htmlFor="edit-name" className="block text-sm font-medium text-gray-700">Device Name</label>
                                    <input
                                        type="text"
                                        id="edit-name"
                                        required
                                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                                        value={editDeviceName}
                                        onChange={(e) => setEditDeviceName(e.target.value)}
                                    />
                                </div>
                                <div className="w-48">
                                    <label htmlFor="edit-type" className="block text-sm font-medium text-gray-700">Type</label>
                                    <input
                                        list="edit-device-types"
                                        id="edit-type"
                                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm text-black"
                                        value={editDeviceType}
                                        onChange={(e) => setEditDeviceType(e.target.value)}
                                    />
                                    <datalist id="edit-device-types">
                                        <option value="Camera" />
                                        <option value="Alarm" />
                                        <option value="Lock" />
                                        <option value="Light" />
                                        <option value="Sensor" />
                                        <option value="Thermostat" />
                                        <option value="Speaker" />
                                        <option value="Appliance" />
                                    </datalist>
                                </div>
                            </div>

                            <div className="border-t pt-4">
                                <h4 className="text-md font-medium text-gray-900 mb-2">Capabilities</h4>
                                <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end bg-gray-50 p-4 rounded-md">
                                    <div className="md:col-span-1">
                                        <label className="block text-xs font-medium text-gray-500">Name</label>
                                        <input
                                            type="text"
                                            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                            value={editNewCapName}
                                            onChange={(e) => setEditNewCapName(e.target.value)}
                                            placeholder="Rotate"
                                        />
                                    </div>
                                    <div className="md:col-span-1">
                                        <label className="block text-xs font-medium text-gray-500">URL</label>
                                        <input
                                            type="text"
                                            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                            value={editNewCapUrl}
                                            onChange={(e) => setEditNewCapUrl(e.target.value)}
                                            placeholder="http://..."
                                        />
                                    </div>
                                    <div className="md:col-span-1">
                                        <label className="block text-xs font-medium text-gray-500">Method</label>
                                        <select
                                            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                            value={editNewCapMethod}
                                            onChange={(e) => setEditNewCapMethod(e.target.value)}
                                        >
                                            <option>GET</option>
                                            <option>POST</option>
                                            <option>PUT</option>
                                            <option>SSE</option>
                                            <option>VLM</option>
                                        </select>
                                    </div>
                                    <div className="md:col-span-1">
                                        <label className="block text-xs font-medium text-gray-500">Input Schema (JSON)</label>
                                        <input
                                            type="text"
                                            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                            value={editNewCapSchema}
                                            onChange={(e) => setEditNewCapSchema(e.target.value)}
                                            placeholder="{}"
                                        />
                                    </div>
                                    <div className="md:col-span-1">
                                        <button
                                            type="button"
                                            onClick={addEditCapability}
                                            className="w-full inline-flex items-center justify-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-indigo-700 bg-indigo-100 hover:bg-indigo-200"
                                        >
                                            Add Cap
                                        </button>
                                    </div>
                                </div>

                                <div className="mt-4 space-y-2 max-h-60 overflow-y-auto">
                                    <h4 className="text-sm font-medium text-gray-700">Existing Capabilities</h4>
                                    {editCapabilities.map((cap, idx) => (
                                        <div key={idx} className="grid grid-cols-1 md:grid-cols-5 gap-4 items-center bg-white border border-gray-200 p-2 rounded-md shadow-sm">
                                            <div className="md:col-span-1">
                                                <input
                                                    type="text"
                                                    className="block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                                    value={cap.name}
                                                    onChange={(e) => handleEditCapabilityChange(idx, 'name', e.target.value)}
                                                    placeholder="Name"
                                                />
                                            </div>
                                            <div className="md:col-span-1">
                                                <input
                                                    type="text"
                                                    className="block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                                    value={cap.url}
                                                    onChange={(e) => handleEditCapabilityChange(idx, 'url', e.target.value)}
                                                    placeholder="URL"
                                                />
                                            </div>
                                            <div className="md:col-span-1">
                                                <select
                                                    className="block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                                    value={cap.method}
                                                    onChange={(e) => handleEditCapabilityChange(idx, 'method', e.target.value)}
                                                >
                                                    <option>GET</option>
                                                    <option>POST</option>
                                                    <option>PUT</option>
                                                    <option>SSE</option>
                                                    <option>VLM</option>
                                                </select>
                                            </div>
                                            <div className="md:col-span-1">
                                                <input
                                                    type="text"
                                                    className="block w-full border border-gray-300 rounded-md shadow-sm py-1 px-2 text-sm text-black"
                                                    value={typeof cap.input_schema === 'string' ? cap.input_schema : JSON.stringify(cap.input_schema)}
                                                    onChange={(e) => {
                                                        const newCaps = [...editCapabilities];
                                                        // We temporarily store the string to allow smooth typing.
                                                        // The backend might complain if we send a string when it expects an object,
                                                        // but since input_schema is defined as `any`, string is technically valid.
                                                        // We will attempt to parse it before submitting in handleUpdateDevice.
                                                        newCaps[idx] = { ...newCaps[idx], input_schema: e.target.value };
                                                        setEditCapabilities(newCaps);
                                                    }}
                                                    placeholder="Schema {}"
                                                />
                                            </div>
                                            <div className="md:col-span-1 flex justify-end">
                                                <button type="button" onClick={() => removeEditCapability(idx)} className="text-red-500 hover:text-red-700 p-1 flex items-center justify-center bg-red-50 rounded-md w-full h-full py-1">
                                                    <Trash2 className="w-4 h-4 mr-1" /> Remove
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                    {editCapabilities.length === 0 && (
                                        <div className="text-sm text-gray-500 text-center py-2">No capabilities added.</div>
                                    )}
                                </div>
                            </div>

                            <div className="pt-4 flex justify-end gap-3">
                                <button
                                    type="button"
                                    onClick={() => setEditingDevice(null)}
                                    className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                                >
                                    Save Changes
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
