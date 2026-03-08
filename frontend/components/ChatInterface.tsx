'use client';

import { useState, useRef, useEffect } from 'react';
import MessageBubble from './MessageBubble';

interface Message {
  id: string;
  text: string;
  isUser: boolean;
  timestamp: Date;
}

interface IndexingProgress {
  is_indexing: boolean;
  progress: number;
  current_file: string;
  total_files: number;
  processed_files: number;
  status: string;
  error_message: string;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      text: 'Bonjour! Je suis l\'assistant IA du Collège Saint-Louis. Comment puis-je vous aider aujourd\'hui?',
      isUser: false,
      timestamp: new Date(),
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isPreloading, setIsPreloading] = useState(true);
  const [indexingProgress, setIndexingProgress] = useState<IndexingProgress | null>(null);
  const [aiProvider, setAiProvider] = useState<'zhipu'>('zhipu');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Poll indexing progress
  useEffect(() => {
    let mounted = true;
    let pollingInterval: NodeJS.Timeout | null = null;

    const checkIndexingProgress = async () => {
      try {
        const response = await fetch('/api/admin/index-progress');
        if (response.ok) {
          const data = await response.json();
          if (data.success && data.data && mounted) {
            setIndexingProgress(data.data);

            // Stop polling if indexing is complete or not happening
            if (!data.data.is_indexing && data.data.status !== 'initializing') {
              if (pollingInterval) {
                clearInterval(pollingInterval);
                pollingInterval = null;
              }
              // Hide preloading after indexing is done
              setTimeout(() => setIsPreloading(false), 500);
            }
          }
        }
      } catch (error) {
        console.warn('Failed to check indexing progress:', error);
        // Don't treat as critical - system can work without indexing
      }
    };

    // Initial check
    checkIndexingProgress();

    // Poll every 2 seconds if indexing is in progress
    pollingInterval = setInterval(checkIndexingProgress, 2000);

    return () => {
      mounted = false;
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, []);

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      text: inputValue.trim(),
      isUser: true,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: userMessage.text, provider: aiProvider }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: data.response,
        isUser: false,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (error) {
      // Detect language from user message
      const isEnglish = /^(hi|hello|who|what|where|when|why|how|can|will|would|should|could|the|is|are|do|does|did)/i.test(userMessage.text);
      const errorText = isEnglish
        ? 'Sorry, an error occurred. Please try again.'
        : 'Désolé, une erreur s\'est produite. Veuillez réessayer.';

      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: errorText,
        isUser: false,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
      // Keep focus on input field for continuous typing
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    // Auto-resize textarea
    if (inputRef.current) {
      inputRef.current.style.height = '48px';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`;
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">
              Collège Saint-Louis
            </h1>
            <p className="text-sm text-gray-600 mt-1">
              Assistant IA - Une fenêtre ouverte sur le monde
            </p>
          </div>
          {/* AI Provider Selector */}
          {/* <div className="flex items-center gap-2"> 
            <label className="text-xs text-gray-500">AI:</label>
            <select
              value={aiProvider}
              onChange={(e) => setAiProvider(e.target.value as 'zhipu')}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="zhipu">Zhipu AI (GLM-4.7)</option>
            </select>
          </div>*/}
        </div>
      </header>

      {/* Messages Container */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-4xl mx-auto space-y-4">
          {isPreloading && (
            <div className="flex justify-center items-center py-8">
              <div className="bg-white rounded-2xl px-6 py-4 shadow-sm w-full max-w-md">
                <div className="flex flex-col items-center space-y-3">
                  <div className="flex space-x-2">
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                  </div>
                  {indexingProgress && indexingProgress.is_indexing ? (
                    <>
                      <span className="text-sm text-gray-600">
                        Indexation des documents en cours...
                      </span>
                      {indexingProgress.total_files > 0 && (
                        <div className="w-full">
                          <div className="flex justify-between text-xs text-gray-500 mb-1">
                            <span>{indexingProgress.processed_files} / {indexingProgress.total_files} fichiers</span>
                            <span>{indexingProgress.progress}%</span>
                          </div>
                          <div className="w-full bg-gray-200 rounded-full h-2">
                            <div
                              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                              style={{ width: `${indexingProgress.progress}%` }}
                            ></div>
                          </div>
                          {indexingProgress.current_file && (
                            <span className="text-xs text-gray-400 truncate w-full text-center">
                              {indexingProgress.current_file}
                            </span>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <span className="text-sm text-gray-600">Chargement des documents...</span>
                  )}
                </div>
              </div>
            </div>
          )}
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white rounded-2xl px-6 py-4 shadow-sm max-w-md">
                <div className="flex space-x-2">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="bg-white border-t border-gray-200 px-4 py-4">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-end space-x-3">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={handleInputChange}
                onKeyPress={handleKeyPress}
                placeholder="Tapez votre message..."
                className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none overflow-y-auto text-gray-900"
                rows={1}
                style={{
                  minHeight: '48px',
                  maxHeight: '120px',
                  color: '#111827', // Force black text color
                }}
                disabled={isLoading || isPreloading}
              />
            </div>
            <button
              onClick={handleSend}
              disabled={!inputValue.trim() || isLoading || isPreloading}
              className="px-6 py-3 bg-blue-600 text-white rounded-2xl font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Envoyer
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

