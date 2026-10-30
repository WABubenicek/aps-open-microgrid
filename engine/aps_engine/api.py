"""Public functions: design_system, get_incentives, model_financing, explore_tradeoffs."""
import math
from .config import Config, ConflictBlocked
from .region import resolve_region
from .load import build_load
from .equipment import inverter, battery, generator
from .simulate import simulate, battery_only_hours
from .costs import cost_design
from . import finance as _fin

ENGINE_VERSION = "0.1.0"
SOLARK = ["solark-12k-2p-n", "solark-15k-2p-n", "solark-18k-2p-n"]
RESEARCH_PLATFORMS = ["eg4", "enphase", "franklinwh"]


def _cfg(cfg):
    return cfg if cfg is not None else Config()


def _floor_units(cfg, sku, load, target_h):
    b = battery(cfg, sku)
    rte = cfg.val("design_rules/battery/round_trip_eff")
    per = b["kwh"] * b["usable_fraction"] * rte ** 0.5
    return max(cfg.val("design_rules/battery/min_units_serious"), math.ceil(target_h * load["avg_kw"] / per))


def _meets(sim, req):
    if not sim["feasible"]:
        return False
    if not req.get("gen_allowed", True) and sim["gen_kwh"] > 0:
        return False
    lim = req.get("fuel_limit_gal")
    return lim is None or sim["total_gal"] <= lim


def explore_tradeoffs(base_design, vary=None, req=None, cfg=None, weather_case="storm", outage_days=None,
                      load=None, region=None):
    cfg = _cfg(cfg); req = req or {}
    region = region or resolve_region(cfg, req.get("address"), req.get("zip"))
    outage_days = outage_days or req.get("outage_days", 7)
    vary = vary or {}
    tiers = vary.get("load_tier", [req.get("tier", "bare_minimum")])
    grid = []
    min_u = cfg.val("design_rules/battery/min_units_serious")
    for tier in tiers:
        ld = load if (load and tier == load["tier"]) else build_load(cfg, tier, req.get("kwh_day"), req.get("peak_w"),
                                                                      req.get("appliances"), req.get("adders"))
        for u in vary.get("battery_units", [base_design.get("battery_units", 2)]):
            for pv in vary.get("pv_kw", [base_design.get("pv_kw_new", 0)]):
                for g in vary.get("generator", [base_design.get("generator")]):
                    d = {**base_design, "battery_units": u, "pv_kw_new": pv, "generator": g,
                         "gen_allowed": g is not None and base_design.get("gen_allowed", True)}
                    s = simulate(cfg, d, ld, region, weather_case, outage_days)
                    c = cost_design(cfg, d)
                    row = {"inverter": d["inverter"], "battery_units": u, "usable_kwh": s["usable_kwh"], "pv_kw_new": pv,
                           "generator": g, "gen_kw_effective": s["gen_effective_kw"], "load_tier": tier,
                           "kwh_day": ld["kwh_day"], "cost_at_cost": c["total_at_cost"],
                           "gen_hrs_per_day": s["avg_gen_hrs_per_day"], "total_gal": s["total_gal"],
                           "gen_free_hours": s["gen_free_hours"], "unserved_kwh": s["unserved_kwh"],
                           "resilience_hours": s["resilience_hours"],
                           "below_min_units": u < min_u,
                           "meets_goal": _meets(s, {**req, "gen_allowed": d["gen_allowed"]}) and u >= min_u}
                    if c["total_at_cost"] is not None:
                        f = _fin.model_financing(cfg, region, d, c, s["usable_kwh"])
                        row.update(annual_value=f.get("annual_value_yr1"), simple_payback=f.get("payback_years"),
                                   npv=f.get("npv"))
                    grid.append(row)
    ok = [r for r in grid if r["meets_goal"] and r["cost_at_cost"] is not None]
    rec = min(ok, key=lambda r: (r["cost_at_cost"], r["total_gal"])) if ok else None
    return {"weather_case": weather_case, "outage_days": outage_days, "grid": grid, "recommendation": rec}


def _size_platform(cfg, iid, req, load, region):
    """Return best design for one inverter model (or rejection)."""
    inv = inverter(cfg, iid)
    peak = load["peak_w"]
    pv_total = (req.get("pv_kw_new", 0) + req.get("pv_kw_existing", 0)) * 1000
    reasons = []
    if inv["battery_side_w"] < peak:
        reasons.append(f"peak {peak:.0f} W exceeds battery-side continuous {inv['battery_side_w']} W")
    if inv["pv_max_w"] and pv_total > inv["pv_max_w"] * (inv["max_units"] if inv["platform"] == "tesla" else 1):
        reasons.append(f"PV {pv_total/1000:.1f} kW exceeds usable PV max {inv['pv_max_w']/1000:.1f} kW")
    if reasons:
        return {"status": "rejected", "reasons": reasons}
    gen_id = req.get("generator", cfg.val("catalog/default_portable_generator")) if req.get("gen_allowed", True) else None
    base = {"inverter": iid, "n_inverters": 1, "pv_kw_new": req.get("pv_kw_new", 0),
            "pv_kw_existing": req.get("pv_kw_existing", 0), "generator": gen_id,
            "gen_allowed": req.get("gen_allowed", True), "battery": req.get("battery", "eg4-wallmount-powerpro-14.3")}
    if inv["platform"] == "tesla":
        units_opts = list(range(1, inv["max_units"] + 1))
    else:
        f = _floor_units(cfg, base["battery"], load, req.get("target_hours", 24))
        units_opts = list(range(f, f + 4))
    ex = explore_tradeoffs(base, {"battery_units": units_opts}, req, cfg, "storm", req.get("outage_days", 7), load, region)
    feas = [r for r in ex["grid"] if r["meets_goal"]]
    notes = []
    gen = generator(cfg, gen_id)
    if gen and inv["platform"] != "tesla" and gen["rated_kw"] * 1000 > inv["gen_port_max_w"]:
        notes.append(f"generator {gen['rated_kw']} kW limited to {inv['gen_port_max_w']/1000:.1f} kW at GEN port")
    if not feas:
        worst = min(ex["grid"], key=lambda r: r["unserved_kwh"])
        return {"status": "rejected", "reasons": [f"goal not met at storm sun: {worst['unserved_kwh']} kWh unserved"
                                                  if worst["unserved_kwh"] > 0 else "goal not met (fuel/gen limit)"], "tradeoffs": ex}
    priced = [r for r in feas if r["cost_at_cost"] is not None]
    if not priced:
        return {"status": "needs_research", "reasons": ["price unknown (NEEDS RESEARCH)"], "tradeoffs": ex, "notes": notes}
    best = min(priced, key=lambda r: (r["cost_at_cost"], r["total_gal"]))
    design = {**base, "battery_units": best["battery_units"]}
    return {"status": "candidate", "design": design, "row": best, "tradeoffs": ex, "notes": notes}


def pick_with_tie_band(cands, band, preferred_platform="sol-ark"):
    """cands: [{id, platform, net_cost}]. Lowest net cost wins unless a preferred-platform candidate is
    within `band` of the best."""
    if not cands:
        return None
    best = min(cands, key=lambda c: c["net_cost"])
    pref = [c for c in cands if c["platform"] == preferred_platform and c["net_cost"] <= best["net_cost"] * (1 + band)]
    return min(pref, key=lambda c: c["net_cost"]) if pref else best


def _goal_needs_gen_recharge(cfg, req, load, region):
    """True if the outage goal cannot be met at storm sun by battery+PV alone (largest practical bank)."""
    if not req.get("gen_allowed", True):
        return False
    units = _floor_units(cfg, "eg4-wallmount-powerpro-14.3", load, req.get("target_hours", 24)) + 3
    d = {"inverter": "solark-15k-2p-n", "battery": "eg4-wallmount-powerpro-14.3", "battery_units": units,
         "pv_kw_new": req.get("pv_kw_new", 0), "pv_kw_existing": req.get("pv_kw_existing", 0),
         "generator": None, "gen_allowed": False}
    return not simulate(cfg, d, load, region, "storm", req.get("outage_days", 7))["feasible"]


def _fuel_plan(cfg, design, region):
    ld = build_load(cfg, "bare_minimum")
    d = {**design, "gen_allowed": True}
    days = cfg.val("design_rules/fuel/autonomy_days_default")
    s = simulate(cfg, d, ld, region, "storm", days)
    can = cfg.val("design_rules/fuel/can_gal"); mn = cfg.val("design_rules/fuel/min_gal")
    plan = max(mn, math.ceil(s["total_gal"] * 1.1 / can) * can) if d.get("generator") else 0
    return {"basis": f"bare_minimum ({ld['kwh_day']} kWh/day) x {days} days at STORM sun (PSH {s['psh']})",
            "energy_kwh": round(ld["kwh_day"] * days, 1), "sim_gal": s["total_gal"],
            "plan_gal": plan, "cans": f"{plan // can} x {can}-gal cans" if plan else None,
            "propane_alt_lb": s.get("propane_lb"),
            "storage": "stabilizer; rotate fuel every 6-12 months"}


def design_system(req, cfg=None):
    cfg = _cfg(cfg)
    conflicts = cfg.scan_conflicts()
    if conflicts:
        raise ConflictBlocked(f"config has conflict values; refusing to publish: {conflicts}")
    region = resolve_region(cfg, req.get("address"), req.get("zip"), req.get("online", False))
    load = build_load(cfg, req.get("tier", "bare_minimum"), req.get("kwh_day"), req.get("peak_w"),
                      req.get("appliances"), req.get("adders"))
    band = cfg.val("policy/preferred_tie_band")
    needs_recharge = _goal_needs_gen_recharge(cfg, req, load, region)
    report, cands = [], []
    default_model = cfg.val("design_rules/inverter_select/default_model")
    models = SOLARK + ["tesla-powerwall-3"]
    if req.get("inverter") and req["inverter"] != "auto":
        models = [req["inverter"]]
    sized = {}
    for iid in models:
        inv = inverter(cfg, iid)
        if inv["platform"] == "tesla" and needs_recharge:
            report.append({"candidate": iid, "status": "rejected", "reasons": [
                f"cannot recharge battery from generator; {req.get('outage_days', 7)}-day goal at storm sun needs generator recharge"]})
            continue
        r = _size_platform(cfg, iid, req, load, region)
        sized[iid] = r
        entry = {"candidate": iid, "status": r["status"], "reasons": r.get("reasons", []) + r.get("notes", [])}
        if r["status"] == "candidate":
            c = cost_design(cfg, r["design"])
            f = _fin.model_financing(cfg, region, r["design"], c, r["row"]["usable_kwh"])
            verified_gs = sum(g["annual_income"] or 0 for g in f["grid_services"] if g["included_in_payback"]) * 5
            net = c["total_at_cost"] - f["incentives"]["total_incentives"] - verified_gs
            cands.append({"id": iid, "platform": inv["platform"], "net_cost": net})
            entry.update(net_cost_5yr=round(net, 0), cost_at_cost=c["total_at_cost"], battery_units=r["design"]["battery_units"])
            for g in f["grid_services"]:
                if g["status"] == "pending eligibility":
                    entry["reasons"].append(f"{g['program']}: pending eligibility, excluded from payback")
        report.append(entry)
    for p in RESEARCH_PLATFORMS:
        report.append({"candidate": p, "status": "needs_research", "reasons": ["required capability flags unknown"]})
    pick = None
    if cands:
        ids = [c["id"] for c in cands]
        if default_model in ids and not req.get("prefer_12k") and req.get("inverter", "auto") == "auto":
            pick = default_model; why = "owner default (15K: rapid recharge with oversized generator)"
            other = pick_with_tie_band([c for c in cands if c["platform"] != "sol-ark"] + [c for c in cands if c["id"] == pick], band)
            if other and other["platform"] != "sol-ark":
                pick = other["id"]; why = "lower net cost beyond Sol-Ark tie band"
        else:
            sol = [c for c in cands if c["id"] == "solark-12k-2p-n"] if req.get("prefer_12k") else []
            chosen = sol[0] if sol else pick_with_tie_band(cands, band)
            pick = chosen["id"]; why = "12K requested (<=9 kW / CLC eligibility)" if sol else "lowest net cost (Sol-Ark wins within tie band)"
        for e in report:
            if e["candidate"] == pick:
                e["status"] = "picked"; e["reasons"].insert(0, why)
            elif e["status"] == "candidate":
                e["status"] = "alternative"
    out = {"engine_version": ENGINE_VERSION, "config_version": cfg.version,
           "status": "preliminary", "region": {k: v for k, v in region.items() if k != "climate"},
           "climate": region["climate"],
           "load": {k: v for k, v in load.items() if k != "hourly_kw"},
           "goal": {"outage_days": req.get("outage_days", 7), "weather_case": "storm",
                    "gen_allowed": req.get("gen_allowed", True), "needs_generator_recharge": needs_recharge},
           "platform_report": report}
    if not pick:
        out["design"] = None
        out["message"] = "No feasible priced design; see platform_report"
    else:
        r = sized[pick]; d = r["design"]
        sim = simulate(cfg, d, load, region, "storm", req.get("outage_days", 7))
        avg = simulate(cfg, d, load, region, "average", req.get("outage_days", 7))
        c = cost_design(cfg, d)
        fin = _fin.model_financing(cfg, region, d, c, sim["usable_kwh"], req.get("finance_mode", "cash"))
        gen = generator(cfg, d.get("generator"))
        start = cfg.val("design_rules/battery/gen_start_soc")
        out.update(design=d, bom=c, simulation_storm=sim, simulation_average_info_only=avg,
                   battery_only_hours_avg_load=round(battery_only_hours(cfg, d, load), 1),
                   generator_operation=None if not gen else (
                       f"Automatic start at {int(start*100)}% battery." if gen["auto_start"] else
                       f"Manual-start portable: you start it when the battery reaches {int(start*100)}% "
                       f"(the inverter alerts you); it recharges to {int(cfg.val('design_rules/battery/gen_stop_soc')*100)}%."),
                   fuel_plan=_fuel_plan(cfg, d, region) if gen else None,
                   tradeoffs=r["tradeoffs"], finance=fin)
    out["confidence"] = {"region": "high" if region.get("pack_id") == "ma-clc" else "low" if region.get("state") else "none",
                         "tariff": region.get("tariff_confidence"), "climate": region["climate"]["confidence"],
                         "solar": "low (synthetic profile)", "prices": "street/owner values; see bom lines"}
    out["disclaimers"] = [cfg.val("policy/licensed_review_gate"),
                          "Preliminary estimate, not licensed engineering. Not a quote.",
                          "Solar output uses a SYNTHETIC hourly profile unless PVWatts is available.",
                          "Federal §25D credit expired after 2025-12-31; §48E for TPO is unverified."]
    out["attribution"] = "APS Open Microgrid Design Engine by Antifragile Power Systems (code Apache-2.0, data CC-BY-4.0)"
    out["handoff"] = {"label": "Get a firm quote / financing", "email": "hello@antifragilepower.com",
                      "consent_required": True, "consent_text": cfg.val("policy/consent_text"),
                      "consent_version": cfg.raw("policy/consent_text").get("version")}
    return out


def get_incentives(req, cfg=None):
    cfg = _cfg(cfg)
    region = resolve_region(cfg, req.get("address"), req.get("zip"))
    return _fin.get_incentives(cfg, region)


def model_financing(design, req, cfg=None):
    cfg = _cfg(cfg)
    region = resolve_region(cfg, req.get("address"), req.get("zip"))
    c = cost_design(cfg, design)
    usable = simulate(cfg, design, build_load(cfg), region, "storm", 1)["usable_kwh"]
    return _fin.model_financing(cfg, region, design, c, usable, req.get("finance_mode", "cash"))
