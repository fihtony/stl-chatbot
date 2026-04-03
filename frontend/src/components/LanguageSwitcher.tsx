"use client";

import { useState, useRef, useEffect } from "react";
import { useLanguage, languageFlags, languageLabels, Language } from "./LanguageContext";

export default function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const languages: Language[] = ["en", "fr", "zh"];

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-white/30 bg-white/10 text-white text-sm font-medium hover:bg-white/20 transition-all shadow-sm"
        aria-label={`Current language: ${languageLabels[language]}. Click to change.`}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span aria-hidden="true">{languageFlags[language]}</span>
        <span>{languageLabels[language]}</span>
        <span className="text-xs opacity-70" aria-hidden="true">▾</span>
      </button>

      {open && (
        <ul
          role="listbox"
          aria-label="Select language"
          className="absolute right-0 mt-1 w-36 bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden z-50"
        >
          {languages.map((lang) => (
            <li key={lang} role="option" aria-selected={language === lang}>
              <button
                onClick={() => { setLanguage(lang); setOpen(false); }}
                className={`w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors ${
                  language === lang
                    ? "bg-blue-50 text-blue-700 font-semibold"
                    : "text-gray-700 hover:bg-gray-50"
                }`}
              >
                <span aria-hidden="true">{languageFlags[lang]}</span>
                <span>{languageLabels[lang]}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
