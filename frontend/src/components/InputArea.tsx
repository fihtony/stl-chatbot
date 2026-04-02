"use client";

import { useState, FormEvent, useRef, useEffect } from "react";
import { useLanguage } from "./LanguageContext";

interface InputAreaProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export default function InputArea({ onSend, disabled }: InputAreaProps) {
  const [message, setMessage] = useState("");
  const { t } = useLanguage();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "48px";
      const scrollHeight = textareaRef.current.scrollHeight;
      const newHeight = Math.min(scrollHeight, 120);
      textareaRef.current.style.height = `${newHeight}px`;
      textareaRef.current.style.overflowY = scrollHeight > 120 ? "auto" : "hidden";
    }
  }, [message]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (message.trim() && !disabled) {
      onSend(message.trim());
      setMessage("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "48px";
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as any);
    }
  };

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-4">
      <form onSubmit={handleSubmit} className="max-w-6xl mx-auto">
        <div className="flex items-center gap-3">
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t.inputPlaceholder}
              className="w-full px-4 py-3 border border-gray-300 rounded-2xl focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent resize-none overflow-y-auto text-gray-900 placeholder-gray-500 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent"
              rows={1}
              style={{
                minHeight: "48px",
                maxHeight: "120px",
                height: "48px",
                overflowY: "hidden",
              }}
              disabled={disabled}
              aria-label={t.inputPlaceholder}
            />
          </div>
          <button
            type="submit"
            disabled={disabled || !message.trim()}
            className="h-12 px-5 bg-yellow-500 text-white rounded-2xl font-medium hover:bg-yellow-600 focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 shrink-0"
            aria-label={t.sendButtonAria}
          >
            <span>➤</span>
            <span>{t.sendButton}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
