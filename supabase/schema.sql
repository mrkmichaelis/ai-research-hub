-- AI Research Hub - Supabase Schema
-- Run this in the Supabase SQL Editor

create extension if not exists "uuid-ossp";

-- Topics: subjects the AI researches
create table if not exists topics (
  id          uuid primary key default uuid_generate_v4(),
  name        text not null unique,
  description text,
  created_at  timestamptz default now()
);

-- Research entries created by agents
create table if not exists research_entries (
  id          uuid primary key default uuid_generate_v4(),
  topic_id    uuid references topics(id) on delete cascade,
  title       text not null,
  content     text not null,
  source_url  text,
  tags        text[] default '{}',
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

-- Agent runs: audit log of agent activity
create table if not exists agent_runs (
  id            uuid primary key default uuid_generate_v4(),
  topic_id      uuid references topics(id) on delete set null,
  status        text not null check (status in ('running','completed','failed')),
  entries_added integer default 0,
  error_msg     text,
  started_at    timestamptz default now(),
  finished_at   timestamptz
);

-- Indexes
create index if not exists idx_entries_topic   on research_entries(topic_id);
create index if not exists idx_entries_created on research_entries(created_at desc);
create index if not exists idx_runs_topic      on agent_runs(topic_id);

-- Row Level Security (public read, service-role write)
alter table topics           enable row level security;
alter table research_entries enable row level security;
alter table agent_runs       enable row level security;

create policy "Public read topics"   on topics           for select using (true);
create policy "Public read entries"  on research_entries for select using (true);
create policy "Public read runs"     on agent_runs       for select using (true);
create policy "Service write topics"   on topics           for all using (auth.role() = 'service_role');
create policy "Service write entries"  on research_entries for all using (auth.role() = 'service_role');
create policy "Service write runs"     on agent_runs       for all using (auth.role() = 'service_role');

-- Seed: starter topics
insert into topics (name, description) values
  ('Mythology Monsters',    'Creatures and monsters from world mythologies'),
  ('Ancient Civilizations', 'Facts and discoveries about ancient human civilizations'),
  ('Space Anomalies',       'Unusual phenomena and discoveries in space')
on conflict (name) do nothing;
