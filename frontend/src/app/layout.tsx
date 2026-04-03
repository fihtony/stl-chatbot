import type { Metadata } from "next";
import "../styles/globals.css";
import { LanguageProvider } from "@/components/LanguageContext";
import { AdminProvider } from "@/components/AdminContext";

export const metadata: Metadata = {
  title: "Collège Saint-Louis Chatbot",
  description: "Your guide to school information and services",
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
        <LanguageProvider>
          <AdminProvider>
            {children}
          </AdminProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
