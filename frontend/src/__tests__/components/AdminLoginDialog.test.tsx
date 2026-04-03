/**
 * AdminLoginDialog tests — AUTH-01, AUTH-02
 *
 * AUTH-01: Clicking the admin icon opens a confirmation dialog with
 *          "I am an administrator" and "No, cancel" buttons.
 * AUTH-02: Clicking "No, cancel" closes the dialog without making any request.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import AdminLoginDialog from '@/components/AdminLoginDialog';

const mockCloseLoginDialog = jest.fn();
const mockShowLoginDialog = jest.fn();

jest.mock('@/components/AdminContext', () => ({
  useAdmin: () => ({
    showLoginDialog: mockShowLoginDialog(),
    closeLoginDialog: mockCloseLoginDialog,
  }),
}));

// Silence console.error from missing act() warnings that don't affect correctness
beforeAll(() => {
  jest.spyOn(console, 'error').mockImplementation(() => {});
});
afterAll(() => {
  (console.error as jest.Mock).mockRestore();
});

beforeEach(() => {
  jest.clearAllMocks();
});

describe('AdminLoginDialog', () => {
  it('AUTH-01: renders the confirmation dialog when showLoginDialog is true', () => {
    mockShowLoginDialog.mockReturnValue(true);
    render(<AdminLoginDialog />);

    // Dialog heading must mention admin login
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/admin login/i)).toBeInTheDocument();

    // Must have both action buttons
    expect(screen.getByRole('button', { name: /i am an administrator/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /no, cancel/i })).toBeInTheDocument();
  });

  it('AUTH-01: renders nothing when showLoginDialog is false', () => {
    mockShowLoginDialog.mockReturnValue(false);
    const { container } = render(<AdminLoginDialog />);
    expect(container.firstChild).toBeNull();
  });

  it('AUTH-02: clicking "No, cancel" calls closeLoginDialog without making any requests', () => {
    mockShowLoginDialog.mockReturnValue(true);
    // Verify no fetch is triggered by mocking it in the module environment
    const originalFetch = global.fetch;
    const mockFetch = jest.fn();
    Object.defineProperty(global, 'fetch', { value: mockFetch, writable: true });

    render(<AdminLoginDialog />);
    fireEvent.click(screen.getByRole('button', { name: /no, cancel/i }));

    expect(mockCloseLoginDialog).toHaveBeenCalledTimes(1);
    expect(mockFetch).not.toHaveBeenCalled();

    Object.defineProperty(global, 'fetch', { value: originalFetch, writable: true });
  });

  it('AUTH-01: dialog has correct accessibility attributes', () => {
    mockShowLoginDialog.mockReturnValue(true);
    render(<AdminLoginDialog />);

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    // The dialog title must be labelled
    const titleId = dialog.getAttribute('aria-labelledby');
    expect(titleId).toBeTruthy();
    expect(document.getElementById(titleId!)).toBeInTheDocument();
  });
});
