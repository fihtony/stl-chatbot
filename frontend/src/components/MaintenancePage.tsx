"use client";

import { useAdmin } from "./AdminContext";

interface Props {
  title: string;
  message: string;
  startTime?: string | null;
  endTime?: string | null;
}

export default function MaintenancePage({ title, message, startTime, endTime }: Props) {
  const { isAdmin } = useAdmin();

  const formatTime = (value: string | null | undefined) => {
    if (!value) return "";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return parsed.toLocaleString();
  };

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4 py-16">
      <div className="text-6xl mb-6" aria-hidden="true">🔧</div>
      <h2 className="text-2xl font-bold text-gray-800 mb-3">
        {title || "System Maintenance"}
      </h2>
      <p className="text-gray-600 max-w-sm mb-8">
        {message || "The system is currently under maintenance. Please check back later."}
      </p>
      {(startTime || endTime) && (
        <p className="text-sm text-gray-500 mb-8">
          {startTime && formatTime(startTime)}
          {startTime && endTime ? " – " : ""}
          {endTime && formatTime(endTime)}
        </p>
      )}
      {isAdmin && (
        <div className="bg-yellow-50 border border-yellow-300 rounded-lg px-4 py-3 text-sm text-yellow-800 max-w-sm">
          <strong>Admin:</strong> Maintenance mode is active. You have bypass access.
        </div>
      )}
    </div>
  );
}
