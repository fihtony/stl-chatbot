"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import MessageBubble from "./MessageBubble";
import SuggestedQuestions from "./SuggestedQuestions";
import InputArea from "./InputArea";
import LoadingIndicator from "./LoadingIndicator";
import { useLanguage } from "./LanguageContext";

interface Citation {
  id: number;
  source: string;
  original_ids: number[];
  excerpt?: string;
  content?: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  citations?: Citation[];
  suggestions?: string[];
  sessionId?: string;
}

// Generate a unique session ID per chat instance
function generateSessionId(): string {
  return `s_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
}

export default function ChatContainer() {
  const { language, t } = useLanguage();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sessionId = useMemo(() => generateSessionId(), []);

  // Reset welcome message when language changes
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          content: t.welcomeMessage,
          timestamp: new Date().toISOString(),
          sessionId,
        },
      ]);
    }
  }, [language]);

  // Initialize with welcome message
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          content: t.welcomeMessage,
          timestamp: new Date().toISOString(),
          sessionId,
        },
      ]);
    }
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSend = async (message: string) => {
    const now = new Date().toISOString();
    const msgId = `msg_${Date.now()}`;
    setMessages((prev) => [...prev, { id: msgId, role: "user", content: message, timestamp: now, sessionId }]);
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId }),
      });

      if (!response.ok) throw new Error("Failed to get response");

      const data = await response.json();

      const responseText = data.answer || data.response || t.errorMessage;
      const citations = data.citations || [];
      const suggestions = data.suggestions || [];

      setMessages((prev) => [
        ...prev,
        {
          id: `resp_${Date.now()}`,
          role: "assistant",
          content: responseText,
          timestamp: new Date().toISOString(),
          citations,
          suggestions,
          sessionId,
        },
      ]);
    } catch (error) {
      console.error("Chat API error:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: `err_${Date.now()}`,
          role: "assistant",
          content: t.errorMessage,
          timestamp: new Date().toISOString(),
          sessionId,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-gradient-to-br from-yellow-50 to-orange-50 overflow-hidden">
      {/* Messages Container - scrollable area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-6xl mx-auto space-y-4">
          {messages.map((msg, index) => (
            <MessageBubble
              key={index}
              role={msg.role}
              content={msg.content}
              citations={msg.citations}
              sessionId={msg.sessionId}
            />
          ))}
          {/* Show suggestions from the last assistant message */}
          {messages.length > 0 &&
            messages[messages.length - 1].role === "assistant" &&
            messages[messages.length - 1].suggestions &&
            messages[messages.length - 1].suggestions!.length > 0 &&
            !isLoading && (
              <SuggestedQuestions
                questions={messages[messages.length - 1].suggestions!}
                onSelect={handleSend}
              />
            )}
          {isLoading && <LoadingIndicator />}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area - fixed at bottom */}
      <InputArea onSend={handleSend} disabled={isLoading} />
    </div>
  );
}
