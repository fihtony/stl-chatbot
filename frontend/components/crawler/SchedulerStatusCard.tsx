"use client";

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { JOB_STATUS, getStatusDisplay } from '@/lib/constants';

interface SchedulerStatus {
  enabled: boolean;
  schedule_time: string;
  running: boolean;
  next_run: string;
  jobs: number;
  last_run_status?: 'completed' | 'error' | null;
  last_run_time?: string | null;
}

interface SchedulerStatusCardProps {
  onConfigChange?: () => void;
  scrapeRunning?: boolean;  // Whether a scrape is actually in progress
  onScrapeRunningChange?: (running: boolean) => void;  // Callback when scrape running state changes
}

const FAST_POLLING_TIMEOUT = 3 * 60 * 1000; // 3 minutes

export function SchedulerStatusCard({ onConfigChange, scrapeRunning = false, onScrapeRunningChange }: SchedulerStatusCardProps) {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [fastPolling, setFastPolling] = useState(false);
  const [fastPollingStartTime, setFastPollingStartTime] = useState<number>(0);

  // Check scrape status on mount - in case a scrape is already running
  useEffect(() => {
    checkScrapeStatusOnMount();
    loadStatus();
    // Refresh every 30 seconds normally
    const interval = setInterval(loadStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  async function checkScrapeStatusOnMount() {
    try {
      const scrapeResponse = await api.getScrapeStatus();
      if (scrapeResponse.success && scrapeResponse.data?.is_running) {
        console.log('[Scheduler] Scrape already running on mount');
        if (onScrapeRunningChange) onScrapeRunningChange(true);
      }
    } catch (error) {
      console.error('Failed to check scrape status on mount:', error);
    }
  }

  // Effect to handle fast polling when scheduler triggers
  useEffect(() => {
    if (!fastPolling) {
      setFastPollingStartTime(0);
      return;
    }

    if (fastPollingStartTime === 0) {
      setFastPollingStartTime(Date.now());
    }

    const interval = setInterval(async () => {
      // Check if timeout exceeded
      const elapsed = Date.now() - fastPollingStartTime;
      if (elapsed > FAST_POLLING_TIMEOUT) {
        console.log('[Scheduler] Fast polling timeout - no scrape detected');
        setFastPolling(false);
        setFastPollingStartTime(0);
        // Reload status to get updated next_run time
        await loadStatus();
        return;
      }

      // Check if scrape started running
      const scrapeResponse = await api.getScrapeStatus();
      if (scrapeResponse.success && scrapeResponse.data?.is_running) {
        console.log('[Scheduler] Scrape detected - stopping fast polling');
        setFastPolling(false);
        setFastPollingStartTime(0);
        if (onScrapeRunningChange) onScrapeRunningChange(true);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [fastPolling, fastPollingStartTime, onScrapeRunningChange]);

  // Effect to set up scheduler timer - triggers at next run time
  useEffect(() => {
    if (!status?.enabled || !status?.next_run || scrapeRunning || fastPolling) return;

    const nextRunTime = new Date(status.next_run);
    const now = new Date();
    const delay = nextRunTime.getTime() - now.getTime();

    // Only set timer if next run is in the future (within 1 hour)
    if (delay > 0 && delay < 3600000) {
      console.log(`[Scheduler Timer] Setting timer for ${status.next_run} (delay: ${Math.round(delay / 1000)}s)`);
      const timerId = setTimeout(async () => {
        console.log(`[Scheduler Timer] Triggered at ${new Date().toLocaleTimeString()}`);
        // Load status to check if scheduler started
        await loadStatus();
        // Start fast polling to detect when scrape starts
        setFastPolling(true);
      }, delay);

      return () => clearTimeout(timerId);
    }
  }, [status?.enabled, status?.next_run, scrapeRunning, fastPolling]);

  async function loadStatus() {
    try {
      const response = await api.getSchedulerStatus();
      if (response.success && response.data) {
        setStatus(response.data);
      }
    } catch (error) {
      console.error('Failed to load scheduler status:', error);
    } finally {
      setLoading(false);
    }
  }

  // Determine the scheduler badge state
  function getSchedulerState(): { label: string; bgColor: string; textColor: string; dotColor: string } {
    if (scrapeRunning) {
      return { label: 'Running', bgColor: 'bg-green-100', textColor: 'text-green-800', dotColor: 'bg-green-500' };
    }
    if (!status?.enabled) {
      return { label: 'Disabled', bgColor: 'bg-gray-100', textColor: 'text-gray-700', dotColor: 'bg-gray-400' };
    }
    if (status.last_run_status === 'completed') {
      return { label: 'Completed', bgColor: 'bg-purple-100', textColor: 'text-purple-800', dotColor: 'bg-purple-500' };
    }
    if (status.last_run_status === 'error') {
      return { label: 'Error', bgColor: 'bg-red-100', textColor: 'text-red-800', dotColor: 'bg-red-500' };
    }
    // Default: enabled, not running, no recent completion/error
    return { label: 'Active', bgColor: 'bg-blue-100', textColor: 'text-blue-800', dotColor: 'bg-blue-500' };
  }

  function formatNextRun(isoString: string): string {
    if (!isoString) return 'Not scheduled';
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = date.getTime() - now.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays > 0) {
      return `In ${diffDays} day${diffDays > 1 ? 's' : ''} at ${date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
    } else if (diffHours > 0) {
      return `In ${diffHours} hour${diffHours > 1 ? 's' : ''} at ${date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
    } else if (diffHours === 0) {
      return `Today at ${date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}`;
    }
    return date.toLocaleString();
  }

  if (loading || !status) {
    return <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4 text-gray-900">Scheduler</h3>
      <div className="text-sm text-gray-900">Loading...</div>
    </div>;
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">Scheduler</h3>
        <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${getSchedulerState().bgColor} ${getSchedulerState().textColor}`}>
          <div className={`w-2 h-2 rounded-full ${getSchedulerState().dotColor} ${scrapeRunning ? 'animate-pulse' : ''}`} />
          {getSchedulerState().label}
        </div>
      </div>

      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-700 font-medium">Schedule:</span>
          <span className="text-gray-900">
            {status.enabled ? `${status.schedule_time}` : 'Disabled'}
          </span>
        </div>

        {status.enabled && status.next_run && !scrapeRunning && (
          <div className="flex justify-between">
            <span className="text-gray-700 font-medium">Next run:</span>
            <span className="text-gray-900">{formatNextRun(status.next_run)}</span>
          </div>
        )}

        {status.last_run_time && (
          <div className="flex justify-between">
            <span className="text-gray-700 font-medium">Last run:</span>
            <span className="text-gray-900">{status.last_run_time}</span>
          </div>
        )}

        {status.last_run_status && status.last_run_time && !scrapeRunning && (() => {
          const statusDisplay = getStatusDisplay(status.last_run_status);
          return (
            <div className="flex justify-between">
              <span className="text-gray-700 font-medium">Last status:</span>
              <span className={`font-medium ${statusDisplay.color}`}>
                {statusDisplay.label}
              </span>
            </div>
          );
        })()}

        {!status.last_run_time && !scrapeRunning && (
          <div className="flex justify-between">
            <span className="text-gray-700 font-medium">Last run:</span>
            <span className="text-gray-400 italic">Not run yet</span>
          </div>
        )}

        {scrapeRunning && (
          <div className="flex justify-between">
            <span className="text-gray-700 font-medium">Status:</span>
            <span className="text-green-600 font-medium">Scraping in progress...</span>
          </div>
        )}
      </div>

      <div className="mt-4 p-3 bg-blue-50 rounded-lg text-xs text-blue-800">
        💡 The scheduler automatically runs scraping at the scheduled time.
        It will skip if a scrape is already running.
      </div>
    </div>
  );
}
