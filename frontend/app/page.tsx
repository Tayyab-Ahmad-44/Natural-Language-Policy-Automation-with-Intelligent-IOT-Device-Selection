import Link from "next/link";
import { Settings, Shield, Calendar } from "lucide-react";

export default function Home() {
  return (
    <div className="space-y-10">
      <div className="text-center">
        <h1 className="text-4xl tracking-tight font-extrabold text-gray-900 sm:text-5xl md:text-6xl">
          <span className="block xl:inline">Smart IoT</span>{' '}
          <span className="block text-indigo-600 xl:inline">Policy Manager</span>
        </h1>
        <p className="mt-3 max-w-md mx-auto text-base text-gray-500 sm:text-lg md:mt-5 md:text-xl md:max-w-3xl">
          Register devices, define natural language policies, and automate your environment with AI-powered scheduling.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
        <Link href="/devices" className="relative rounded-lg border border-gray-300 bg-white px-6 py-5 shadow-sm flex items-center space-x-3 hover:border-indigo-400 focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-indigo-500">
          <div className="flex-shrink-0">
            <Settings className="h-10 w-10 text-indigo-600" />
          </div>
          <div className="flex-1 min-w-0">
            <span className="absolute inset-0" aria-hidden="true" />
            <p className="text-sm font-medium text-gray-900">Register Devices</p>
            <p className="text-sm text-gray-500 truncate">Add cameras, alarms, and locks</p>
          </div>
        </Link>

        <Link href="/policies" className="relative rounded-lg border border-gray-300 bg-white px-6 py-5 shadow-sm flex items-center space-x-3 hover:border-indigo-400 focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-indigo-500">
          <div className="flex-shrink-0">
            <Shield className="h-10 w-10 text-indigo-600" />
          </div>
          <div className="flex-1 min-w-0">
            <span className="absolute inset-0" aria-hidden="true" />
            <p className="text-sm font-medium text-gray-900">Define Policies</p>
            <p className="text-sm text-gray-500 truncate">Create AI-powered rules</p>
          </div>
        </Link>

        <Link href="/schedule" className="relative rounded-lg border border-gray-300 bg-white px-6 py-5 shadow-sm flex items-center space-x-3 hover:border-indigo-400 focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-indigo-500">
          <div className="flex-shrink-0">
            <Calendar className="h-10 w-10 text-indigo-600" />
          </div>
          <div className="flex-1 min-w-0">
            <span className="absolute inset-0" aria-hidden="true" />
            <p className="text-sm font-medium text-gray-900">View Schedule</p>
            <p className="text-sm text-gray-500 truncate">See active automations</p>
          </div>
        </Link>
      </div>
    </div>
  );
}
