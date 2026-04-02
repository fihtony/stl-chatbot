import type { Metadata } from "next";
import "../styles/globals.css";
import { LanguageProvider } from "@/components/LanguageContext";

export const metadata: Metadata = {
  title: "Saint-Louis Chatbot",
  description: "Your guide to insurance, wealth, and health solutions",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <html lang="en">
      <body>
        <LanguageProvider>{children}</LanguageProvider>
      </body>
    </html>
  );
}
