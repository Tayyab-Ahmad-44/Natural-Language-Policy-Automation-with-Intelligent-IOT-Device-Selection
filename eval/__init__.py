"""
Evaluation harness for the NL -> DAG compiler and conflict detector.

Isolated from backend/ application code: nothing here is imported by the
FastAPI app, and nothing here modifies backend/ files. This __init__ only
adds backend/ to sys.path so eval submodules can import the real
schemas.ExecutionDAG / dag_utils.topological_levels contracts directly,
instead of maintaining a second, parallel data model that could drift from
what the pipeline actually produces.
"""

import os
import sys
import pathlib

_BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# llm.py (via llm_provider.py) calls load_dotenv() with no explicit path,
# which searches upward from the current working directory -- fine when the
# app is run from backend/, but this harness runs from the repo root, where
# that search never reaches backend/.env. Load it explicitly, here, before
# anything else touches GROQ_API_KEY/OPENAI_API_KEY: the `load_dotenv`
# package defaults to override=False (won't clobber a var that's already
# set), so if the placeholders below were set first they'd permanently block
# the real key from ever loading.
try:
    from load_dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=_BACKEND_DIR / ".env")
except ImportError:
    pass

# Only a true last resort: conflicts.py unconditionally imports llm.py, and
# llm.py imports llm_provider, which constructs an LLM client at *module
# import time* -- both the Groq and OpenAI SDKs raise immediately if their
# respective API key is entirely unset, not just empty. Without this
# fallback, merely importing conflicts.py (needed for its pure, offline
# rule-based fallback and pre-filter logic) would hard-fail on a machine
# with no backend/.env, breaking the pytest suite's "no network calls"
# requirement before a single test runs. Both keys are seeded regardless of
# which LLM_PROVIDER is configured, since either SDK could be the one
# constructed depending on that setting -- setdefault() only fills a gap,
# so a real key already loaded above from .env is never touched.
PLACEHOLDER_GROQ_API_KEY = "eval-harness-placeholder-unused-unless-use_llm=True"
PLACEHOLDER_OPENAI_API_KEY = "eval-harness-placeholder-unused-unless-use_llm=True"
os.environ.setdefault("GROQ_API_KEY", PLACEHOLDER_GROQ_API_KEY)
os.environ.setdefault("OPENAI_API_KEY", PLACEHOLDER_OPENAI_API_KEY)
