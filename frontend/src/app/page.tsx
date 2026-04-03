"use client";

import ChatContainer from "@/components/ChatContainer";
import Header from "@/components/Header";
import MaintenanceBanner from "@/components/MaintenanceBanner";
import MaintenancePage from "@/components/MaintenancePage";
import ConfigChangePrompt from "@/components/ConfigChangePrompt";
import { useConfigPolling } from "@/components/useConfigPolling";
import { useAdmin } from "@/components/AdminContext";

export default function Home() {
  const { isAdmin } = useAdmin();
  const {
    showRefreshPrompt,
    maintenanceMode,
    maintenanceTitle,
    maintenanceMessage,
    maintenanceStart,
    maintenanceEnd,
    snooze,
    refresh,
  } = useConfigPolling();

  // Admins always bypass maintenance mode
  const showMaintenance = maintenanceMode && !isAdmin;

  return (
    <main className="h-screen flex flex-col bg-gradient-to-br from-blue-50 to-indigo-50 overflow-hidden">
      <Header />
      <MaintenanceBanner />
      {showMaintenance ? (
        <div className="flex-1 overflow-hidden">
          <MaintenancePage
            title={maintenanceTitle}
            message={maintenanceMessage}
            startTime={maintenanceStart}
            endTime={maintenanceEnd}
          />
        </div>
      ) : (
        <ChatContainer
          inputBlocked={showRefreshPrompt}
          blockReason="A system update is ready. Please refresh before sending a new message."
        />
      )}
      <ConfigChangePrompt show={showRefreshPrompt} onSnooze={snooze} onRefresh={refresh} />
    </main>
  );
}
