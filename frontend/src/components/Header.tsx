"use client";

import LanguageSwitcher from "./LanguageSwitcher";
import { useLanguage } from "./LanguageContext";

export default function Header() {
  const { t } = useLanguage();

  return (
    <header className="bg-gradient-to-r from-yellow-500 to-yellow-600 text-white shadow-lg">
      <div className="max-w-6xl mx-auto px-4 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {/* Saint-Louis Logo */}
            <div className="flex items-center justify-center w-12 h-12 bg-white rounded-full shadow-md">
              <span className="text-3xl font-bold text-yellow-600">S</span>
            </div>

            <div>
              <h1 className="text-2xl font-bold">{t.headerTitle}</h1>
              <p className="text-yellow-100 text-sm mt-0.5">
                {t.headerSubtitle}
              </p>
            </div>
          </div>

          {/* Language Switcher - top right */}
          <LanguageSwitcher />
        </div>
      </div>
    </header>
  );
}
