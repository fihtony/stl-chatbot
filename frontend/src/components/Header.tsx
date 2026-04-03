"use client";

import Link from "next/link";
import LanguageSwitcher from "./LanguageSwitcher";
import AdminLoginDialog from "./AdminLoginDialog";
import { useLanguage } from "./LanguageContext";
import { useAdmin } from "./AdminContext";

export default function Header() {
  const { t } = useLanguage();
  const { isAdmin, adminEmail, openLoginDialog, logout } = useAdmin();

  return (
    <>
      <header className="bg-gradient-to-r from-blue-800 to-blue-900 text-white shadow-lg">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              {/* School Logo */}
              <div className="flex items-center justify-center w-12 h-12 bg-white rounded-full shadow-md">
                <span className="text-3xl font-bold text-blue-900">S</span>
              </div>

              <div>
                <h1 className="text-2xl font-bold">{t.headerTitle}</h1>
                <p className="text-blue-200 text-sm mt-0.5">{t.headerSubtitle}</p>
              </div>
            </div>

            {/* Right controls */}
            <div className="flex items-center gap-2">
              <LanguageSwitcher />

              {/* Admin button */}
              {isAdmin ? (
                <div className="flex items-center gap-1">
                  <Link
                    href="/admin"
                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-green-400/50 bg-green-500/20 text-white text-sm font-medium hover:bg-green-500/30 transition-all shadow-sm"
                    title={adminEmail ?? "Admin panel"}
                  >
                    <span aria-hidden="true">🛡</span>
                    <span>Admin</span>
                    <span className="text-green-300 text-xs" aria-hidden="true">✓</span>
                  </Link>
                  <button
                    onClick={logout}
                    className="px-2 py-2 rounded-lg border border-white/20 bg-white/10 text-white text-xs hover:bg-white/20 transition-all"
                    title="Logout"
                    aria-label="Logout from admin"
                  >
                    ↩
                  </button>
                </div>
              ) : (
                <button
                  onClick={openLoginDialog}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-white/30 bg-white/10 text-white text-sm font-medium hover:bg-white/20 transition-all shadow-sm"
                  aria-label="Administrator login"
                >
                  <span aria-hidden="true">🛡</span>
                  <span>Admin</span>
                </button>
              )}
            </div>
          </div>
        </div>
      </header>
      <AdminLoginDialog />
    </>
  );
}
