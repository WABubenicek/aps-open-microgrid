import os, sys
sys.path[:0] = [os.path.join(os.path.dirname(__file__), ".."), os.path.join(os.path.dirname(__file__), "..", "..", "engine")]
os.environ["APS_ONLINE"] = "0"
from fastapi.testclient import TestClient
import app as svc

import pytest
from contextlib import nullcontext
_C = None

def client():
    # MCP session manager can only start once per process: share one started client
    global _C
    if _C is None:
        _C = TestClient(svc.app); _C.__enter__()
    return nullcontext(_C)

def test_health():
    with client() as c:
        assert c.get("/health").json()["ok"]

def test_design_modes():
    with client() as c:
        a = c.post("/v1/design_system", json={"address": "10234 Main St, Brewster, MA 02631"}).json()
        assert a["mode"] == "aps_service" and a["handoff_email"] == "hello@antifragilepower.com" and "PRELIMINARY" in a["disclaimer"]
        b = c.post("/v1/design_system", json={"address": "1 Congress Ave, Austin, TX 78701"}).json()
        assert b["mode"] == "diy_nationwide" and b["handoff_email"] is None
        assert a["result"]["solar"]["confidence"] == "low"  # offline -> synthetic labelled

def test_mcp_lists_tools():
    with client() as c:
        h = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
        r = c.post("/mcp", headers=h, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        names = {t["name"] for t in r.json()["result"]["tools"]}
        assert names == {"design_system", "get_incentives", "model_financing", "explore_tradeoffs"}

def test_private_config_not_loaded():
    assert svc.CFG.private == {}

def test_rate_limit(monkeypatch):
    monkeypatch.setattr(svc, "RATE_PER_MIN", 2)
    with client() as c:
        codes = [c.post("/v1/get_incentives", json={}, headers={"x-forwarded-for": "2001:db8::%d" % i}).status_code for i in range(4)]
    assert codes[-1] == 429  # same /64 shares a bucket
