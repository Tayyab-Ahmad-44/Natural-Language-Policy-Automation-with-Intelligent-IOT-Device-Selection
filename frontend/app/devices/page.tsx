"use client";
import { useState, useEffect } from 'react';
import api, { Device, Capability } from '@/lib/api';
import { Plus, Server, Trash2 } from 'lucide-react';

export default function DevicesPage() {
    const [devices, setDevices] = useState<Device[]>([]);
    const [newDeviceName, setNewDeviceName] = useState('');
    const [newDeviceType, setNewDeviceType] = useState('camera');
    const [loading, setLoading] = useState(true);

    // Capabilities state
    const [capabilities, setCapabilities] = useState<Capability[]>([]);
    const [newCapName, setNewCapName] = useState('');
    const [newCapUrl, setNewCapUrl] = useState('');
    const [newCapMethod, setNewCapMethod] = useState('GET');
    const [newCapSchema, setNewCapSchema] = useState('{}');

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
        } catch (e) {
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
        </div>
    );
}
