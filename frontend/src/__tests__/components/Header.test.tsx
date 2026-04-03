import React from 'react';
import { render, screen } from '@testing-library/react';
import Header from '@/components/Header';

const mockUseAdmin = jest.fn();

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

jest.mock('@/components/LanguageContext', () => ({
  useLanguage: () => ({
    language: 'en',
    setLanguage: jest.fn(),
    t: {
      headerTitle: 'Collège Saint-Louis Chatbot',
      headerSubtitle: 'Your guide to school information and services',
    },
  }),
  languageFlags: { en: '🇬🇧', fr: '🇫🇷', zh: '🇨🇳' },
  languageLabels: { en: 'English', fr: 'Français', zh: '中文' },
}));

jest.mock('@/components/AdminContext', () => ({
  useAdmin: () => mockUseAdmin(),
}));

jest.mock('@/components/AdminLoginDialog', () => () => null);

describe('Header', () => {
  beforeEach(() => {
    mockUseAdmin.mockReset();
  });

  it('shows language and admin login controls for logged-out users', () => {
    mockUseAdmin.mockReturnValue({
      isAdmin: false,
      adminEmail: null,
      openLoginDialog: jest.fn(),
      logout: jest.fn(),
    });

    render(<Header />);

    expect(screen.getByRole('button', { name: /current language: english/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /administrator login/i })).toBeInTheDocument();
  });

  it('shows admin panel and logout controls for logged-in admins', () => {
    mockUseAdmin.mockReturnValue({
      isAdmin: true,
      adminEmail: 'redacted@example.com',
      openLoginDialog: jest.fn(),
      logout: jest.fn(),
    });

    render(<Header />);

    expect(screen.getByRole('link', { name: /admin/i })).toHaveAttribute('href', '/admin');
    expect(screen.getByRole('button', { name: /logout from admin/i })).toBeInTheDocument();
  });
});