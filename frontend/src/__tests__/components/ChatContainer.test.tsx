import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatContainer from '@/components/ChatContainer';

jest.mock('@/components/LanguageContext', () => ({
  useLanguage: () => ({
    language: 'en',
    t: {
      headerTitle: 'Collège Saint-Louis Chatbot',
      headerSubtitle: 'Your guide to school information and services',
      assistantName: 'Saint-Louis Assistant',
      userName: 'You',
      inputPlaceholder: 'Ask your question...',
      sendButton: 'Send',
      sendButtonAria: 'Send message',
      relatedQuestions: 'Related questions',
      welcomeMessage: "Hello! I'm your Collège Saint-Louis assistant. How can I help you today?",
      errorMessage: 'Sorry, an error occurred. Please try again.',
      assistantLabel: 'Saint-Louis Assistant',
      userLabel: 'You',
    },
  }),
}));

global.fetch = jest.fn();

let consoleErrorSpy: jest.SpyInstance;

describe('ChatContainer', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('renders the welcome message and input controls', () => {
    render(<ChatContainer />);

    expect(screen.getByText(/Collège Saint-Louis assistant/i)).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toHaveAttribute('data-chat-input', 'true');
    expect(screen.getByRole('button', { name: /send message/i })).toBeInTheDocument();
  });

  it('sends chat requests with a generated session id', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ answer: 'Hello back', citations: [], suggestions: [] }),
    });
    const user = userEvent.setup();

    render(<ChatContainer />);

    await act(async () => {
      await user.type(screen.getByRole('textbox'), 'Test message');
      await user.click(screen.getByRole('button', { name: /send message/i }));
    });

    await waitFor(() => expect(screen.getByText('Hello back')).toBeInTheDocument());

    expect(global.fetch).toHaveBeenCalledWith('/api/chat', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }));

    const [, requestInit] = (global.fetch as jest.Mock).mock.calls[0];
    const payload = JSON.parse(requestInit.body as string);
    expect(payload).toMatchObject({ message: 'Test message' });
    expect(payload.session_id).toEqual(expect.any(String));
  });

  it('restores a saved draft from sessionStorage', () => {
    sessionStorage.setItem('stl_chat_draft', 'Saved draft');

    render(<ChatContainer />);

    expect(screen.getByRole('textbox')).toHaveValue('Saved draft');
  });

  it('shows the translated error message on request failure', async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));
    const user = userEvent.setup();

    render(<ChatContainer />);

    await act(async () => {
      await user.type(screen.getByRole('textbox'), 'Test');
      await user.click(screen.getByRole('button', { name: /send message/i }));
    });

    await waitFor(() => {
      expect(screen.getByText('Sorry, an error occurred. Please try again.')).toBeInTheDocument();
    });
  });

  it('blocks new messages when a config refresh is required', () => {
    render(<ChatContainer inputBlocked blockReason="Refresh first" />);

    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(screen.getByText('Refresh first')).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });
});