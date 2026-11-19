"""Sol-Ark Limitless 12K-2P-LL (rules engine) and announced S16 battery (opt-in only)."""
from aps_engine.api import design_system, explore_tradeoffs

BREWSTER = "1 Main St, Brewster, MA 02631"
MODEST = {"address": BREWSTER, "tier": "critical", "kwh_day": 15.38, "pv_kw_new": 4, "outage_days": 7}


def status(out, cid):
    return next(e for e in out["platform_report"] if e["candidate"] == cid)


def test_12k_ll_selected_on_modest_load_home():
    out = design_system(MODEST)
    assert out["load"]["peak_w"] <= 10000
    assert out["design"]["inverter"] == "solark-12k-2p-ll"
    e = status(out, "solark-12k-2p-ll")
    assert e["status"] == "picked" and "12K-LL rule" in e["reasons"][0]
    assert any("100 A grid passthrough" in r for r in e["reasons"])
    assert status(out, "solark-15k-2p-n")["status"] == "alternative"
    assert status(out, "solark-12k-2p-n")["status"] == "alternative"  # legacy still evaluated
    inv_line = out["bom"]["lines"][0]
    assert inv_line["item"] == "Sol-Ark Limitless 12K-2P-LL" and inv_line["total"] == 3999
    assert out["simulation_storm"]["gen_effective_kw"] > 9.6  # 14 kW GEN port: no 9.6 kW clip like 12K-2P-N


def test_12k_ll_rejected_above_10kw_peak():
    out = design_system({"address": BREWSTER, "tier": "critical", "kwh_day": 25, "peak_w": 10500, "outage_days": 3})
    assert status(out, "solark-12k-2p-ll")["status"] == "rejected"
    assert out["design"]["inverter"] == "solark-15k-2p-n"


def test_s16_not_chosen_by_default():
    out = design_system(MODEST)
    assert out["design"]["battery"] == "eg4-wallmount-powerpro-14.3"
    assert "battery_comparison" not in out
    assert all(r["battery"] != "solark-s16" for r in out["tradeoffs"]["grid"])


def test_s16_opt_in_battery_brand():
    out = design_system({**MODEST, "battery_brand": "sol-ark-s16"})
    assert out["design"]["battery"] == "solark-s16"
    assert any("UL 9540" in w for w in out["warnings"])
    cmp_ = out["battery_comparison"]
    assert cmp_["solark-s16"]["availability"] == "announced" and cmp_["solark-s16"]["price_status"] == "announced"
    assert cmp_["solark-s16"]["per_usable_kwh"] == round(4350 / 16)
    assert "cost_at_cost" in cmp_["eg4-wallmount-powerpro-14.3"]
    assert any("Apr 2027" in f for f in cmp_["flags"])
    assert status(out, "solark-12k-2p-n")["status"] == "rejected"  # S16 not listed for legacy 12K-2P-N


def test_s16_include_announced_keeps_eg4_default():
    out = design_system({**MODEST, "include_announced": True})
    assert out["design"]["battery"] == "eg4-wallmount-powerpro-14.3"
    assert "solark-s16" in out["battery_comparison"]


def test_explore_tradeoffs_s16_opt_in():
    base = {"inverter": "solark-12k-2p-ll", "battery": "eg4-wallmount-powerpro-14.3", "battery_units": 2,
            "pv_kw_new": 4, "generator": "duromax-xp13000hxt"}
    ex = explore_tradeoffs(base, None, {**MODEST, "include_announced": True})
    assert {r["battery"] for r in ex["grid"]} == {"eg4-wallmount-powerpro-14.3", "solark-s16"}
    assert "battery_comparison" in ex
    ex0 = explore_tradeoffs(base, None, MODEST)
    assert {r["battery"] for r in ex0["grid"]} == {"eg4-wallmount-powerpro-14.3"}
