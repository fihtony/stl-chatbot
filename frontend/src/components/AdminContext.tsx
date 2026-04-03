"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  ReactNode,
} from "react";

const LOGIN_DIALOG_KEY = "stl_admin_login_prompt";

interface AdminContextType {
  isAdmin: boolean;
  adminEmail: string | null;
  showLoginDialog: boolean;
  openLoginDialog: () => void;
  closeLoginDialog: () => void;
  logout: () => Promise<void>;
  checkSession: () => Promise<void>;
}

const AdminContext = createContext<AdminContextType>({
  isAdmin: false,
  adminEmail: null,
  showLoginDialog: false,
  openLoginDialog: () => {},
  closeLoginDialog: () => {},
  logout: async () => {},
  checkSession: async () => {},
});

export function AdminProvider({ children }: { children: ReactNode }) {
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminEmail, setAdminEmail] = useState<string | null>(null);
  const [showLoginDialog, setShowLoginDialog] = useState(false);

  const checkSession = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/me", { cache: "no-store", credentials: "include" });
      if (res.ok) {
        const data = await res.json();
        setIsAdmin(data.logged_in === true);
        setAdminEmail(data.email ?? null);
      } else {
        setIsAdmin(false);
        setAdminEmail(null);
      }
    } catch {
      setIsAdmin(false);
      setAdminEmail(null);
    }
  }, []);

  // Check on mount (e.g., after OAuth redirect back to /admin)
  useEffect(() => {
    try {
      if (sessionStorage.getItem(LOGIN_DIALOG_KEY) === "1") {
        sessionStorage.removeItem(LOGIN_DIALOG_KEY);
        setShowLoginDialog(true);
      }
    } catch {
      // Ignore session storage errors.
    }

    checkSession();
  }, [checkSession]);

  const openLoginDialog = useCallback(() => setShowLoginDialog(true), []);
  const closeLoginDialog = useCallback(() => setShowLoginDialog(false), []);

  const logout = useCallback(async () => {
    try {
      await fetch("/api/admin/logout", { method: "DELETE", credentials: "include" });
    } finally {
      setIsAdmin(false);
      setAdminEmail(null);
    }
  }, []);

  return (
    <AdminContext.Provider
      value={{ isAdmin, adminEmail, showLoginDialog, openLoginDialog, closeLoginDialog, logout, checkSession }}
    >
      {children}
    </AdminContext.Provider>
  );
}

export function useAdmin() {
  return useContext(AdminContext);
}
