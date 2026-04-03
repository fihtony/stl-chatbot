import React from 'react';
import { render, screen } from '@testing-library/react';
import MessageBubble from '@/components/MessageBubble';

jest.mock('@/components/LanguageContext', () => ({
  useLanguage: () => ({
    t: {
      userName: 'You',
      assistantLabel: 'Saint-Louis Assistant',
    },
  }),
}));

describe('MessageBubble', () => {
  it('renders a user bubble with the user label', () => {
    render(<MessageBubble role="user" content="Test message" />);

    expect(screen.getByText('You')).toBeInTheDocument();
    expect(screen.getByText('👤')).toBeInTheDocument();
    expect(screen.getByText('Test message').closest('.bg-blue-600')).toBeInTheDocument();
  });

  it('renders an assistant bubble with the assistant label', () => {
    render(<MessageBubble role="assistant" content="Assistant reply" />);

    expect(screen.getByText('Saint-Louis Assistant')).toBeInTheDocument();
    expect(screen.getByText('🤖')).toBeInTheDocument();
    expect(screen.getByText('Assistant reply').closest('.bg-white')).toBeInTheDocument();
  });

  it('removes standalone separator lines before rendering', () => {
    render(<MessageBubble role="assistant" content={'===\nVisible content'} />);

    expect(screen.getByText('Visible content')).toBeInTheDocument();
    expect(screen.queryByText('===')).not.toBeInTheDocument();
  });
});