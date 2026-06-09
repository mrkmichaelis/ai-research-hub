import { supabase } from '../lib/supabase';
import type { Topic, ResearchEntry } from '../lib/types';
import Link from 'next/link';

export const revalidate = 60; // ISR: refresh every 60s

async function getData() {
  const [topicsRes, entriesRes] = await Promise.all([
    supabase.from('topics').select('*').order('name'),
    supabase.from('research_entries').select('*').order('created_at', { ascending: false }).limit(12),
  ]);
  return {
    topics: (topicsRes.data ?? []) as Topic[],
    entries: (entriesRes.data ?? []) as ResearchEntry[],
  };
}

export default async function HomePage() {
  const { topics, entries } = await getData();

  return (
    <div className="space-y-10">
      {/* Hero */}
      <div className="text-center py-8">
        <h2 className="text-4xl font-extrabold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent mb-3">
          Knowledge, Researched by AI
        </h2>
        <p className="text-gray-400 max-w-xl mx-auto">
          AI agents explore the internet 24/7, finding and cataloguing fascinating facts
          across mythology, history, science, and more.
        </p>
      </div>

      {/* Topics */}
      <section>
        <h3 className="text-lg font-semibold mb-4 text-gray-300">Research Topics</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {topics.map(t => (
            <Link key={t.id} href={`/topics/${t.id}`}
              className="rounded-xl border border-gray-800 bg-gray-900 p-5 hover:border-indigo-500 transition">
              <p className="font-semibold">{t.name}</p>
              {t.description && <p className="text-sm text-gray-400 mt-1">{t.description}</p>}
            </Link>
          ))}
        </div>
      </section>

      {/* Latest entries */}
      <section>
        <h3 className="text-lg font-semibold mb-4 text-gray-300">Latest Discoveries</h3>
        {entries.length === 0 ? (
          <p className="text-gray-500 text-sm">No entries yet — agents are warming up!</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {entries.map(e => (
              <article key={e.id}
                className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-2">
                <h4 className="font-semibold text-indigo-300">{e.title}</h4>
                <p className="text-sm text-gray-400 line-clamp-3">{e.content}</p>
                {e.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {e.tags.map(tag => (
                      <span key={tag}
                        className="text-xs bg-indigo-900/50 text-indigo-300 px-2 py-0.5 rounded-full">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                {e.source_url && (
                  <a href={e.source_url} target="_blank" rel="noopener noreferrer"
                    className="text-xs text-gray-500 hover:text-indigo-400 truncate block">
                    {e.source_url}
                  </a>
                )}
                <p className="text-xs text-gray-600">
                  {new Date(e.created_at).toLocaleDateString()}
                </p>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
