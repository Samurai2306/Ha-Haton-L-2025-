import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "UAV Analytics",
  description: "Аналитика полётов: метрики, карта, прогноз",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased neo-surface`}>
        <header className="sticky top-0 z-10 backdrop-blur bg-[rgba(14,19,26,0.6)]">
          <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
            <a href="/" className="text-lg font-semibold">UAV Analytics</a>
            <nav className="flex gap-4 text-sm">
              <a href="/overview" className="neo-link">Обзор</a>
              <a href="/trends" className="neo-link">Тренды</a>
              <a href="/map" className="neo-link">Карта</a>
              <a href="/about" className="neo-link">О системе</a>
            </nav>
          </div>
        </header>
        <main className="min-h-screen">{children}</main>
        <footer className="mt-10 py-6 text-center text-xs text-gray-600">
          © UAV Analytics
        </footer>
      </body>
    </html>
  );
}
