"""Finance: cash / loan / lease-TPO. Payback only when tariff confidence >= medium; grid-services
income only for approved (verified) programs AND verified-eligible equipment."""
from .equipment import inverter, battery
from .solar import annual_kwh

CONF_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def grid_services(cfg, design, region, usable_kwh):
    out = []
    inv = inverter(cfg, design["inverter"])
    n = design.get("battery_units", 1) if inv["platform"] == "tesla" else design.get("n_inverters", 1)
    for pid in region.get("grid_services", []):
        base = f"grid_services/programs/{pid}"
        rate, rm = cfg.leaf(f"{base}/rate")
        hrs = cfg.val(f"{base}/event_hours", default=3) if "event_hours" in cfg.raw(base) else 3
        elig_tbl = cfg.val(f"{base}/eligible_equipment") if "eligible_equipment" in cfg.raw(base) else {}
        elig = (elig_tbl or {}).get(design["inverter"], "unknown")
        paid_kw = min(inv["battery_side_w"] / 1000 * n, usable_kwh / hrs)  # A03 F1 capped formula
        income = None if rate is None else round(paid_kw * rate, 0)
        approved = rm["status"] == "verified"
        status = ("included" if (approved and elig is True) else
                  "pending eligibility" if elig == "pending_eligibility" else
                  "estimate, not approved" if not approved else "eligibility unknown")
        out.append({"program": pid, "name": cfg.raw(base).get("name"), "paid_kw": round(paid_kw, 2),
                    "rate": rate, "annual_income": income, "status": status,
                    "included_in_payback": status == "included",
                    "lock_in_years": cfg.val(f"{base}/lock_in_years", default=5) if "lock_in_years" in cfg.raw(base) else None,
                    "confidence": "high" if status == "included" else "low", "basis": rm["status"]})
    for g in region.get("baseline_grid_services", []):  # national baseline utility DR programs
        paid_kw = min(inv["battery_side_w"] / 1000 * n, usable_kwh / g["event_hours"])
        inc = g["counted_in_base_case"] and g["status"] == "verified"
        out.append({"program": g["id"], "name": g["name"], "paid_kw": round(paid_kw, 2), "rate": g["rate_per_kw_yr"],
                    "annual_income": round(paid_kw * g["rate_per_kw_yr"], 0), "status": "included" if inc else "estimate, not approved",
                    "included_in_payback": inc, "lock_in_years": g.get("lock_in_years"), "confidence": g["confidence"],
                    "basis": g["status"], "source": g["source"], "verified_on": g.get("verified_on"), "conditions": g.get("conditions")})
    return out


def _cost_of(cost, applies_to):
    pref = {"pv": ("New solar",), "storage": ("Battery", "Tesla")}[applies_to]
    return sum(l["total"] or 0 for l in (cost or {}).get("lines", []) if l["item"].startswith(pref))


def _baseline_incentives(entries, design, cost):
    """Apply national-baseline incentive entries; only counted (fresh, entitlement-like) entries add to total."""
    out, total = [], 0.0
    pv = (design or {}).get("pv_kw_new", 0) or 0
    storage = (design or {}).get("battery_units", 0) or 0
    for e in entries:
        amt = 0.0
        applies = (pv >= e.get("min_pv_kw", 0.001)) if e["applies_to"] == "pv" else storage > 0
        if design and applies:
            if e["kind"] == "rebate_flat":
                amt = e["amount"]
            elif e["kind"] == "state_tax_credit_pct":
                amt = min(e["pct"] * _cost_of(cost, e["applies_to"]), e["cap"])
            elif e["kind"] == "rebate_per_kwh":
                amt = 0.0  # never counted (program-limited)
        counted = e["counted_in_base_case"] and applies and amt > 0
        if counted:
            total += amt
        out.append({"id": e["id"], "name": e["name"], "kind": e["kind"], "amount": round(amt, 0) if counted else 0,
                    "potential_amount": round(amt, 0) if amt else None, "counted_in_base_case": counted,
                    "basis": e["basis"], "confidence": e["confidence"], "source": e["source"],
                    "verified_on": e.get("verified_on"), "expires": e.get("expires"), "expired": e.get("expired"),
                    "conditions": e.get("conditions"), "program_status": e.get("program_status")})
    return out, total


def get_incentives(cfg, region, design=None, cost=None):
    inc = dict(region.get("incentives") or {})
    amt = 0.0
    if region.get("baseline"):
        items, amt = _baseline_incentives(inc.pop("baseline", []), design, cost)
        inc["programs"] = items
        return {"incentives": inc, "total_incentives": round(amt, 0), "basis": "auto_sourced + per-item basis",
                "note": "Only entitlement-like, unexpired items count; property/sales-tax exemptions and waitlisted programs are info-only."}
    if design and cost and "ma_state_credit" in inc and design.get("pv_kw_new", 0) > 0:
        pv_cost = sum(l["total"] or 0 for l in cost["lines"] if l["item"].startswith("New solar"))
        c = inc["ma_state_credit"]
        amt = min(c["pct"] * pv_cost, c["cap"])
        inc["ma_state_credit"] = {**c, "amount": round(amt, 0), "applies_to": "new solar cost"}
    return {"incentives": inc, "total_incentives": round(amt, 0)}


def model_financing(cfg, region, design, cost, usable_kwh, mode="cash", loan_apr=0.0799, loan_years=10,
                    discount=0.06, years=25, online=False):
    conf = region.get("tariff_confidence", "none")
    gs = grid_services(cfg, design, region, usable_kwh)
    inc = get_incentives(cfg, region, design, cost)
    res = {"mode": mode, "tariff_confidence": conf, "grid_services": gs, "incentives": inc,
           "lease_tpo": {"available": "quote required", "note": "§48E eligibility for third-party-owned storage is UNVERIFIED and never promised"}}
    if cost["total_at_cost"] is None:
        res.update(finance_available=False, reason=f"missing prices: {cost['missing_prices']}")
        return res
    net = cost["total_at_cost"] - inc["total_incentives"]
    res["net_cost"] = round(net, 0)
    min_conf = CONF_RANK["low"] if region.get("baseline") else CONF_RANK["medium"]
    if CONF_RANK.get(conf, 0) < min_conf:
        res.update(finance_available=False, payback_years=None, npv=None,
                   reason="finance not available for this region (tariff confidence below medium)")
        return res
    rate = region["tariff"]["rate_per_kwh"]; esc = region["tariff"]["escalation"]
    deg = cfg.val("regions/climate_defaults/degradation_per_yr", default=0.005)
    kwh, kmeta = annual_kwh(design.get("pv_kw_new", 0), region["climate"]["psh_average"],
                         lat=region.get("lat"), lon=region.get("lon"), online=online or region.get("online", False))
    exp = region["tariff"].get("export_credit") if region.get("baseline") else None
    if isinstance(exp, dict) and exp.get("export_policy") == "value_of_solar":
        solar_val = kwh * exp["vos_per_kwh"]; solar_method = f"all production credited at value-of-solar ${exp['vos_per_kwh']}/kWh"
    elif isinstance(exp, dict):
        sc = cfg.val("regions/climate_defaults/self_consumption", default=None) or 0.5
        ratio = exp.get("export_ratio_of_retail", 0.0)
        solar_val = kwh * rate * (sc + (1 - sc) * ratio)
        solar_method = f"{int(sc*100)}% self-consumed at retail, rest exported at {ratio:.0%} of retail ({exp.get('export_policy')})"
    else:
        solar_val = kwh * rate  # NEM export credited ~retail (C19) -> self-consumption ~= export
        solar_method = "net metering at retail (curated pack)"
    gs_inc = sum(g["annual_income"] or 0 for g in gs if g["included_in_payback"])
    lock = max([g["lock_in_years"] or 5 for g in gs if g["included_in_payback"]] or [0])
    yr1 = solar_val + gs_inc
    res["solar_value_method"] = solar_method
    res["labels"] = _labels(region, gs, inc)
    res.update(finance_available=True, solar_new_kwh_yr1=round(kwh, 0), solar_source=kmeta,
               annual_value_yr1=round(yr1, 0), grid_services_income_included=gs_inc)
    if yr1 <= 0:
        res.update(payback_years=None, npv=round(-net, 0), reason="resilience-only design: no bill savings or approved grid-services income")
    else:
        cum, pb, npv = -net, None, -net
        for y in range(1, years + 1):
            v = solar_val * (1 + esc) ** (y - 1) * (1 - deg) ** (y - 1) + (gs_inc if y <= lock else 0)
            prev = cum; cum += v; npv += v / (1 + discount) ** y
            if pb is None and cum >= 0:
                pb = round(y - 1 + (-prev) / v, 1)
        res.update(payback_years=pb, npv=round(npv, 0), payback_note=None if pb else f"> {years} yr")
    if mode == "loan":
        r = loan_apr / 12; n = loan_years * 12
        pmt = net * r / (1 - (1 + r) ** -n) if r else net / n
        res["loan"] = {"apr": loan_apr, "years": loan_years, "monthly_payment": round(pmt, 0),
                       "yr1_net_cash_flow": round(yr1 - 12 * pmt, 0), "note": "illustrative terms; lender quote required"}
    return res


def _labels(region, gs, inc):
    """Provenance of every financial input: verified (curated/primary source) vs auto_sourced (baseline)."""
    if not region.get("baseline"):
        return {"tariff_rate": "verified" if region.get("tariff_confidence") == "high" else "auto_sourced",
                "escalation": "verified", "export_credit": "verified", "incentives": "verified",
                "grid_services": {g["program"]: g.get("basis") for g in gs}, "pack": "curated MA pack"}
    t = region["tariff"]
    return {"tariff_rate": {"basis": t["rate_meta"]["basis"], "confidence": t["rate_meta"]["confidence"], "source": t["rate_meta"]["source"]},
            "escalation": {"basis": "auto_sourced", "confidence": t["escalation_meta"]["confidence"], "source": t["escalation_meta"]["source"]},
            "export_credit": {"basis": t["export_credit"].get("basis"), "confidence": t["export_credit"].get("confidence"),
                              "source": t["export_credit"].get("source"), "policy": t["export_credit"].get("export_policy")},
            "incentives": {p["id"]: p["basis"] for p in inc["incentives"].get("programs", [])},
            "grid_services": {g["program"]: g.get("basis") for g in gs},
            "federal": {"25D": "verified ($0, ended 2025-12-31)", "48E_tpo": "unverified, not counted"},
            "pack": "national baseline (auto-sourced)"}
