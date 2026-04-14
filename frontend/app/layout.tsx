import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Toaster } from "sonner";
import { RouteProgress } from "@/components/route-progress";

const inter = Inter({ subsets: ["latin", "cyrillic"] });

export const metadata: Metadata = {
  title: "YandexMagic",
  description: "AI-агент для Яндекс Директа",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className={inter.className}>
        <RouteProgress />
        {children}
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
}
