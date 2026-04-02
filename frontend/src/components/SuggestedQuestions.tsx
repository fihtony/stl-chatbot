"use client";

import { useLanguage } from "./LanguageContext";

interface SuggestedQuestionsProps {
  questions: string[];
  onSelect: (question: string) => void;
}

export default function SuggestedQuestions({ questions, onSelect }: SuggestedQuestionsProps) {
  const { t: labels } = useLanguage();

  if (!questions || questions.length === 0) return null;

  return (
    <div className="ml-2 mt-2 max-w-2xl">
      <p className="text-xs text-gray-400 font-medium mb-1.5 italic">{labels.relatedQuestions}</p>
      <div className="flex flex-col gap-1.5">
        {questions.map((question, index) => (
          <button
            key={index}
            onClick={() => onSelect(question)}
            className="w-fit text-left px-3 py-1.5 rounded-lg
                     text-xs italic text-gray-600
                     border border-gray-200 bg-white
                     hover:text-yellow-700 hover:border-yellow-400 hover:bg-yellow-50
                     transition-all duration-150 cursor-pointer
                     shadow-sm hover:shadow"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
