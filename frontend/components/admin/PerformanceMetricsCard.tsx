'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

interface PerformanceSummary {
  total_queries: number;
  avg_response_time_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
}

interface PerformanceBreakdown {
  count: number;
  avg_ms: number;
  total_ms: number;
}

interface PerformanceMetrics {
  status: string;
  summary: PerformanceSummary;
  by_language: Record<string, PerformanceBreakdown>;
  by_path: Record<string, PerformanceBreakdown>;
  stages: Record<string, any>;
}

export function PerformanceMetricsCard() {
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState<PerformanceMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchMetrics = async () => {
    try {
      setError(null);
      const response = await api.getPerformanceMetrics();

      if (response.success && response.data) {
        setMetrics(response.data as PerformanceMetrics);
        setLastUpdate(new Date());
      } else {
        setError(response.error || 'Failed to fetch performance metrics');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMetrics();

    if (autoRefresh) {
      const interval = setInterval(fetchMetrics, 30000); // Refresh every 30 seconds
      return () => clearInterval(interval);
    }
  }, [autoRefresh]);

  const formatDuration = (ms: number): string => {
    if (ms < 1000) return `${ms.toFixed(2)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <span className="ml-3 text-gray-800">Loading performance metrics...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
        <p className="text-red-800">{error}</p>
        <button
          onClick={fetchMetrics}
          className="mt-2 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!metrics) return null;

  return (
    <div className="space-y-6">
      {/* Header with Auto-Refresh Control */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Performance Metrics</h2>
          <p className="text-sm text-gray-600 mt-1">
            Last updated: {lastUpdate.toLocaleTimeString()}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
            />
            Auto-refresh (30s)
          </label>
          <button
            onClick={fetchMetrics}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Refresh Now
          </button>
        </div>
      </div>

      {/* Summary Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm text-gray-800">Total Queries</div>
          <div className="text-3xl font-bold text-blue-600 mt-2">
            {metrics.summary.total_queries}
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm text-gray-800">Avg Response</div>
          <div className="text-3xl font-bold text-green-600 mt-2">
            {formatDuration(metrics.summary.avg_response_time_ms)}
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm text-gray-800">P95 Latency</div>
          <div className="text-3xl font-bold text-yellow-600 mt-2">
            {formatDuration(metrics.summary.p95_ms)}
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <div className="text-sm text-gray-800">P99 Latency</div>
          <div className="text-3xl font-bold text-red-600 mt-2">
            {formatDuration(metrics.summary.p99_ms)}
          </div>
        </div>
      </div>

      {/* Breakdown by Language */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Performance by Language</h3>

        {Object.keys(metrics.by_language).length === 0 ? (
          <p className="text-gray-600">No language data available yet</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left p-3 text-gray-900">Language</th>
                  <th className="text-right p-3 text-gray-900">Queries</th>
                  <th className="text-right p-3 text-gray-900">Avg Time</th>
                  <th className="text-right p-3 text-gray-900">Total Time</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(metrics.by_language)
                  .sort(([, a], [, b]) => b.count - a.count)
                  .map(([lang, data]) => (
                    <tr key={lang} className="border-t">
                      <td className="p-3 text-gray-900 font-medium">{lang}</td>
                      <td className="p-3 text-right text-gray-900">{data.count}</td>
                      <td className="p-3 text-right text-gray-900">
                        {formatDuration(data.avg_ms)}
                      </td>
                      <td className="p-3 text-right text-gray-900">
                        {formatDuration(data.total_ms)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Breakdown by Path */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Performance by Path</h3>

        {Object.keys(metrics.by_path).length === 0 ? (
          <p className="text-gray-600">No path data available yet</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-left p-3 text-gray-900">API Path</th>
                  <th className="text-right p-3 text-gray-900">Queries</th>
                  <th className="text-right p-3 text-gray-900">Avg Time</th>
                  <th className="text-right p-3 text-gray-900">Total Time</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(metrics.by_path)
                  .sort(([, a], [, b]) => b.count - a.count)
                  .map(([path, data]) => (
                    <tr key={path} className="border-t">
                      <td className="p-3 text-gray-900 font-medium break-all">{path}</td>
                      <td className="p-3 text-right text-gray-900">{data.count}</td>
                      <td className="p-3 text-right text-gray-900">
                        {formatDuration(data.avg_ms)}
                      </td>
                      <td className="p-3 text-right text-gray-900">
                        {formatDuration(data.total_ms)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Stage Performance (if available) */}
      {Object.keys(metrics.stages).length > 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Pipeline Stage Performance</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(metrics.stages).map(([stage, data]: [string, any]) => (
              <div key={stage} className="bg-gray-50 rounded-lg p-4">
                <div className="text-sm text-gray-800 capitalize">{stage.replace(/_/g, ' ')}</div>
                <div className="text-xl font-bold text-gray-900 mt-1">
                  {formatDuration(data.avg_ms || 0)}
                </div>
                <div className="text-xs text-gray-600 mt-1">
                  {data.count || 0} operations
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
