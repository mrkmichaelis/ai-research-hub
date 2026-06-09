import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'AI Research Hub',
  description: 'A living database of AI-researched knowledge, updated 24/7',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-950 text-gray-100">
        <header className="border-b border-gray-800 px-6 py-4 flex items-center gap-3">
          <span className="text-2xl">🔬</span>
          <div>
            <h1 className="text-xl font-bold tracking-tight">AI Research Hub</h1>
            <p className="text-xs text-gray-400">Autonomous AI agents, researching around the clock</p>
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-6 py-8">{children}</main>
        <footer className="border-t border-gray-800 text-center text-xs text-gray-500 py-4">
          Powered by Groq AI · Stored in Supabase · Deployed on Vercel
        </footer>
      </body>
    </html>
  );
}
