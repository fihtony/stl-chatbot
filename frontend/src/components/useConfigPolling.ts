"use client";

import { useEffect, useCallback, useRef, useState } from "react";

const POLL_INTERVAL_MS = 30_000;
const SNOOZE_MS = 10 * 60_000;
const SESSION_KEY = "stl_config_version";
const DRAFT_KEY = "stl_chat_draft";

export interface ConfigPollState {
  showRefreshPrompt: boolean;
  maintenanceMode: boolean;
  maintenanceTitle: string;
  maintenanceMessage: string;
  maintenanceStart: string | null;
  maintenanceEnd: string | null;
  snooze: () => void;
  refresh: () => void;
}

export function useConfigPolling(): ConfigPollState {
  const [showRefreshPrompt, setShowRefreshPrompt] = useState(false);
  const [maintenanceMode, setMaintenanceMode] = useState(false);
  const [maintenanceTitle, setMaintenanceTitle] = useState("System Maintenance");
  const [maintenanceMessage, setMaintenanceMessage] = useState("The chatbot is currently under maintenance. Please check back later.");
  const [maintenanceStart, setMaintenanceStart] = useState<string | null>(null);
  const [maintenanceEnd, setMaintenanceEnd] = useState<string | null>(null);
  const knownVersion = useRef<number | null>(null);
  const latestVersion = useRef<number>(1);
  const snoozeUntil = useRef<number>(0);
  const previousMaintenanceMode = useRef<boolean>(false);

  const persistDraft = useCallback(() => {
    const input = document.querySelector<HTMLTextAreaElement>("[data-chat-input]");
    if (input?.value) {
      try {
        sessionStorage.setItem(DRAFT_KEY, input.value);
      } catch {
        // Ignore session storage errors.
      }
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      const [versionRes, stateRes] = await Promise.all([
        fetch("/api/config/version", { cache: "no-store" }),
        fetch("/api/public-state", { cache: "no-store" }),
      ]);

      if (versionRes.ok) {
        const versionData = await versionRes.json();
        const newVersion: number = versionData.config_version ?? 1;
        latestVersion.current = newVersion;

        if (knownVersion.current === null) {
          const stored = sessionStorage.getItem(SESSION_KEY);
          const parsedStored = stored ? parseInt(stored, 10) : Number.NaN;
          knownVersion.current = Number.isFinite(parsedStored) ? parsedStored : newVersion;
          if (!stored) {
            sessionStorage.setItem(SESSION_KEY, String(newVersion));
          }
      }

        if (newVersion > (knownVersion.current ?? newVersion) && Date.now() >= snoozeUntil.current) {
          setShowRefreshPrompt(true);
        }
      }

      if (stateRes.ok) {
        const data = await stateRes.json();
        const maint: boolean = data.maintenance_mode === true;
        setMaintenanceMode(maint);
        setMaintenanceTitle(data.maintenance_title || "System Maintenance");
        setMaintenanceMessage(data.maintenance_message || "The chatbot is currently under maintenance. Please check back later.");
        setMaintenanceStart(data.maintenance_start || null);
        setMaintenanceEnd(data.maintenance_end || null);

        if (maint && !previousMaintenanceMode.current) {
          persistDraft();
        }
        previousMaintenanceMode.current = maint;
      }
    } catch {
      // Silently ignore network errors in polling
    }
  }, [persistDraft]);

  useEffect(() => {
    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    // Resume polling when tab becomes visible
    const onVisible = () => { if (document.visibilityState === "visible") poll(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [poll]);

  const snooze = useCallback(() => {
    snoozeUntil.current = Date.now() + SNOOZE_MS;
    setShowRefreshPrompt(false);
  }, []);

  const refresh = useCallback(() => {
    persistDraft();
    try {
      const nextVersion = latestVersion.current || knownVersion.current || 1;
      sessionStorage.setItem(SESSION_KEY, String(nextVersion));
      knownVersion.current = nextVersion;
    } catch {
      // Ignore session storage errors.
    }
    setShowRefreshPrompt(false);
    window.location.reload();
  }, [persistDraft]);

  return {
    showRefreshPrompt,
    maintenanceMode,
    maintenanceTitle,
    maintenanceMessage,
    maintenanceStart,
    maintenanceEnd,
    snooze,
    refresh,
  };
}
