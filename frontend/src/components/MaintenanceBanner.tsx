"use client";

import { useCallback, useEffect, useState } from "react";

interface BannerState {
  banner_enabled: boolean;
  banner_title: string;
  banner_content: string;
  banner_start: string | null;
  banner_end: string | null;
  banner_timezone: string;
  banner_severity: string;
  banner_version: number;
}

const SESSION_KEY = "stl_dismissed_banner_v";

export default function MaintenanceBanner() {
  const [banner, setBanner] = useState<BannerState | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const loadBanner = useCallback(async () => {
    try {
      const response = await fetch("/api/public-state", { cache: "no-store" });
      if (!response.ok) {
        return;
      }

      const data = await response.json() as BannerState;
      if (!data.banner_enabled) {
        setBanner(null);
        setDismissed(false);
        return;
      }

      setBanner(data);
      const dismissedVersion = sessionStorage.getItem(SESSION_KEY);
      setDismissed(dismissedVersion === String(data.banner_version));
    } catch {
      // Ignore banner fetch failures.
    }
  }, []);

  useEffect(() => {
    loadBanner();
    const intervalId = window.setInterval(loadBanner, 30_000);
    return () => window.clearInterval(intervalId);
  }, [loadBanner]);

  if (!banner || !banner.banner_enabled || dismissed) return null;

  const bg = banner.banner_severity === "warning"
    ? "bg-amber-50 border-amber-400 text-amber-900"
    : "bg-blue-50 border-blue-400 text-blue-900";
  const icon = banner.banner_severity === "warning" ? "⚠️" : "ℹ️";

  const formatTime = (iso: string | null, tz: string) => {
    if (!iso) return "";
    try {
      return new Intl.DateTimeFormat("en-CA", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: tz,
      }).format(new Date(iso));
    } catch {
      return iso;
    }
  };

  const tzAbbr = banner.banner_timezone === "America/Toronto" ? "ET" : banner.banner_timezone;

  return (
    <div
      className={`border-b px-4 py-3 ${bg}`}
      role="alert"
      aria-live="polite"
    >
      <div className="max-w-6xl mx-auto flex items-start gap-3">
        <span className="text-lg mt-0.5 shrink-0" aria-hidden="true">{icon}</span>
        <div className="flex-1 min-w-0">
          {banner.banner_title && (
            <p className="font-semibold text-sm">{banner.banner_title}</p>
          )}
          {banner.banner_content && (
            <p className="text-sm mt-0.5">{banner.banner_content}</p>
          )}
          {(banner.banner_start || banner.banner_end) && (
            <p className="text-xs mt-1 opacity-80">
              Planned maintenance:{" "}
              {banner.banner_start && formatTime(banner.banner_start, banner.banner_timezone)}{" "}
              {banner.banner_start && banner.banner_end && "–"}{" "}
              {banner.banner_end && formatTime(banner.banner_end, banner.banner_timezone)}
              {" "}({tzAbbr} / {banner.banner_timezone})
            </p>
          )}
        </div>
        <button
          onClick={() => {
            try { sessionStorage.setItem(SESSION_KEY, String(banner.banner_version)); } catch (_) {}
            setDismissed(true);
          }}
          className="shrink-0 text-sm opacity-60 hover:opacity-100 transition-opacity p-1"
          aria-label="Dismiss maintenance notice"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
