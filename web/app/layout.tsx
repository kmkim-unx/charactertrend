import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CharacterTrend — AI 캐릭터 랭킹",
  description: "Zeta AI, Crack AI, Rofan AI 인기 캐릭터 일일 트렌드 분석",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-bg text-gray-200">
        <header className="border-b border-border px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center text-white font-bold text-sm">
              CT
            </div>
            <h1 className="text-lg font-semibold text-white">CharacterTrend</h1>
            <span className="text-muted text-sm ml-1">by UNX</span>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 py-8">{children}</main>
        <footer className="border-t border-border mt-16 px-6 py-6 text-center text-muted text-sm">
          <p>CharacterTrend · Powered by UNX · 매일 KST 자정 업데이트</p>
        </footer>
      </body>
    </html>
  );
}
