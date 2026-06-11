"""
AI Research Hub - Meta Agent
Runs on a schedule, picks a topic, uses Groq to research it,
and saves findings to Supabase.
"""

import os
import json
import logging
import schedule
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from groq import Groq
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Clients ──────────────────────────────────────────────────────────────────
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"],
)

def get_topics() -> list[dict]:
    res = supabase.table("topics").select("*").execute()
    return res.data or []

def get_due_topics(batch_size: int = 5) -> list[dict]:
    """Return the topics least recently researched (or never researched).

    Topics are sorted so that never-researched topics come first,
    followed by the oldest-researched, ensuring every topic gets
    equal attention over time in a strict rotation.
    """
    topics = get_topics()
    if not topics:
        return []

    # Get the most recent research entry timestamp per topic
    entries_resp = (
        supabase.table("research_entries")
        .select("topic_id, created_at")
        .order("created_at", desc=True)
        .execute()
    )

    # Build a map of topic_id -> most recent entry timestamp
    latest: dict = {}
    for entry in entries_resp.data or []:
        tid = entry["topic_id"]
        if tid not in latest:
            latest[tid] = entry["created_at"]

    # Sort: never-researched (empty string sorts first) then oldest timestamp first
    topics.sort(key=lambda t: latest.get(t["id"], ""))

    return topics[:batch_size]

def get_existing_titles(topic_id: str) -> list[str]:
    """Fetch all entry titles already stored for a given topic."""
    resp = (
        supabase.table("research_entries")
        .select("title")
        .eq("topic_id", topic_id)
        .execute()
    )
    return [row["title"] for row in resp.data or []]

def research_topic(
    topic_name: str,
    topic_description: str,
    existing_titles: list[str],
) -> list[dict]:
    """Ask Groq to produce structured research entries for a topic,
    explicitly avoiding titles that already exist in the database.
    """
    avoid_section = ""
    if existing_titles:
        formatted = "\n".join(f"  - {t}" for t in existing_titles)
        avoid_section = f"""
The following entries have ALREADY been researched and must NOT be repeated or closely rephrased:
{formatted}

Produce entries on entirely different aspects, creatures, myths, or stories not listed above.
"""

    prompt = f"""You are a research agent. Your job is to produce 3 fascinating, accurate research
entries about: "{topic_name}" ({topic_description}).
{avoid_section}
Return ONLY a JSON array with exactly 3 objects. Each object must have:
- "title": a concise headline (max 10 words)
- "content": a detailed paragraph (100-200 words) with interesting facts
- "tags": an array of 3-5 relevant keyword strings
- "source_url": a plausible Wikipedia or encyclopedia URL (can be approximate)

Return ONLY the JSON array, no other text."""

    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2048,
    )

    raw = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())

def run_agent_for_topic(topic: dict) -> None:
    topic_id = topic["id"]
    topic_name = topic["name"]
    log.info(f"Starting research run for topic: {topic_name}")

    # Log run start
    run_res = supabase.table("agent_runs").insert({
        "topic_id": topic_id,
        "status": "running",
    }).execute()
    run_id = run_res.data[0]["id"]

    try:
        # Fetch existing titles — used for both prompt-level and DB-level dedup
        existing_titles = get_existing_titles(topic_id)
        existing_normalized = {t.strip().lower() for t in existing_titles}
        log.info(
            f"Found {len(existing_titles)} existing entries for '{topic_name}' "
            f"— sending to AI to avoid repeats."
        )

        entries = research_topic(
            topic_name,
            topic.get("description") or "",
            existing_titles,
        )

        inserted = 0
        skipped = 0
        for entry in entries:
            title = entry.get("title", "Untitled")

            # DB-level dedup: skip if this title (case-insensitive) already exists
            if title.strip().lower() in existing_normalized:
                log.info(f"  Skipping duplicate: '{title}'")
                skipped += 1
                continue

            supabase.table("research_entries").insert({
                "topic_id": topic_id,
                "title": title,
                "content": entry.get("content", ""),
                "tags": entry.get("tags", []),
                "source_url": entry.get("source_url"),
            }).execute()

            inserted += 1
            # Track within this batch too, in case AI returns two near-identical titles
            existing_normalized.add(title.strip().lower())

        supabase.table("agent_runs").update({
            "status": "completed",
            "entries_added": inserted,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()

        log.info(
            f"Completed '{topic_name}': {inserted} new, {skipped} duplicate(s) skipped."
        )

    except Exception as e:
        log.error(f"Agent failed for '{topic_name}': {e}")
        supabase.table("agent_runs").update({
            "status": "failed",
            "error_msg": str(e),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()

def run_all_topics() -> None:
    topics = get_due_topics()
    if not topics:
        log.warning("No topics found in database.")
        return
    log.info(f"Processing {len(topics)} due topic(s) this run.")
    for topic in topics:
        run_agent_for_topic(topic)

def main() -> None:
    log.info("Meta-agent starting up...")
    run_all_topics()  # run once immediately on start

    # Schedule: run every 6 hours
    schedule.every(6).hours.do(run_all_topics)
