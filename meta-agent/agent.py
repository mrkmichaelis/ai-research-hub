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


def research_topic(topic_name: str, topic_description: str) -> list[dict]:
    """Ask Groq to produce structured research entries for a topic."""
    prompt = f"""You are a research agent. Your job is to produce 3 fascinating, accurate research 
entries about: "{topic_name}" ({topic_description}).

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
        entries = research_topic(topic_name, topic.get("description") or "")
        inserted = 0
        for entry in entries:
            supabase.table("research_entries").insert({
                "topic_id": topic_id,
                "title":      entry.get("title", "Untitled"),
                "content":    entry.get("content", ""),
                "tags":       entry.get("tags", []),
                "source_url": entry.get("source_url"),
            }).execute()
            inserted += 1

        supabase.table("agent_runs").update({
            "status":        "completed",
            "entries_added": inserted,
            "finished_at":   datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()

        log.info(f"Completed: added {inserted} entries for '{topic_name}'")

    except Exception as e:
        log.error(f"Agent failed for '{topic_name}': {e}")
        supabase.table("agent_runs").update({
            "status":      "failed",
            "error_msg":   str(e),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()


def run_all_topics() -> None:
    topics = get_topics()
    if not topics:
        log.warning("No topics found in database.")
        return
    for topic in topics:
        run_agent_for_topic(topic)


def main() -> None:
    log.info("Meta-agent starting up...")
    run_all_topics()  # run once immediately on start

    # Schedule: run every 6 hours
    schedule.every(6).hours.do(run_all_topics)
    log.info("Scheduled to run every 6 hours. Waiting...")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    m