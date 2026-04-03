"use client";

import { useEffect, useState, useCallback } from "react";
import { useAdmin } from "@/components/AdminContext";
import Link from "next/link";
import { useRouter } from "next/navigation";

const LOGIN_DIALOG_KEY = "stl_admin_login_prompt";

// ──────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────
interface Config {
  default_language: string;
  active_theme_id: string;
  config_version: number;
  maintenance_mode: boolean;
  maintenance_title: string;
  maintenance_message: string;
}

interface Theme {
  id: string;
  name: string;
  is_preset: boolean;
}

interface Banner {
  title: string;
  content: string;
  start_time: string;
  end_time: string;
  timezone: string;
  severity: string;
  enabled: boolean;
}

interface LogItem {
  id: number;
  session_id: string;
  requested_at: string;
  question_summary: string;
  browser_name: string;
  city: string;
  is_error: boolean;
  response_ms: number;
}

interface Dashboard {
  active_sessions: number;
  notebooklm_status: string;
  today_questions: number;
  maintenance_status: string;
  total_sessions: number;
  total_questions: number;
  avg_questions_per_session: number;
  avg_response_ms: number;
  error_rate: number;
  config_version: number;
}

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────
async function api(path: string, method = "GET", body?: object) {
  const res = await fetch(`/api/admin${path}`, {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined") {
      try {
        sessionStorage.setItem(LOGIN_DIALOG_KEY, "1");
      } catch {
        // Ignore session storage errors.
      }
      window.location.assign("/");
      throw new Error("Admin session expired");
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "API error");
  }
  return res.json();
}

// ──────────────────────────────────────────────
// Section components
// ──────────────────────────────────────────────

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
      <h2 className="text-lg font-bold text-gray-800 border-b pb-2">{title}</h2>
      {children}
    </section>
  );
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
      ok ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
    }`}>
      {ok ? "✓" : "✗"} {label}
    </span>
  );
}

// ──────────────────────────────────────────────
// Dashboard section
// ──────────────────────────────────────────────
function DashboardSection() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api("/dashboard").then(setData).catch(console.error).finally(() => setLoading(false));
  }, []);
  if (loading) return <p className="text-sm text-gray-500">Loading…</p>;
  if (!data) return <p className="text-sm text-red-500">Failed to load dashboard</p>;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {[
        { label: "Active Sessions", value: data.active_sessions },
        { label: "Today Questions", value: data.today_questions },
        { label: "Config Version", value: data.config_version },
        { label: "Error Rate", value: `${(data.error_rate * 100).toFixed(1)}%` },
        { label: "Total Sessions", value: data.total_sessions },
        { label: "Total Questions", value: data.total_questions },
        { label: "Avg Q/Session", value: data.avg_questions_per_session.toFixed(1) },
        { label: "Avg Response", value: `${data.avg_response_ms.toFixed(0)}ms` },
      ].map(({ label, value }) => (
        <div key={label} className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-blue-700">{value}</p>
          <p className="text-xs text-gray-500 mt-1">{label}</p>
        </div>
      ))}
      <div className="col-span-2 md:col-span-4 flex gap-3 flex-wrap">
        <StatusBadge ok={data.notebooklm_status === "connected"} label={`NotebookLM: ${data.notebooklm_status}`} />
        <StatusBadge ok={data.maintenance_status === "normal"} label={`Maintenance: ${data.maintenance_status}`} />
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────
// NotebookLM URL section
// ──────────────────────────────────────────────
function NotebookLMSection() {
  const [masked, setMasked] = useState("");
  const [version, setVersion] = useState(0);
  const [editing, setEditing] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [msg, setMsg] = useState("");
  const [reauthJobId, setReauthJobId] = useState<string | null>(null);
  const [reauthStatus, setReauthStatus] = useState<string>("");
  const [reauthUrl, setReauthUrl] = useState<string>("");
  const [reauthModal, setReauthModal] = useState(false);

  const loadUrl = useCallback(() => {
    api("/config/notebooklm").then((d) => { setMasked(d.url_masked); setVersion(d.config_version); });
  }, []);

  useEffect(() => { loadUrl(); }, [loadUrl]);

  const save = async () => {
    try {
      const r = await api("/config/notebooklm", "PUT", { url: newUrl });
      setMsg(`Saved. Config version: ${r.config_version}`);
      setEditing(false);
      loadUrl();
    } catch (e: unknown) {
      setMsg(String(e));
    }
  };

  const startReauth = async (method: string) => {
    try {
      const r = await api("/notebooklm/reauth/start", "POST", { method });
      setReauthJobId(r.job_id);
      setReauthStatus(r.status);
      setReauthUrl(r.auth_url || "");
      // Poll status
      const pollId = setInterval(async () => {
        const s = await api(`/notebooklm/reauth/status/${r.job_id}`);
        setReauthStatus(s.status);
        if (["authenticated", "failed", "timeout", "cancelled"].includes(s.status)) {
          clearInterval(pollId);
        }
      }, 3000);
    } catch (e: unknown) { setMsg(String(e)); }
  };

  const cancelReauth = async () => {
    if (!reauthJobId) return;
    await api(`/notebooklm/reauth/cancel/${reauthJobId}`, "POST");
    setReauthStatus("cancelled");
    setReauthUrl("");
    setReauthModal(false);
  };

  const copyReauthUrl = async () => {
    if (!reauthUrl) return;
    await navigator.clipboard.writeText(reauthUrl);
    setMsg("Re-authentication link copied.");
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-gray-500">Current URL:</span>
        <code className="bg-gray-100 px-2 py-0.5 rounded text-gray-700">{masked || "—"}</code>
        <span className="text-xs text-gray-400">v{version}</span>
      </div>
      {!editing ? (
        <button onClick={() => setEditing(true)} className="btn-secondary text-sm">Edit URL</button>
      ) : (
        <div className="flex gap-2 items-start">
          <input
            type="url"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            placeholder="https://notebooklm.google.com/..."
            className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button onClick={save} className="btn-primary text-sm px-3 py-2">Save</button>
          <button onClick={() => setEditing(false)} className="btn-secondary text-sm px-3 py-2">Cancel</button>
        </div>
      )}
      {msg && <p className="text-xs text-blue-600">{msg}</p>}
      <button onClick={() => setReauthModal(true)} className="btn-secondary text-sm">
        🔄 Re-authenticate NotebookLM
      </button>

      {reauthModal && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-3 text-sm">
          <p className="font-medium text-blue-800">
            Note: Your admin login and NotebookLM authentication are two independent states.
          </p>
          <p className="text-gray-600">Status: <strong>{reauthStatus || "idle"}</strong></p>
          <div className="flex gap-2 flex-wrap">
            <button onClick={() => startReauth("browser")} className="btn-primary text-sm">
              Method A: Start in this browser
            </button>
            <button onClick={() => startReauth("copy_url")} className="btn-secondary text-sm">
              Method B: Copy auth URL
            </button>
            {reauthJobId && (
              <button onClick={cancelReauth} className="text-red-600 underline text-sm">
                Cancel
              </button>
            )}
            <button onClick={() => setReauthModal(false)} className="text-gray-500 underline text-sm">
              Close
            </button>
          </div>
          {reauthStatus === "authenticated" && (
            <p className="text-green-700 font-medium">✅ Authentication successful!</p>
          )}
          {reauthUrl && (
            <div className="space-y-2 rounded-lg border border-blue-200 bg-white p-3">
              <p className="text-xs text-gray-600">
                Open this URL in a browser on the machine running the chatbot backend to launch the NotebookLM sign-in flow.
              </p>
              <div className="flex gap-2">
                <input readOnly value={reauthUrl} className="flex-1 rounded border border-gray-300 px-3 py-2 text-xs text-gray-700" />
                <button onClick={copyReauthUrl} className="btn-secondary text-sm">Copy</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────
// Theme section
// ──────────────────────────────────────────────
function ThemeSection() {
  const [themes, setThemes] = useState<Theme[]>([]);
  const [activeId, setActiveId] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api("/themes").then((t) => setThemes(t)).catch(console.error);
    api("/config/notebooklm").then(() => {/* just for side-effect */}).catch(() => {});
    // Get active theme from public state
    fetch("/api/public-state").then(r => r.json()).then((d) => setActiveId(d.active_theme_id));
  }, []);

  const apply = async (id: string) => {
    try {
      await api("/themes/active", "PUT", { theme_id: id });
      setActiveId(id);
      setMsg(`Theme "${id}" applied. Takes effect on next user page load.`);
    } catch (e: unknown) { setMsg(String(e)); }
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {themes.map((t) => (
          <div
            key={t.id}
            className={`border rounded-lg p-3 cursor-pointer transition-all ${
              t.id === activeId ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:border-blue-300"
            }`}
            onClick={() => apply(t.id)}
          >
            <p className="text-sm font-medium text-gray-800">{t.name}</p>
            <p className="text-xs text-gray-500">{t.is_preset ? "Preset" : "Custom"} • {t.id}</p>
            {t.id === activeId && <p className="text-xs text-blue-600 mt-1">✓ Active</p>}
          </div>
        ))}
      </div>
      {msg && <p className="text-xs text-blue-600">{msg}</p>}
    </div>
  );
}

// ──────────────────────────────────────────────
// Language section
// ──────────────────────────────────────────────
function LanguageSectionAdmin() {
  const [lang, setLang] = useState("en");
  const [msg, setMsg] = useState("");
  useEffect(() => {
    fetch("/api/public-state").then(r => r.json()).then((d) => setLang(d.default_language || "en"));
  }, []);
  const save = async () => {
    try {
      await api("/default-language", "PUT", { language: lang });
      setMsg("Default language updated.");
    } catch (e: unknown) { setMsg(String(e)); }
  };
  return (
    <div className="flex items-center gap-3">
      <select
        value={lang}
        onChange={(e) => setLang(e.target.value)}
        className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        <option value="en">🇬🇧 English</option>
        <option value="fr">🇫🇷 Français</option>
        <option value="zh">🇨🇳 中文</option>
      </select>
      <button onClick={save} className="btn-primary text-sm px-3 py-2">Save</button>
      {msg && <span className="text-xs text-blue-600">{msg}</span>}
    </div>
  );
}

// ──────────────────────────────────────────────
// Maintenance section
// ──────────────────────────────────────────────
function MaintenanceSection() {
  const [enabled, setEnabled] = useState(false);
  const [title, setTitle] = useState("System Maintenance");
  const [message, setMessage] = useState("The system is currently under maintenance.");
  const [bannerEnabled, setBannerEnabled] = useState(false);
  const [bannerTitle, setBannerTitle] = useState("");
  const [bannerContent, setBannerContent] = useState("");
  const [bannerStart, setBannerStart] = useState("");
  const [bannerEnd, setBannerEnd] = useState("");
  const [bannerSeverity, setBannerSeverity] = useState("info");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    fetch("/api/public-state").then(r => r.json()).then((d) => {
      setEnabled(d.maintenance_mode || false);
      setTitle(d.maintenance_title || "System Maintenance");
      setMessage(d.maintenance_message || "");
      setBannerEnabled(d.banner_enabled || false);
      setBannerTitle(d.banner_title || "");
      setBannerContent(d.banner_content || "");
      setBannerStart(d.banner_start || "");
      setBannerEnd(d.banner_end || "");
      setBannerSeverity(d.banner_severity || "info");
    });
  }, []);

  const saveMaintenance = async () => {
    try {
      await api("/maintenance", "PUT", { enabled, title, message });
      setMsg(`Maintenance mode ${enabled ? "enabled" : "disabled"}.`);
    } catch (e: unknown) { setMsg(String(e)); }
  };

  const saveBanner = async () => {
    try {
      await api("/notice-banner", "PUT", {
        title: bannerTitle,
        content: bannerContent,
        start_time: bannerStart || null,
        end_time: bannerEnd || null,
        timezone: "America/Toronto",
        severity: bannerSeverity,
        enabled: bannerEnabled,
      });
      setMsg("Banner saved.");
    } catch (e: unknown) { setMsg(String(e)); }
  };

  return (
    <div className="space-y-6">
      {/* Maintenance mode */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-700">Maintenance Mode</h3>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="w-4 h-4 rounded"
          />
          <span className="text-sm">Enable maintenance mode (blocks regular users)</span>
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Maintenance page title"
          className="w-full border rounded-lg px-3 py-2 text-sm"
        />
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Message shown to users"
          rows={2}
          className="w-full border rounded-lg px-3 py-2 text-sm resize-none"
        />
        <button onClick={saveMaintenance} className="btn-primary text-sm px-3 py-2">
          {enabled ? "Enable Maintenance" : "Disable Maintenance"}
        </button>
      </div>

      <hr />

      {/* Notice banner */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-700">Notice Banner (Announcement)</h3>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={bannerEnabled}
            onChange={(e) => setBannerEnabled(e.target.checked)}
            className="w-4 h-4 rounded"
          />
          <span className="text-sm">Enable banner</span>
        </label>
        <input
          type="text"
          value={bannerTitle}
          onChange={(e) => setBannerTitle(e.target.value)}
          placeholder="Banner title"
          className="w-full border rounded-lg px-3 py-2 text-sm"
        />
        <textarea
          value={bannerContent}
          onChange={(e) => setBannerContent(e.target.value)}
          placeholder="Banner message"
          rows={2}
          className="w-full border rounded-lg px-3 py-2 text-sm resize-none"
        />
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-gray-500">Start time (ET)</label>
            <input
              type="datetime-local"
              value={bannerStart}
              onChange={(e) => setBannerStart(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm mt-1"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500">End time (ET)</label>
            <input
              type="datetime-local"
              value={bannerEnd}
              onChange={(e) => setBannerEnd(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm mt-1"
            />
          </div>
        </div>
        <p className="text-xs text-gray-400">Timezone: America/Toronto (ET) — displayed to users</p>
        <select
          value={bannerSeverity}
          onChange={(e) => setBannerSeverity(e.target.value)}
          className="border rounded-lg px-3 py-2 text-sm"
        >
          <option value="info">ℹ️ Info</option>
          <option value="warning">⚠️ Warning</option>
        </select>
        <button onClick={saveBanner} className="btn-primary text-sm px-3 py-2">Save Banner</button>
      </div>
      {msg && <p className="text-xs text-blue-600">{msg}</p>}
    </div>
  );
}

// ──────────────────────────────────────────────
// Logs section
// ──────────────────────────────────────────────
function LogsSection() {
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState("");
  const [isError, setIsError] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "50" });
      if (keyword) params.set("keyword", keyword);
      if (isError !== null) params.set("is_error", String(isError));
      const r = await api(`/logs?${params}`);
      setLogs(r.items);
      setTotal(r.total);
    } catch (e: unknown) { console.error(e); }
    setLoading(false);
  }, [page, keyword, isError]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = () => {
    window.open("/api/admin/logs/export/csv", "_blank");
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2 flex-wrap items-center">
        <input
          type="text"
          value={keyword}
          onChange={(e) => { setKeyword(e.target.value); setPage(1); }}
          placeholder="Search keyword…"
          className="border rounded-lg px-3 py-2 text-sm flex-1 min-w-40"
        />
        <select
          value={isError === null ? "" : String(isError)}
          onChange={(e) => {
            setIsError(e.target.value === "" ? null : e.target.value === "true");
            setPage(1);
          }}
          className="border rounded-lg px-3 py-2 text-sm"
        >
          <option value="">All</option>
          <option value="false">Success</option>
          <option value="true">Errors only</option>
        </select>
        <button onClick={exportCsv} className="btn-secondary text-sm">↓ Export CSV</button>
      </div>

      <p className="text-xs text-gray-500">{total} records</p>

      {loading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : logs.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-8">No logs found.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-gray-50 text-left">
                {["Time", "Session", "Question", "Browser", "City", "Ms", "Status"].map(h => (
                  <th key={h} className="px-3 py-2 border-b font-semibold text-gray-600">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} className={`border-b hover:bg-gray-50 ${l.is_error ? "bg-red-50" : ""}`}>
                  <td className="px-3 py-2 whitespace-nowrap">{l.requested_at.replace("T", " ").slice(0, 19)}</td>
                  <td className="px-3 py-2 font-mono">{l.session_id.slice(0, 12)}…</td>
                  <td className="px-3 py-2 max-w-xs truncate">{l.question_summary}</td>
                  <td className="px-3 py-2">{l.browser_name}</td>
                  <td className="px-3 py-2">{l.city || "—"}</td>
                  <td className="px-3 py-2">{l.response_ms}</td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded text-xs ${l.is_error ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"}`}>
                      {l.is_error ? "Error" : "OK"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex gap-2 items-center">
        <button
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1}
          className="btn-secondary text-xs px-2 py-1 disabled:opacity-50"
        >← Prev</button>
        <span className="text-xs text-gray-500">Page {page}</span>
        <button
          onClick={() => setPage((p) => p + 1)}
          disabled={logs.length < 50}
          className="btn-secondary text-xs px-2 py-1 disabled:opacity-50"
        >Next →</button>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────
// Audit logs section
// ──────────────────────────────────────────────
function AuditSection() {
  const [items, setItems] = useState<Array<{ id: number; admin_email: string; action: string; result: string; created_at: string }>>([]);
  useEffect(() => {
    api("/audit-logs").then((r) => setItems(r.items)).catch(console.error);
  }, []);
  return (
    <div className="overflow-x-auto">
      {items.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-4">No audit events yet.</p>
      ) : (
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-50 text-left">
              {["Time", "Admin", "Action", "Result"].map(h => (
                <th key={h} className="px-3 py-2 border-b font-semibold text-gray-600">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id} className="border-b hover:bg-gray-50">
                <td className="px-3 py-2 whitespace-nowrap">{a.created_at.slice(0, 19).replace("T", " ")}</td>
                <td className="px-3 py-2">{a.admin_email}</td>
                <td className="px-3 py-2">{a.action}</td>
                <td className="px-3 py-2">
                  <span className={`px-1.5 py-0.5 rounded text-xs ${a.result === "success" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                    {a.result}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────
// Main admin page
// ──────────────────────────────────────────────
type Tab = "dashboard" | "notebooklm" | "themes" | "language" | "maintenance" | "logs" | "audit";

const TABS: Array<{ id: Tab; label: string; icon: string }> = [
  { id: "dashboard", label: "Dashboard", icon: "📊" },
  { id: "notebooklm", label: "NotebookLM", icon: "🔗" },
  { id: "themes", label: "Themes", icon: "🎨" },
  { id: "language", label: "Language", icon: "🌐" },
  { id: "maintenance", label: "Maintenance", icon: "🔧" },
  { id: "logs", label: "Chat Logs", icon: "📋" },
  { id: "audit", label: "Audit Log", icon: "🔍" },
];

export default function AdminPage() {
  const { isAdmin, adminEmail, checkSession, openLoginDialog } = useAdmin();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("dashboard");
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    // Handle OAuth redirect result
    const params = new URLSearchParams(window.location.search);
    const authResult = params.get("auth");
    if (authResult) {
      // Clean up URL
      window.history.replaceState({}, "", "/admin");
      if (authResult === "success") {
        checkSession();
      }
    }
    checkSession().finally(() => setAuthChecked(true));
  }, [checkSession]);

  useEffect(() => {
    if (!authChecked || isAdmin) {
      return;
    }
    openLoginDialog();
    router.replace("/");
  }, [authChecked, isAdmin, openLoginDialog, router]);

  if (!authChecked || !isAdmin) {
    return (
      <div className="flex items-center justify-center h-screen">
        <p className="text-gray-500">Checking authentication…</p>
      </div>
    );
  }

  const sectionTitles: Record<Tab, string> = {
    dashboard: "Dashboard",
    notebooklm: "NotebookLM URL & Re-authentication",
    themes: "Theme Management",
    language: "Default Language",
    maintenance: "Maintenance & Banners",
    logs: "Chat Request Logs",
    audit: "Admin Audit Log",
  };

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      {/* Top bar */}
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-gray-400 hover:text-gray-600 transition-colors" title="Back to chat">
            ←
          </Link>
          <h1 className="text-lg font-bold text-gray-800">🛡 Admin Panel</h1>
        </div>
        <p className="text-sm text-gray-500">{adminEmail}</p>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <nav className="w-52 bg-white border-r shrink-0 py-4 space-y-1 overflow-y-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`w-full flex items-center gap-2 px-4 py-2.5 text-sm transition-colors text-left ${
                tab === t.id
                  ? "bg-blue-50 text-blue-700 font-semibold border-r-2 border-blue-600"
                  : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              <span aria-hidden="true">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto p-6">
          <SectionCard title={sectionTitles[tab]}>
            {tab === "dashboard" && <DashboardSection />}
            {tab === "notebooklm" && <NotebookLMSection />}
            {tab === "themes" && <ThemeSection />}
            {tab === "language" && <LanguageSectionAdmin />}
            {tab === "maintenance" && <MaintenanceSection />}
            {tab === "logs" && <LogsSection />}
            {tab === "audit" && <AuditSection />}
          </SectionCard>
        </main>
      </div>
    </div>
  );
}
