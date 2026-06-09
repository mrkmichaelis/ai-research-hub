export interface Topic {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface ResearchEntry {
  id: string;
  topic_id: string;
  title: string;
  content: string;
  source_url: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface AgentRun {
  id: string;
  topic_id: string | null;
  status: 'running' | 'completed' | 'failed';
  entries_added: number;
  error_msg: string | null;
  started_at: string;
  finished_at: string | null;
}
