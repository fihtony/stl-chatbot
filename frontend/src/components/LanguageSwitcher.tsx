"use client";

import { useLanguage, languageLabels, Language } from "./LanguageContext";

export default function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage();

  const languages: Language[] = ["en", "fr", "zh"];

  return (
    <div className="flex items-center gap-1 bg-white/20 rounded-lg p-0.5">
      {languages.map((lang) => (
        <button
          key={lang}
          onClick={() => setLanguage(lang)}
          className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
            language === lang
              ? "bg-white text-yellow-700 shadow-sm"
              : "text-white/80 hover:text-white hover:bg-white/10"
          }`}
          aria-label={`Switch to ${languageLabels[lang]}`}
        >
          {languageLabels[lang]}
        </button>
      ))}
    </div>
  );
}
