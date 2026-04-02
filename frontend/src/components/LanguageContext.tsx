"use client";

import { createContext, useContext, useState, ReactNode, useCallback } from "react";

export type Language = "en" | "fr" | "zh";

interface Translations {
  headerTitle: string;
  headerSubtitle: string;
  assistantName: string;
  userName: string;
  inputPlaceholder: string;
  sendButton: string;
  sendButtonAria: string;
  relatedQuestions: string;
  welcomeMessage: string;
  errorMessage: string;
  assistantLabel: string;
  userLabel: string;
}

const translations: Record<Language, Translations> = {
  en: {
    headerTitle: "Saint-Louis Chatbot",
    headerSubtitle: "Your guide to insurance, wealth, and health solutions",
    assistantName: "Saint-Louis Assistant",
    userName: "You",
    inputPlaceholder: "Ask your question...",
    sendButton: "Send",
    sendButtonAria: "Send message",
    relatedQuestions: "Related questions",
    welcomeMessage: "Hello! I'm your Saint-Louis assistant. How can I help you with insurance, investments, or health solutions today?",
    errorMessage: "Sorry, an error occurred. Please try again.",
    assistantLabel: "Saint-Louis Assistant",
    userLabel: "You",
  },
  fr: {
    headerTitle: "Saint-Louis Chatbot",
    headerSubtitle: "Votre guide en assurance, richesse et solutions de santé",
    assistantName: "Assistant Saint-Louis",
    userName: "Vous",
    inputPlaceholder: "Posez votre question...",
    sendButton: "Envoyer",
    sendButtonAria: "Envoyer le message",
    relatedQuestions: "Questions connexes",
    welcomeMessage: "Bonjour ! Je suis votre assistant Saint-Louis. Comment puis-je vous aider avec l'assurance, les investissements ou les solutions de santé aujourd'hui ?",
    errorMessage: "Désolé, une erreur s'est produite. Veuillez réessayer.",
    assistantLabel: "Assistant Saint-Louis",
    userLabel: "Vous",
  },
  zh: {
    headerTitle: "Saint-Louis 智能助手",
    headerSubtitle: "您的保险、财富和健康解决方案指南",
    assistantName: "Saint-Louis 助手",
    userName: "我",
    inputPlaceholder: "请输入您的问题...",
    sendButton: "发送",
    sendButtonAria: "发送消息",
    relatedQuestions: "相关问题",
    welcomeMessage: "您好！我是您的 Saint-Louis 助手。今天我能在保险、投资或健康方案方面为您提供什么帮助？",
    errorMessage: "抱歉，发生了错误。请重试。",
    assistantLabel: "Saint-Louis 助手",
    userLabel: "我",
  },
};

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: Translations;
}

const LanguageContext = createContext<LanguageContextType>({
  language: "en",
  setLanguage: () => {},
  t: translations.en,
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>("en");

  const value = {
    language,
    setLanguage,
    t: translations[language],
  };

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}

export const languageLabels: Record<Language, string> = {
  en: "EN",
  fr: "FR",
  zh: "中文",
};
