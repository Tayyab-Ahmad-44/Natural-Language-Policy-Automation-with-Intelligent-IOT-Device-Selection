"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Shield, Settings, Calendar } from "lucide-react";

export default function Navbar() {
    const pathname = usePathname();

    const isActive = (path: string) => {
        return pathname === path ? "border-indigo-500 text-gray-900" : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700";
    };

    return (
        <nav className="bg-white border-b border-gray-200">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="flex justify-between h-16">
                    <div className="flex">
                        <div className="flex-shrink-0 flex items-center">
                            <Shield className="h-8 w-8 text-indigo-600" />
                            <span className="ml-2 text-xl font-bold text-gray-900">IoT Manager</span>
                        </div>
                        <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
                            <Link href="/" className={`${isActive("/")} inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium`}>
                                Home
                            </Link>
                            <Link href="/devices" className={`${isActive("/devices")} inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium`}>
                                <Settings className="w-4 h-4 mr-2" />
                                Devices
                            </Link>
                            <Link href="/policies" className={`${isActive("/policies")} inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium`}>
                                <Shield className="w-4 h-4 mr-2" />
                                Policies
                            </Link>
                            <Link href="/schedule" className={`${isActive("/schedule")} inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium`}>
                                <Calendar className="w-4 h-4 mr-2" />
                                Schedule
                            </Link>
                            <Link href="/tasks" className={`${isActive("/tasks")} inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium`}>
                                <Shield className="w-4 h-4 mr-2" />
                                Tasks
                            </Link>
                        </div>
                    </div>
                </div>
            </div>
        </nav>
    );
}
