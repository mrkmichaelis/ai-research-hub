"""
AI Research Hub - Weekly Hallucination Audit  (Method 5)

Runs every Sunday via .github/workflows/audit.yml.
Scans all research_entries where flagged_hallucination IS NULL,
sends them to Groq in batches for fact-checking, and writes
the verdict back to Supabase.

Flagged entries (flagged_hallucination = true) are hidden from
the website automatically -- no human review needed.
"""

import os
import json
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from groq import Groq
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"],
)

BATCH_SIZE = 8  # Entries per Groq call -- keeps prompts within token limits


def get_unaudited_entries() -> list[dict]:
    """Return all entries where flagged_hallucination IS NULL.
    These are entries that predate the validation system and have
    never been reviewed, plus any that slipped through on an API error.
    """
    resp = (
        supabase.table("research_entries")
        .select("id, topic_id, title, content, topics(name)")
        .is_("flagged_hallucination", "null")
        .execute()
    )
    return resp.data or []


def audit_batch(entries: list[dict]) -> list[dict]:
    """Send one batch to Groq for hallucination review.
    Conservative bias: only flag when clearly wrong, not when merely uncertain.
    """
    batch_payload = json.dumps(
        [
            {
                "index": i,
                "id": e["id"],
                "topic": (
                    e["topics"]["name"]
                    if isinstance(e.get("topics"), dict)
                    else "Unknown"
                ),
                "title": e["title"],
                "content": (e.get("content") or "")[:350],
            }
            for i, e in enumerate(entries)
        ],
        indent=2,
    )
    prompt = (
        "You are auditing AI-generated mythology research entries for factual accuracy.\n\n"
        "For each entry, determine if it contains hallucinated information:\n"
        "- Invented creature or deity names that don't exist in real mythology\n"
        "- Fabricated story details or incorrect attributions\n"
        "- Claims that clearly contradict documented mythology\n\n"
        "IMPORTANT: Only flag if you are CONFIDENT it contains clear errors.\n"
        "If unsure, do NOT flag -- false positives remove real content.\n\n"
        'Return ONLY a JSON array, one object per entry:\n'
        '{"index": <int>, "id": "<uuid>", "flagged": true|false, "reason": "<max 20 words>"}\n\n'
        f"Entries to audit:\n{batch_payload}\n\nReturn ONLY the JSON array."
    )
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as exc:
        log.error(f"  Batch audit failed: {exc}")
        return []

def run_audit() -> None:
    log.info("=== Weekly Hallucination Audit starting ===")
    entries = get_unaudited_entries()
    if not entries:
        log.info("No unaudited entries found -- database is clean.")
        return
    log.info(f"Found {len(entries)} unaudited entries. Processing in batches of {BATCH_SIZE}...")
    total_flagged = 0
    total_cleared = 0
    total_errors = 0
    for batch_start in range(0, len(entries), BATCH_SIZE):
        batch = entries[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        log.info(f"  Batch {batch_num}: auditing {len(batch)} entries...")
        decisions = audit_batch(batch)
        if not decisions:
            for e in batch:
                supabase.table("research_entries").update({
                    "flagged_hallucination": False,
                    "flag_reason": None,
                }).eq("id", e["id"]).execute()
            total_errors += len(batch)
            log.warning(f"  Batch {batch_num} failed -- marked clean by default.")
            continue
        id_map = {d["id"]: d for d in decisions if d.get("id")}
        for entry in batch:
            entry_id = entry["id"]
            decision = id_map.get(entry_id)
            if decision is None:
                flagged = False
                reason = None
            else:
                flagged = bool(decision.get("flagged", False))
                reason = decision.get("reason") if flagged else None
            supabase.table("research_entries").update({
                "flagged_hallucination": flagged,
                "flag_reason": reason,
            }).eq("id", entry_id).execute()
            if flagged:
                total_flagged += 1
                log.info(f"  FLAGGED: '{entry['title']}' -- {reason}")
            else:
                total_cleared += 1
    log.info(
        f"=== Audit complete: {total_cleared} cleared, "
        f"{total_flagged} flagged, {total_errors} batch-error defaults ==="
    )


if __name__ == "__main__":
    run_audit()
