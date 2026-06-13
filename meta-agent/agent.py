"""
AI Research Hub - Meta Agent
Runs on a schedule, picks a topic, uses Groq to research it,
and saves findings to Supabase.

Anti-hallucination methods implemented:
  1. Prompt specificity enforcement - requires named entities, forbids vague generalities
  2. AI self-critique - second low-temp Groq call fact-checks the first response
  3. Content rules validation - Python checks: length, disclaimer phrases, topic relevance
  4. URL reachability - HTTP HEAD on source_url; dead links cleared before saving
  5. Weekly audit workflow - see meta-agent/audit.py + .github/workflows/audit.yml
"""

import os
import json
import logging
import re
import schedule
import time
import urllib.request
from datetime import datetime, timezone
from dotenv import load_dotenv
from groq import Groq
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# -- Clients ------------------------------------------------------------------
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"],
)


# -- Topic helpers ------------------------------------------------------------

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

    entries_resp = (
        supabase.table("research_entries")
        .select("topic_id, created_at")
        .order("created_at", desc=True)
        .execute()
    )

    latest: dict = {}
    for entry in entries_resp.data or []:
        tid = entry["topic_id"]
        if tid not in latest:
            latest[tid] = entry["created_at"]

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


# -- Anti-hallucination: Method 3 - Content rules ----------------------------

def validate_entry_rules(entry: dict, topic_name: str) -> tuple[bool, str]:
    """
    Pure-Python static checks that catch low-quality or clearly fabricated
    entries without any API calls.
    - Minimum word count (< 60 is suspiciously thin)
    - Patterns that indicate the AI is hedging, disclaiming, or confessing uncertainty
    - Topic keyword relevance (at least one significant word from the topic name
      must appear in the content)
    - Reject generic filler titles
    """
    title = entry.get("title", "")
    content = entry.get("content", "")
    word_count = len(content.split())

    if word_count < 60:
        return False, f"too short ({word_count} words)"

    bad_patterns = [
        r"I (don't|do not|cannot|can't) (know|confirm|verify|say)",
        r"\[citation needed\]",
        r"\[insert\b",
        r"\bNote:\s",
        r"\bDisclaimer:\s",
        r"\bAs an AI\b",
        r"I'm not (sure|certain|confident)",
        r"there (is|are) (no|little|limited) (known|documented|recorded)",
        r"little is known",
        r"records (do not|don't) survive",
    ]
    for pat in bad_patterns:
        if re.search(pat, content, re.IGNORECASE):
            return False, "hedging/disclaimer pattern detected"

    topic_words = [w for w in re.sub(r"[^a-z ]", "", topic_name.lower()).split() if len(w) > 4]
    if topic_words:
        content_lower = content.lower()
        if not any(w in content_lower for w in topic_words):
            return False, "content does not reference the topic"

    generic_titles = {
        "untitled", "research entry", "mythology entry",
        "topic overview", "introduction", "overview",
    }
    if title.strip().lower() in generic_titles:
        return False, "generic filler title"

    return True, "ok"


# -- Anti-hallucination: Method 4 - URL reachability -------------------------

def check_url_reachability(url: str, timeout: int = 6) -> str | None:
    """
    Attempts a HEAD request on the generated source URL.
    Returns the URL if reachable (HTTP < 400), or None if dead/hallucinated.
    Wikipedia hallucinations typically 404 -- a strong signal the entry may
    contain fabricated details. Dead URLs are cleared rather than causing
    an entry reject, since a bad URL doesn't mean the text is wrong.
    """
    if not url:
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (research-hub-validator/1.0)"},
            method="HEAD",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return url if resp.status < 400 else None
    except Exception:
        return None


# -- Anti-hallucination: Method 2 - AI self-critique -------------------------

def ai_self_critique(topic_name: str, entries: list[dict]) -> list[dict]:
    """
    Sends the generated entries back to Groq at near-zero temperature and
    asks it to identify UNCERTAIN or HALLUCINATED claims.
    Only entries rated ACCURATE are returned.
    """
    if not entries:
        return entries

    payload = json.dumps(
        [
            {
                "index": i,
                "title": e.get("title", ""),
                "content": e.get("content", "")[:400],
            }
            for i, e in enumerate(entries)
        ],
        indent=2,
    )

    prompt = f"""You are a rigorous fact-checker reviewing AI-generated entries about "{topic_name}".

Evaluate each entry: are the specific creature names, deity names, story details, and facts
consistent with REAL, documented mythology and folklore?

Rate each entry:
- ACCURATE   -- all specific claims appear in real documented sources
- UNCERTAIN  -- some claims are vague, hard to verify, or slightly off
- HALLUCINATED -- entry contains invented names, stories, or facts

Return ONLY a JSON array, one object per entry (in index order):
{{"index": <int>, "verdict": "ACCURATE"|"UNCERTAIN"|"HALLUCINATED", "reason": "<max 20 words>"}}

When genuinely unsure, prefer ACCURATE -- false positives remove valid content.

Entries:
{payload}

Return ONLY the JSON array, no other text."""

    try:
        resp = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=768,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        verdicts = json.loads(raw.strip())

        good_indices = {v["index"] for v in verdicts if v.get("verdict") == "ACCURATE"}
        for v in verdicts:
            if v.get("verdict") != "ACCURATE":
                idx = v.get("index")
                title = entries[idx].get("title", "?") if isinstance(idx, int) and idx < len(entries) else "?"
                log.info(f"  [self-critique] Removed '{title}': {v.get('verdict')} -- {v.get('reason', '')}")

        return [e for i, e in enumerate(entries) if i in good_indices]

    except Exception as exc:
        log.warning(f"  [self-critique] Failed ({exc}), skipping filter.")
        return entries


# -- Research -----------------------------------------------------------------

def research_topic(
    topic_name: str,
    topic_description: str,
    existing_titles: list[str],
) -> list[dict]:
    """
    Ask Groq to produce structured research entries for a topic.

    Method 1 -- Specificity enforcement: the prompt explicitly requires
    named, real, documented entities and forbids vague generalities.
    Asking for 5 entries (we only keep 3) gives the quality filters
    more to work with.
    """
    avoid_section = ""
    if existing_titles:
        formatted = "\n".join(f"  - {t}" for t in existing_titles)
        avoid_section = f"""
The following entries have ALREADY been researched and must NOT be repeated or closely rephrased:
{formatted}

Produce entries on entirely different aspects, creatures, myths, or stories not listed above.
"""

    prompt = f"""You are a research agent producing factual entries about mythology and folklore.

Topic: "{topic_name}" ({topic_description})
{avoid_section}
ACCURACY RULES -- follow strictly:
- Every entry MUST name at least one SPECIFIC, real, documented creature, deity, hero, or story by its actual name.
- Do NOT invent names, places, attributes, or events. Only include claims found in real documented mythology.
- If uncertain about a specific fact, omit it rather than guess.
- Do NOT write vague generalities -- be concrete and specific.
- Do NOT include disclaimers or phrases like "little is known" or "records are scarce."

Return ONLY a JSON array with exactly 5 objects. Each object must have:
- "title": a concise headline naming a specific creature, deity, or myth (max 10 words)
- "content": a factual paragraph (100-200 words) with specific, documented details
- "tags": an array of 3-5 relevant keyword strings
- "source_url": the Wikipedia URL most directly relevant (e.g. https://en.wikipedia.org/wiki/Banshee)

Return ONLY the JSON array, no other text."""

    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=3000,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


# -- Run loop -----------------------------------------------------------------

def run_agent_for_topic(topic: dict) -> None:
    topic_id = topic["id"]
    topic_name = topic["name"]
    log.info(f"Starting research run for topic: {topic_name}")

    run_res = supabase.table("agent_runs").insert({
        "topic_id": topic_id,
        "status": "running",
    }).execute()
    run_id = run_res.data[0]["id"]

    try:
        existing_titles = get_existing_titles(topic_id)
        existing_normalized = {t.strip().lower() for t in existing_titles}
        log.info(f"Found {len(existing_titles)} existing entries. Generating candidates...")

        # Generate 5 candidates
        raw_entries = research_topic(
            topic_name,
            topic.get("description") or "",
            existing_titles,
        )
        log.info(f"Generated {len(raw_entries)} candidates. Running quality filters...")

        # Method 2: AI self-critique
        entries = ai_self_critique(topic_name, raw_entries)
        log.info(f"After self-critique: {len(entries)} entries remain.")

        inserted = 0
        skipped_dup = 0
        skipped_rules = 0

        for entry in entries:
            if inserted >= 3:
                break

            title = entry.get("title", "Untitled")

            # Dedup check
            if title.strip().lower() in existing_normalized:
                log.info(f"  [dedup] Skipping duplicate: '{title}'")
                skipped_dup += 1
                continue

            # Method 3: Content rules
            valid, reason = validate_entry_rules(entry, topic_name)
            if not valid:
                log.info(f"  [rules] Skipping '{title}': {reason}")
                skipped_rules += 1
                continue

            # Method 4: URL reachability
            raw_url = entry.get("source_url")
            verified_url = check_url_reachability(raw_url)
            if raw_url and not verified_url:
                log.info(f"  [url] Dead link cleared for '{title}': {raw_url}")

            supabase.table("research_entries").insert({
                "topic_id": topic_id,
                "title": title,
                "content": entry.get("content", ""),
                "tags": entry.get("tags", []),
                "source_url": verified_url,
                "flagged_hallucination": False,
            }).execute()

            inserted += 1
            existing_normalized.add(title.strip().lower())

        supabase.table("agent_runs").update({
            "status": "completed",
            "entries_added": inserted,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()

        log.info(
            f"Done '{topic_name}': {inserted} saved, "
            f"{skipped_dup} dup(s), {skipped_rules} rule-fail(s) skipped."
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
    run_all_topics()

    schedule.every(6).hours.do(run_all_topics)
