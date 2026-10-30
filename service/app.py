"""APS Open Microgrid hosted API + MCP server (Cloud Run).

REST:  POST /v1/design_system, /v1/get_incentives, /v1/model_financing, /v1/explore_tradeoffs; GET /health
MCP:   streamable HTTP at /mcp exposing the same four tools.
No lead capture and no PII storage: requests are not persisted; only the ZIP is sent to the geocoder.
Public config only (aps-config.v0.1.json); the private config is never shipped in the image.
"""
import os, time, threading, ipaddress
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import aps_engine
from aps_engine import api as eng
from aps_engine.config import Config
from aps_engine.region import resolve_region

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

HANDOFF_EMAIL = "hello@antifragilepower.com"
DISCLAIMER = ("PRELIMINARY ESTIMATE ONLY - not licensed engineering, not a quote. Any installation requires review "
              "and stamping by a licensed professional (electrician/engineer) and local permitting.")
RATE_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))
GLOBAL_PER_MIN = int(os.environ.get("GLOBAL_RATE_LIMIT_PER_MIN", "300"))  # per instance; cost guard
ONLINE = os.environ.get("APS_ONLINE", "1") == "1"  # PVWatts + ZIP geocode lookups

CFG = Config(private={})  # explicit: never load private config in the hosted service


def _mode(req: dict) -> dict:
    region = resolve_region(CFG, req.get("address"), req.get("zip"))
    if region.get("turnkey_service_area"):
        return {"mode": "aps_service",
                "next_step": f"You are in the APS service area ({region.get('turnkey_area_text')}). "
                             f"For a firm quote, site visit, and licensed install contact {HANDOFF_EMAIL}.",
                "handoff_email": HANDOFF_EMAIL}
    return {"mode": "diy_nationwide",
            "next_step": "Outside the APS service area. Use the BOM as a shopping list: get independent quotes "
                         "for equipment and a licensed local electrician/installer, and procure independently.",
            "handoff_email": None}


def _wrap(result: Any, req: dict) -> dict:
    return {"disclaimer": DISCLAIMER, **_mode(req), "result": result}


def _req(d: dict | None) -> dict:
    d = dict(d or {})
    d.setdefault("online", ONLINE)
    return d


# ---- engine calls (shared by REST and MCP) ----
def t_design_system(req: dict) -> dict:
    r = _req(req); return _wrap(eng.design_system(r, CFG), r)

def t_get_incentives(req: dict) -> dict:
    r = _req(req); return _wrap(eng.get_incentives(r, CFG), r)

def t_model_financing(design: dict, req: dict) -> dict:
    r = _req(req); return _wrap(eng.model_financing(design, r, CFG), r)

def t_explore_tradeoffs(base_design: dict, vary: dict | None, req: dict) -> dict:
    r = _req(req)
    region = resolve_region(CFG, r.get("address"), r.get("zip"), r.get("online", False))
    return _wrap(eng.explore_tradeoffs(base_design, vary, r, CFG, region=region), r)


# ---- MCP ----
mcp = MCPServer("aps-open-microgrid", instructions="APS Open Microgrid design engine. Outputs are preliminary; "
                "licensed review required. Inputs: address or zip, outage_days, tier, pv_kw_new, etc.")

@mcp.tool()
def design_system(request: dict) -> dict:
    """Size a backup-power microgrid (inverter, batteries, PV, generator) for an address/ZIP and outage goal.
    request keys: address|zip, outage_days (default 7), tier (bare_minimum|...), kwh_day, peak_w, pv_kw_new,
    pv_kw_existing, gen_allowed, fuel_limit_gal, inverter, prefer_12k, finance_mode (cash|loan)."""
    return t_design_system(request)

@mcp.tool()
def get_incentives(request: dict) -> dict:
    """Incentives available for an address/ZIP. request: {address|zip}."""
    return t_get_incentives(request)

@mcp.tool()
def model_financing(design: dict, request: dict) -> dict:
    """Cost, incentives, payback/NPV for a design (as returned by design_system.result.design). request: {address|zip, finance_mode}."""
    return t_model_financing(design, request)

@mcp.tool()
def explore_tradeoffs(base_design: dict, request: dict, vary: dict | None = None) -> dict:
    """Grid of variants around a base design. vary: {battery_units:[..], pv_kw:[..], generator:[..], load_tier:[..]}."""
    return t_explore_tradeoffs(base_design, vary, request)

mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp", json_response=True, stateless_http=True,
                                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


@asynccontextmanager
async def lifespan(app):
    async with mcp_app.router.lifespan_context(app):
        yield

app = FastAPI(title="APS Open Microgrid API", version=aps_engine.api.ENGINE_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origin_regex=r"https://([a-z0-9-]+\.)?antifragilepower\.com",
                   allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"],
                   expose_headers=["mcp-session-id"])

_hits: dict[str, list[float]] = defaultdict(list); _lock = threading.Lock()

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path != "/health" and request.method != "OPTIONS":
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
        try:  # bucket IPv6 by /64
            a = ipaddress.ip_address(ip)
            if a.version == 6: ip = str(ipaddress.ip_network(f"{ip}/64", strict=False))
        except ValueError:
            pass
        now = time.time()
        with _lock:
            h = [t for t in _hits[ip] if now - t < 60]; h.append(now); _hits[ip] = h
            g = [t for t in _hits["*"] if now - t < 60]; g.append(now); _hits["*"] = g
            if len(_hits) > 10000: _hits.clear()
        if len(h) > RATE_PER_MIN or len(g) > GLOBAL_PER_MIN:
            return JSONResponse({"error": "rate limit exceeded", "limit_per_min": RATE_PER_MIN}, status_code=429)
    return await call_next(request)


@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception):
    return JSONResponse({"error": type(exc).__name__, "detail": str(exc), "disclaimer": DISCLAIMER}, status_code=400)


@app.get("/health")
def health():
    return {"ok": True, "engine_version": eng.ENGINE_VERSION, "config_version": CFG.version,
            "pvwatts_key": bool(os.environ.get("NLR_API_KEY")), "online": ONLINE, "disclaimer": DISCLAIMER}

@app.post("/v1/design_system")
def r_design(body: dict):
    return t_design_system(body)

@app.post("/v1/get_incentives")
def r_inc(body: dict):
    return t_get_incentives(body)

@app.post("/v1/model_financing")
def r_fin(body: dict):
    """body: {design: {...}, request: {address|zip, ...}}"""
    return t_model_financing(body["design"], body.get("request", {}))

@app.post("/v1/explore_tradeoffs")
def r_trade(body: dict):
    """body: {base_design: {...}, vary: {...}, request: {...}}"""
    return t_explore_tradeoffs(body["base_design"], body.get("vary"), body.get("request", {}))

app.mount("/", mcp_app)
