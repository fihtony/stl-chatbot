import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MaintenanceBanner from '@/components/MaintenanceBanner';

const mockFetch = jest.fn();
global.fetch = mockFetch;

let consoleErrorSpy: jest.SpyInstance;

describe('MaintenanceBanner integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('renders the maintenance banner with timezone details when enabled', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        banner_enabled: true,
        banner_title: 'Scheduled maintenance',
        banner_content: 'Expect downtime tonight.',
        banner_start: '2026-04-02T21:00:00',
        banner_end: '2026-04-02T22:00:00',
        banner_timezone: 'America/Toronto',
        banner_severity: 'warning',
        banner_version: 3,
      }),
    });

    render(<MaintenanceBanner />);

    await waitFor(() => {
      expect(screen.getByText('Scheduled maintenance')).toBeInTheDocument();
    });
    expect(screen.getByText('Expect downtime tonight.')).toBeInTheDocument();
    expect(screen.getByText(/ET \/ America\/Toronto/)).toBeInTheDocument();
  });

  it('dismisses the current banner version for the session', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        banner_enabled: true,
        banner_title: 'Scheduled maintenance',
        banner_content: 'Expect downtime tonight.',
        banner_start: null,
        banner_end: null,
        banner_timezone: 'America/Toronto',
        banner_severity: 'info',
        banner_version: 7,
      }),
    });

    const user = userEvent.setup();

    render(<MaintenanceBanner />);

    await waitFor(() => {
      expect(screen.getByText('Scheduled maintenance')).toBeInTheDocument();
    });

    await act(async () => {
      await user.click(screen.getByRole('button', { name: /dismiss maintenance notice/i }));
    });

    expect(sessionStorage.getItem('stl_dismissed_banner_v')).toBe('7');
    expect(screen.queryByText('Scheduled maintenance')).not.toBeInTheDocument();
  });
});