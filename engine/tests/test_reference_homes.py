"""Reference homes (spec §15) + known-error regressions. Do not weaken to pass."""
import copy, math, pytest
from aps_engine import (design_system, explore_tradeoffs, get_incentives, model_financing, parse_zip,
                        resolve_region, simulate, Config, ConflictBlocked, pick_with_tie_band)
from aps_engine.load import build_load
from aps_engine.costs import cost_design
from aps_engine.finance import grid_services

CFG = Config()
BREWSTER = "10234 Main St, Brewster, MA 02631"


def status(out, cand):
    return next(e for e in out["platform_report"] if e["candidate"] == cand)


# ---- Region / ZIP (F-7) ----
def test_F_house_number_not_zip():
    assert parse_zip(BREWSTER) == "02631"
    r = resolve_region(CFG, BREWSTER)
    assert r["pack_id"] == "ma-clc" and r["state"] == "MA"

def test_house_number_only_digits_no_state():
    assert parse_zip("12345 Ocean Ave") is None  # house number alone is never a ZIP

def test_zip4_and_explicit_field_precedence():
    assert parse_zip("1 Main St, Austin, TX 78701-1234") == "78701"
    assert parse_zip("02631 Fake Rd, Chatham, MA 02633", zip_field="02631") == "02631"
    assert parse_zip("99 Elm, Chatham, MA 02633") == "02633"

def test_G_blank_address_is_unknown_not_outside_ma():
    r = resolve_region(CFG, "")
    assert r["status"] == "unknown" and r["state"] is None and r["pack_id"] is None
    out = design_system({"address": "", "outage_days": 3})
    assert out["region"]["status"] == "unknown"
    assert out["confidence"]["region"] == "none"

def test_nantucket_in_turnkey_area_and_not_clc():
    r = resolve_region(CFG, "5 Main St, Nantucket, MA 02554")
    assert r["turnkey_service_area"] and r["nantucket"]
    assert r["pack_id"] == "ma-other"  # National Grid territory, not CLC
    assert "Nantucket" in r["turnkey_area_text"]


# ---- E: non-MA ----
def test_E_austin_finance_hidden_cs_zero():
    out = design_system({"address": "100 Congress Ave, Austin, TX 78701", "tier": "critical", "kwh_day": 20, "pv_kw_new": 6, "outage_days": 3})
    f = out["finance"]
    assert f["finance_available"] is False and f["payback_years"] is None
    assert "not available" in f["reason"]
    assert f["grid_services"] == [] and f["incentives"]["total_incentives"] == 0
    assert out["design"] is not None  # resilience still designed


# ---- T: Brewster 7-day, PW3 rejected ----
def test_T_brewster_7day_rejects_pw3_picks_solark():
    out = design_system({"address": BREWSTER, "tier": "critical", "kwh_day": 15.38, "pv_kw_new": 4, "outage_days": 7})
    pw3 = status(out, "tesla-powerwall-3")
    assert pw3["status"] == "rejected"
    assert any("cannot recharge battery from generator" in r for r in pw3["reasons"])
    assert out["design"]["inverter"].startswith("solark")

def test_pw3_not_rejected_for_gen_when_goal_needs_no_gen():
    out = design_system({"address": BREWSTER, "tier": "bare_minimum", "pv_kw_new": 8, "outage_days": 1})
    pw3 = status(out, "tesla-powerwall-3")
    assert not any("generator" in r for r in pw3["reasons"])
    assert pw3["status"] in ("needs_research", "rejected")  # price unknown -> never recommended


# ---- 15K default / 12K vs 15K / H ----
def test_15k_is_default_inverter():
    out = design_system({"address": BREWSTER, "tier": "critical", "kwh_day": 15.38, "pv_kw_new": 4, "outage_days": 7})
    assert out["design"]["inverter"] == "solark-15k-2p-n"
    assert status(out, "solark-12k-2p-n")["status"] == "alternative"

def test_12k_optional_and_cs_eligible_vs_15k_pending():
    req = {"address": BREWSTER, "tier": "critical", "kwh_day": 15.38, "pv_kw_new": 4, "outage_days": 7}
    o12 = design_system({**req, "prefer_12k": True})
    o15 = design_system(req)
    assert o12["design"]["inverter"] == "solark-12k-2p-n"
    g12 = o12["finance"]["grid_services"][0]; g15 = o15["finance"]["grid_services"][0]
    assert g12["status"] == "included" and g12["included_in_payback"]
    assert g15["status"] == "pending eligibility" and not g15["included_in_payback"]  # F-2
    assert o15["finance"]["grid_services_income_included"] == 0

def test_12k_rejected_above_9kw_peak():
    out = design_system({"address": BREWSTER, "tier": "critical", "kwh_day": 25, "peak_w": 10500, "outage_days": 3})
    assert status(out, "solark-12k-2p-n")["status"] == "rejected"
    assert out["design"]["inverter"] == "solark-15k-2p-n"

def test_H_chatham_peak_12975_not_15k():
    out = design_system({"address": "1 Main St, Chatham, MA 02633", "tier": "whole_home", "kwh_day": 29.5, "peak_w": 12975, "outage_days": 3})
    assert status(out, "solark-15k-2p-n")["status"] == "rejected"  # 12 kW battery-side
    assert out["design"]["inverter"] == "solark-18k-2p-n"
    assert all(h <= 24 for h in out["simulation_storm"]["gen_hrs_per_day"])  # no 1,372 h recharge

def test_12k_gen_port_limits_xp13000():
    out = design_system({"address": BREWSTER, "tier": "critical", "kwh_day": 15.38, "pv_kw_new": 4, "outage_days": 7, "prefer_12k": True})
    assert out["simulation_storm"]["gen_effective_kw"] == 9.6
    o15 = design_system({"address": BREWSTER, "tier": "critical", "kwh_day": 15.38, "pv_kw_new": 4, "outage_days": 7})
    assert o15["simulation_storm"]["gen_effective_kw"] == 10.5


# ---- Generator ----
def test_manual_start_generator_copy():
    out = design_system({"address": BREWSTER, "outage_days": 7})
    assert "Manual-start" in out["generator_operation"] and "you start it" in out["generator_operation"]

def test_infeasible_never_infinite():
    out = design_system({"address": BREWSTER, "tier": "critical", "kwh_day": 15.38, "outage_days": 7, "gen_allowed": False})
    s = out.get("simulation_storm")
    if s:
        assert all(math.isfinite(x) for x in s["fuel_gal_per_day"])
    for e in out["platform_report"]:
        assert "inf" not in " ".join(e["reasons"]).lower().replace("info", "")


# ---- Solar double count (F-3, F-27) ----
def test_A_no_double_counted_new_solar():
    base = {"inverter": "solark-15k-2p-n", "battery": "eg4-wallmount-powerpro-14.3", "battery_units": 2,
            "generator": "duromax-xp13000hxt", "pv_kw_new": 4}
    req = {"address": BREWSTER}
    f_new = model_financing({**base, "pv_kw_existing": 0}, req)
    f_add = model_financing({**base, "pv_kw_existing": 10}, req)
    assert f_new["solar_new_kwh_yr1"] == f_add["solar_new_kwh_yr1"]
    assert 4500 <= f_new["solar_new_kwh_yr1"] <= 5600   # ~5,048, not 10,108

def test_C_existing_pv_not_counted_in_savings_and_served():
    out = design_system({"address": "1 Main St, Falmouth, MA 02540", "tier": "whole_home", "kwh_day": 33, "peak_w": 14500,
                         "pv_kw_existing": 10, "pv_kw_new": 0, "outage_days": 3})
    assert out["design"] is not None and out["simulation_storm"]["feasible"]
    f = out["finance"]
    assert f["solar_new_kwh_yr1"] == 0
    assert max(out["simulation_storm"]["gen_hrs_per_day"]) <= 24


# ---- Autonomy on daily kWh, not peak (F-1) ----
def test_B_autonomy_uses_avg_not_peak():
    out = design_system({"address": "1 Commercial St, Provincetown, MA 02657", "tier": "critical", "kwh_day": 20.5, "peak_w": 7350, "outage_days": 3})
    ld = out["load"]
    assert abs(ld["avg_kw"] - 20.5 / 24) < 1e-6
    assert out["battery_only_hours_avg_load"] >= 24
    usable = out["simulation_storm"]["usable_kwh"]
    assert out["battery_only_hours_avg_load"] > usable / 7.35 * 2  # would be ~4 h if peak were used


# ---- Fuel at storm sun (F-4) + BM sanity ----
def test_BM_fuel_plan_10_15_gal_storm():
    out = design_system({"address": BREWSTER, "tier": "bare_minimum", "pv_kw_new": 0, "outage_days": 7, "battery_units": 1})
    fp = out["fuel_plan"]
    assert fp["energy_kwh"] == 45.5 and "STORM" in fp["basis"]
    assert 10 <= fp["plan_gal"] <= 15
    assert 3 <= fp["sim_gal"] <= 15

def test_fuel_headline_storm_exceeds_average():
    out = design_system({"address": BREWSTER, "tier": "critical", "kwh_day": 15.38, "pv_kw_new": 6, "outage_days": 7})
    assert out["simulation_storm"]["weather_case"] == "storm"
    assert out["simulation_storm"]["total_gal"] > out["simulation_average_info_only"]["total_gal"]


# ---- Batteries ----
def test_LP4_three_units_15_36():
    d = {"inverter": "solark-12k-2p-n", "battery": "eg4-lifepower4-v2-5.12", "battery_units": 3, "generator": None, "gen_allowed": False}
    s = simulate(CFG, d, build_load(CFG), resolve_region(CFG, BREWSTER), "storm", 1)
    assert abs(s["usable_kwh"] - 15.36 * 0.9) < 0.01  # 15.36 kWh nominal, not 42.9

def test_adding_battery_never_lowers_resilience():
    r = resolve_region(CFG, BREWSTER); ld = build_load(CFG, "critical", 15.38)
    prev = -1
    for u in range(1, 6):
        d = {"inverter": "solark-15k-2p-n", "battery": "eg4-wallmount-powerpro-14.3", "battery_units": u,
             "generator": "duromax-xp13000hxt", "pv_kw_new": 4}
        s = simulate(CFG, d, ld, r, "storm", 7)
        assert s["resilience_hours"] >= prev and s["unserved_kwh"] == 0
        prev = s["resilience_hours"]

def test_cs_kw_formula_capped():
    d = {"inverter": "solark-12k-2p-n", "battery": "eg4-wallmount-powerpro-14.3", "battery_units": 1, "n_inverters": 1}
    g = grid_services(CFG, d, resolve_region(CFG, BREWSTER), 12.87)[0]
    assert g["paid_kw"] == round(12.87 / 3, 2)  # usable/3, not 5 kW per battery


# ---- Policy / outputs ----
def test_conflict_values_refused():
    data = copy.deepcopy(CFG.data)
    data["prices"]["permit"]["status"] = "conflict"; data["prices"]["permit"]["conflict_id"] = "CX"
    with pytest.raises(ConflictBlocked):
        design_system({"address": BREWSTER}, cfg=Config(data))

def test_same_payload_same_price():
    req = {"address": BREWSTER, "tier": "critical", "kwh_day": 15.38, "pv_kw_new": 4, "outage_days": 7}
    a, b = design_system(req), design_system(req)
    assert a["bom"]["total_at_cost"] == b["bom"]["total_at_cost"] and a["bom"]["markup"] == 0

def test_outputs_have_disclaimers_attribution_handoff_confidence():
    out = design_system({"address": BREWSTER})
    assert out["handoff"]["email"] == "hello@antifragilepower.com"
    assert out["handoff"]["label"] == "Get a firm quote / financing" and out["handoff"]["consent_required"]
    assert "will not be sold" in out["handoff"]["consent_text"]
    assert out["disclaimers"] and "Antifragile" in out["attribution"]
    assert set(out["confidence"]) >= {"region", "tariff", "climate"}
    assert all("confidence" in l for l in out["bom"]["lines"])

def test_payback_hidden_when_tariff_low():
    r = resolve_region(CFG, BREWSTER); r = {**r, "tariff_confidence": "low"}
    from aps_engine.finance import model_financing as mf
    d = {"inverter": "solark-15k-2p-n", "battery": "eg4-wallmount-powerpro-14.3", "battery_units": 2, "generator": None, "pv_kw_new": 4}
    f = mf(CFG, r, d, cost_design(CFG, d), 25.7)
    assert f["payback_years"] is None and not f["finance_available"]

def test_loan_and_lease_paths():
    d = {"inverter": "solark-15k-2p-n", "battery": "eg4-wallmount-powerpro-14.3", "battery_units": 2, "generator": None, "pv_kw_new": 6}
    f = model_financing(d, {"address": BREWSTER, "finance_mode": "loan"})
    assert f["loan"]["monthly_payment"] > 0
    assert "UNVERIFIED" in f["lease_tpo"]["note"]

def test_rest_of_ma_cs_estimate_not_in_payback():
    d = {"inverter": "solark-12k-2p-n", "battery": "eg4-wallmount-powerpro-14.3", "battery_units": 2, "generator": None, "pv_kw_new": 4}
    f = model_financing(d, {"address": "1 Main St, Worcester, MA 01608"})
    assert all(not g["included_in_payback"] for g in f["grid_services"])

def test_tie_band_prefers_solark():
    c = [{"id": "x", "platform": "eg4", "net_cost": 10000}, {"id": "s", "platform": "sol-ark", "net_cost": 10400}]
    assert pick_with_tie_band(c, 0.05)["id"] == "s"
    c[1]["net_cost"] = 10600
    assert pick_with_tie_band(c, 0.05)["id"] == "x"

def test_explore_tradeoffs_recommends_cheapest_meeting_goal():
    base = {"inverter": "solark-15k-2p-n", "battery": "eg4-wallmount-powerpro-14.3", "battery_units": 2,
            "generator": "duromax-xp13000hxt", "pv_kw_new": 4}
    ex = explore_tradeoffs(base, {"battery_units": [1, 2, 3, 4], "pv_kw": [0, 4, 8]},
                           {"address": BREWSTER, "tier": "critical", "kwh_day": 15.38}, outage_days=7)
    assert len(ex["grid"]) == 12
    ok = [r for r in ex["grid"] if r["meets_goal"]]
    assert ex["recommendation"]["cost_at_cost"] == min(r["cost_at_cost"] for r in ok)
    assert ex["recommendation"]["battery_units"] >= 2  # min 2 units for a serious system
    assert all(not r["meets_goal"] for r in ex["grid"] if r["battery_units"] < 2)

def test_get_incentives_ma_only():
    assert "ma_state_credit" in get_incentives({"address": BREWSTER})["incentives"]
    assert "ma_state_credit" not in get_incentives({"address": "1 Main, Austin, TX 78701"})["incentives"]
