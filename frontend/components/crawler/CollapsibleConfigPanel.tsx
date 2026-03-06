"use client";

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

interface ScrapeConfig {
  school_url: string;
  schedule_enabled: boolean;
  schedule_time: string;
  output_dir: string;
  timeout: number;
  respect_robots_txt: boolean;
}

interface CollapsibleConfigPanelProps {
  onConfigSaved?: () => void;
}

export function CollapsibleConfigPanel({ onConfigSaved }: CollapsibleConfigPanelProps) {
  const [config, setConfig] = useState<ScrapeConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    loadConfig();
  }, []);

  async function loadConfig() {
    setLoading(true);
    try {
      const data = await api.getScrapeConfig();
      if (data.success && data.data) {
        setConfig(data.data);
      } else {
        setMessage(data.error || 'Failed to load configuration');
      }
    } catch (error) {
      console.error('Failed to load config:', error);
      setMessage('Failed to load configuration');
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!config) return;

    setSaving(true);
    setMessage('');

    try {
      await api.saveScrapeConfig(config);
      setMessage('Configuration saved!');
      onConfigSaved?.();
    } catch (error) {
      console.error('Failed to save config:', error);
      setMessage('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  }

  if (loading || !config) {
    return <div className="text-gray-900">Loading configuration...</div>;
  }

  return (
    <details className="bg-white rounded-lg shadow">
      <summary className="p-4 cursor-pointer hover:bg-gray-50 text-gray-900 font-medium">
        Configuration
      </summary>
      <form onSubmit={handleSave} className="p-4 pt-0 space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700">
            School URL
          </label>
          <input
            type="url"
            value={config.school_url}
            onChange={(e) => setConfig({ ...config, school_url: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded text-gray-900"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1 text-gray-700">
            Schedule Time
          </label>
          <input
            type="time"
            value={config.schedule_time}
            onChange={(e) => setConfig({ ...config, schedule_time: e.target.value })}
            className="px-3 py-2 border border-gray-300 rounded text-gray-900"
          />
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="schedule-enabled"
            checked={config.schedule_enabled}
            onChange={(e) => setConfig({ ...config, schedule_enabled: e.target.checked })}
            className="w-4 h-4"
          />
          <label htmlFor="schedule-enabled" className="text-sm text-gray-900">
            Enable scheduled scraping
          </label>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>

        {message && (
          <div className={`text-sm font-medium ${message.includes('saved') ? 'text-green-600' : 'text-red-600'}`}>
            {message}
          </div>
        )}
      </form>
    </details>
  );
}
