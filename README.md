# APS Open Microgrid

A free, public, **preliminary** microgrid design engine for any US address: hybrid inverter + LFP battery + generator (with optional solar).

## Modes
- **APS service area** — Massachusetts: Cape Cod, the Islands (incl. Nantucket), and SouthCoast. Designs can be handed off for an APS turnkey quote at **hello@antifragilepower.com** (with explicit opt-in consent only).
- **Nationwide DIY** — anywhere in the US: system design, bill of materials, incentives, and financials so you can procure and install independently with licensed local professionals.

## Contents
- `spec-v0.1.md` — engine specification
- `aps-config.v0.1.json` — public configuration (equipment catalog, prices, assumptions, sources)
- `conflicts.md` — resolved/open data conflicts log
- `engine/` — `aps_engine` Python package and tests

## Quick start
```bash
cd engine
python -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest -q tests
```
Solar uses NREL/NLR PVWatts v8 when `NLR_API_KEY` is set in your environment; otherwise a synthetic, low-confidence profile. Never commit keys.

## Important disclaimer
All outputs are **preliminary estimates** and require review by licensed professionals (electrician, engineer, AHJ) before purchase or installation. No warranty; see LICENSE.

## Roadmap
Planned hosted API + MCP server exposing: `design_system`, `get_incentives`, `model_financing`, `explore_tradeoffs`.

## Licenses & trademarks
- Code: Apache-2.0 (`LICENSE`)
- Data/config: CC-BY-4.0 (`DATA-LICENSE`)
- "APS", "Antifragile Power Systems" and "WABD" names and marks are **not** licensed under either license.

## Hosted API + MCP server

A public instance runs on Google Cloud Run: `https://aps-engine-453566584239.us-east1.run.app`

- REST: `POST /v1/design_system`, `/v1/get_incentives`, `/v1/model_financing`, `/v1/explore_tradeoffs`; `GET /health`
- MCP (streamable HTTP): `https://aps-engine-453566584239.us-east1.run.app/mcp` (same four tools)

Every response carries a preliminary / licensed-review disclaimer and a `mode`: `aps_service` inside the APS
service area (handoff hello@antifragilepower.com) or `diy_nationwide` (procure the BOM independently).
Solar uses PVWatts v8 when `NLR_API_KEY` is set (source labelled in `result.solar`), else a synthetic profile.
No requests or personal data are stored. Source: `service/`, `Dockerfile`.
