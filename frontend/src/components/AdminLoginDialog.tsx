"use client";

import { useAdmin } from "./AdminContext";

export default function AdminLoginDialog() {
  const { showLoginDialog, closeLoginDialog } = useAdmin();

  if (!showLoginDialog) return null;

  const handleLogin = () => {
    // Route through the Next.js proxy so the OAuth callback cookie is set
    // for the frontend origin (localhost:3086) rather than the backend origin
    // (127.0.0.1:8086).  This ensures the admin_token cookie is usable for
    // all subsequent proxy-based admin API calls.
    window.location.href = "/api/admin/login/initiate";
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="admin-dialog-title"
    >
      <div className="bg-white rounded-xl shadow-2xl p-6 w-full max-w-sm mx-4">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-3xl" aria-hidden="true">🔐</span>
          <h2 id="admin-dialog-title" className="text-lg font-bold text-gray-800">
            Admin Login
          </h2>
        </div>
        <p className="text-sm text-gray-600 mb-6">
          This area is restricted to system administrators only.<br />
          <span className="font-medium">Are you an administrator?</span>
        </p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={closeLoginDialog}
            className="px-4 py-2 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
          >
            No, cancel
          </button>
          <button
            onClick={handleLogin}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            I am an administrator
          </button>
        </div>
      </div>
    </div>
  );
}
