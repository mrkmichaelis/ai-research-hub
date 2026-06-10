"""
One-shot agent run — used by GitHub Actions cron workflow.
Calls run_all_topics() once and exits (no scheduling loop).
"""
import os
import sys

# Ensure the meta-agent directory is on the path when run from repo root
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from agent import run_all_topics

if __name__ == "__main__":
    run_all_topics()
