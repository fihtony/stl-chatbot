"use client";

import { useState, useEffect } from 'react';
import { api as apiClient } from '@/lib/api';
import type { ScrapeStatus as BackendScrapeStatus } from '@/lib/api';

interface ScrapingStatusCardProps {
  onIndex?: () => void;
  indexing?: boolean;
  indexProgress?: number;
  onScrapeRunningChange?: (running: boolean) => void;
  onStopScrape?: () => void;
  scrapeRunning?: boolean;  // External scrape running state from parent
}

// Component-internal camelCase interface (transformed from backend snake_case)
interface ScrapingStatus {
  isRunning: boolean;
  pagesCrawled: number;
  newPages: number;
  pdfsDownloaded: number;
  newDocuments: number;
  totalPdfs: number;
  currentPage: string;
  startTime: number;
  lastRunTime: string;
  nextRunTime: string;
  errorMessage?: string;
  hasNewContent: boolean;
}

// Transform backend snake_case to component camelCase
function transformStatus(apiStatus: BackendScrapeStatus): ScrapingStatus {
  return {
    isRunning: apiStatus.is_running,
    pagesCrawled: apiStatus.total_pages || 0,
    newPages: apiStatus.new_pages || 0,
    pdfsDownloaded: apiStatus.downloaded_pdfs || 0,
    newDocuments: apiStatus.new_documents || 0,
    totalPdfs: apiStatus.total_pdfs || 0,
    currentPage: apiStatus.current_page || '',
    startTime: apiStatus.start_time || 0,
    lastRunTime: apiStatus.last_run || '',
    nextRunTime: '',  // Will be populated if backend adds this
    errorMessage: apiStatus.error_message || '',
    hasNewContent: false,  // Will be determined by checking content status
  };
}

export function ScrapingStatusCard({ onIndex, indexing, indexProgress, onScrapeRunningChange, onStopScrape, scrapeRunning = false }: ScrapingStatusCardProps) {
  const [status, setStatus] = useState<ScrapingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [stopping, setStopping] = useState(false);

  // Initial load
  useEffect(() => {
    loadStatus();
  }, []);

  // Respond to external scrapeRunning state from parent (e.g., triggered by scheduler)
  useEffect(() => {
    // If parent says scrape is running but our state shows stopped, refresh immediately
    if (scrapeRunning && status && !status.isRunning) {
      console.log('[ScrapingCard] Parent detected running scrape, refreshing...');
      loadStatus();
    }
    // If parent says scrape stopped but our state shows running, refresh to confirm
    if (!scrapeRunning && status && status.isRunning) {
      console.log('[ScrapingCard] Parent detected scrape stopped, refreshing...');
      loadStatus();
    }
  }, [scrapeRunning]);

  // Notify parent when running state changes
  useEffect(() => {
    if (status && onScrapeRunningChange) {
      onScrapeRunningChange(status.isRunning);
    }
  }, [status?.isRunning, onScrapeRunningChange]);

  // Hybrid polling: only when running
  useEffect(() => {
    if (!status?.isRunning) return;

    const interval = setInterval(async () => {
      const response = await apiClient.getScrapeStatus();
      if (response.success && response.data) {
        const newStatus = transformStatus(response.data);

        // Check for transition: running -> stopped
        if (status.isRunning && !newStatus.isRunning) {
          checkNewContent();
        }

        setStatus(newStatus);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [status?.isRunning]);

  async function loadStatus() {
    setLoading(true);
    try {
      const response = await apiClient.getScrapeStatus();
      if (response.success && response.data) {
        setStatus(transformStatus(response.data));
      }
    } catch (error) {
      console.error('Failed to load status:', error);
    } finally {
      setLoading(false);
    }
  }

  async function checkNewContent() {
    // Will implement in later task
  }

  async function handleTrigger() {
    if (status?.isRunning) {
      // Should not happen - button should be disabled
      return;
    }

    setTriggering(true);
    try {
      await apiClient.triggerScrape();
      await loadStatus();
    } catch (error) {
      console.error('Failed to trigger scrape:', error);
    } finally {
      setTriggering(false);
    }
  }

  async function handleStop() {
    setStopping(true);
    try {
      if (onStopScrape) {
        await onStopScrape();
      }
      setTriggering(false);
      setStatus(prev => prev ? { ...prev, isRunning: false } : null);
    } catch (error) {
      console.error('Failed to stop scrape:', error);
    } finally {
      setStopping(false);
    }
  }

  if (loading || !status) {
    return <div className="p-4">Loading...</div>;
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center gap-2 mb-4">
        <div className={`w-3 h-3 rounded-full ${status.isRunning ? 'bg-green-500' : 'bg-gray-400'}`} />
        <h2 className="text-xl font-semibold text-gray-900">
          {status.isRunning ? 'Running' : 'Stopped'}
        </h2>
      </div>

      {/* Progress */}
      <div className="space-y-1 mb-4 text-gray-900">
        <div>Pages Processed: {status.pagesCrawled} <span className="text-green-600">({status.newPages} new)</span></div>
        <div>Documents Downloaded: {status.pdfsDownloaded} / {status.totalPdfs} <span className="text-green-600">({status.newDocuments} new)</span></div>
        {status.currentPage && <div className="text-sm text-gray-600 truncate">Current: {status.currentPage}</div>}
      </div>

      {/* Time info */}
      <div className="space-y-1 mb-4 text-sm text-gray-600">
        {status.isRunning && status.startTime && (
          <div>Running: {formatDuration(status.startTime)}</div>
        )}
        {status.lastRunTime && <div>Last run: {status.lastRunTime}</div>}
        {status.nextRunTime && <div>Next run: {status.nextRunTime}</div>}
      </div>

      {/* Error or Progress Message */}
      {status.errorMessage && (
        <div className={`mb-4 p-2 rounded text-sm ${
          status.errorMessage.includes('Error') || status.errorMessage.includes('404') || status.errorMessage.includes('Timeout')
            ? 'bg-red-50 text-red-700'
            : 'bg-blue-50 text-blue-700'
        }`}>
          {status.errorMessage}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        {!status.isRunning ? (
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {triggering ? 'Starting...' : 'Start Scrape'}
          </button>
        ) : (
          <button
            onClick={handleStop}
            disabled={stopping}
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {stopping ? 'Stopping...' : 'Stop Scrape'}
          </button>
        )}

        {status.hasNewContent && onIndex && (
          <button
            onClick={onIndex}
            disabled={indexing}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
          >
            {indexing ? `Indexing ${indexProgress}%` : 'Create Index'}
          </button>
        )}
      </div>
    </div>
  );
}

function formatDuration(startTime: number): string {
  // Backend sends Unix timestamp (seconds since epoch)
  // Convert to milliseconds for Date calculation
  const startTimeMs = startTime * 1000;
  const elapsedMs = Date.now() - startTimeMs;
  const seconds = Math.floor(elapsedMs / 1000);

  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}
