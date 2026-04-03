"use client";

import { createContext, useContext, useState, ReactNode, useCallback, useEffect } from "react";

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
    headerTitle: "Collège Saint-Louis Chatbot",
    headerSubtitle: "Your guide to school information and services",
    assistantName: "Saint-Louis Assistant",
    userName: "You",
    inputPlaceholder: "Ask your question...",
    sendButton: "Send",
    sendButtonAria: "Send message",
    relatedQuestions: "Related questions",
    welcomeMessage: "Hello! I'm your Collège Saint-Louis assistant. How can I help you today?",
    errorMessage: "Sorry, an error occurred. Please try again.",
    assistantLabel: "Saint-Louis Assistant",
    userLabel: "You",
  },
  fr: {
    headerTitle: "Chatbot Collège Saint-Louis",
    headerSubtitle: "Votre guide pour les informations et services scolaires",
    assistantName: "Assistant Saint-Louis",
    userName: "Vous",
    inputPlaceholder: "Posez votre question...",
    sendButton: "Envoyer",
    sendButtonAria: "Envoyer le message",
    relatedQuestions: "Questions connexes",
    welcomeMessage: "Bonjour ! Je suis votre assistant du Collège Saint-Louis. Comment puis-je vous aider aujourd'hui ?",
    errorMessage: "Désolé, une erreur s'est produite. Veuillez réessayer.",
    assistantLabel: "Assistant Saint-Louis",
    userLabel: "Vous",
  },
  zh: {
    headerTitle: "圣路易斯学院智能助手",
    headerSubtitle: "您的学校信息与服务指南",
    assistantName: "圣路易斯助手",
    userName: "我",
    inputPlaceholder: "请输入您的问题...",
    sendButton: "发送",
    sendButtonAria: "发送消息",
    relatedQuestions: "相关问题",
    welcomeMessage: "您好！我是圣路易斯学院助手。今天我能为您提供什么帮助？",
    errorMessage: "抱歉，发生了错误。请重试。",
    assistantLabel: "圣路易斯助手",
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
  const [language, setLanguageState] = useState<Language>("en");

  // Fetch default language from public config on first load
  useEffect(() => {
    const sessionLang = sessionStorage.getItem("stl_language") as Language | null;
    if (sessionLang && ["en", "fr", "zh"].includes(sessionLang)) {
      setLanguageState(sessionLang);
      return;
    }
    // Fallback: fetch from backend public config
    fetch("/api/public-state")
      .then((r) => r.json())
      .then((data: { default_language?: string }) => {
        const lang = data.default_language as Language;
        if (lang && ["en", "fr", "zh"].includes(lang)) {
          setLanguageState(lang);
        }
      })
      .catch(() => {/* keep "en" default */});
  }, []);

  const setLanguage = useCallback((lang: Language) => {
    setLanguageState(lang);
    // Persist for this session only
    try { sessionStorage.setItem("stl_language", lang); } catch (_) {}
  }, []);

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

export const languageFlags: Record<Language, string> = {
  en: "🇬🇧",
  fr: "🇫🇷",
  zh: "🇨🇳",
};

export const languageLabels: Record<Language, string> = {
  en: "English",
  fr: "Français",
  zh: "中文",
};
