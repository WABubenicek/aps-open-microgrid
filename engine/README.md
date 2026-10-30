# aps_engine v0.1 (PRELIMINARY — not licensed engineering)
Run tests: `python3 -m venv .venv && .venv/bin/pip install pytest && .venv/bin/python -m pytest -q tests`
API: design_system(req), get_incentives(req), model_financing(design, req), explore_tradeoffs(base, vary, req, outage_days).
Solar: PVWatts (developer.nlr.gov) when NLR_API_KEY is set and online=True; otherwise a SYNTHETIC profile, labeled low confidence.
Config: ../aps-config.v0.1.json (0.6.0). Any status "conflict" raises ConflictBlocked.
