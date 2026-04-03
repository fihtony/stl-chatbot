"use client";

interface Props {
  show: boolean;
  onSnooze: () => void;
  onRefresh: () => void;
}

export default function ConfigChangePrompt({ show, onSnooze, onRefresh }: Props) {
  if (!show) return null;
  return (
    <div
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-white rounded-xl shadow-xl border border-blue-200 px-5 py-4 w-full max-w-md"
      role="alert"
      aria-live="assertive"
    >
      <p className="text-sm font-semibold text-gray-800 mb-1">🔄 System configuration updated</p>
      <p className="text-xs text-gray-600 mb-3">
        The system configuration has been updated. Please refresh to continue.
      </p>
      <div className="flex gap-2 justify-end">
        <button
          onClick={onSnooze}
          className="px-3 py-1.5 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
        >
          Remind me later
        </button>
        <button
          onClick={onRefresh}
          className="px-3 py-1.5 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          Refresh now
        </button>
      </div>
    </div>
  );
}
