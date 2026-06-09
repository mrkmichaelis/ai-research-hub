import { supabase } from '../../../lib/supabase';
import type { Topic, ResearchEntry } from '../../../lib/types';
import Link from 'next/link';
import { notFound } from 'next/navigation';

export const revalidate = 60;

export default async function TopicPage({ params }: { params: { id: string } }) {
  const [topicRes, entriesRes] = await Promise.all([
    supabase.from('topics').select('*').eq('id', params.id).single(),
    supabase.from('research_entries').select('*')
      .eq('topic_id', params.id)
      .order('created_at', { ascending: false }),
  ]);

  if (!topicRes.data) return notFound();
  const topic = topicRes.data as Topic;
  const entries = (entriesRes.data ?? []) as ResearchEntry[];

  return (
    <div className="space-y-8">
      <div>
        <Link href="/" className="text-sm text-indigo-400 hover:underline">← All topics</Link>
        <h2 className="text-3xl font-bold mt-2">{topic.name}</h2>
        {topic.description && <p className="text-gray-400 mt-1">{topic.description}</p>}
        <p className="text-sm text-gray-500 mt-2">{entries.length} entries</p>
      </div>

      {entries.length === 0 ? (
        <p className="text-gray-500">No entries yet for this topic.</p>
      ) : (
        <div className="space-y-4">
          {entries.map(e => (
            <article key={e.id}
              className="rounded-xl border border-gray-800 bg-gray-900 p-6 space-y-2">
              <h3 className="text-lg font-semibold text-indigo-300">{e.title}</h3>
              <p className="text-gray-300 leading-relaxed">{e.content}</p>
              {e.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
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
                  className="text-xs text-gray-500 hover:text-indigo-400 break-all block pt-1">
                  Source: {e.source_url}
                </a>
              )}
              <p className="text-xs text-gray-600 pt-1">
                Added {new Date(e.created_at).toLocaleString()}
              </p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
