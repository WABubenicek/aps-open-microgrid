"""National baseline (non-MA): utility by ZIP, residential rate, export policy, incentives, escalation.
Free sources only, bundled as compact data files (see tools/ and data/):
- utility by ZIP: NREL/OpenEI 'Utility Companies and Rates: Look-up by Zipcode (2023)'
- residential $/kWh: EIA-861 2024 (revenue/sales, bundled); escalation = state CAGR 2019->2024 (clamped)
- export policy + incentives: curated state_policy.json (each entry has source, dates, confidence, status)
- optional online: OpenEI URDB default residential tariff (reference only) with the NLR/NREL key.
Every number carries basis 'verified' or 'auto_sourced'."""
import os, json, datetime, urllib.request, urllib.parse
from functools import lru_cache

_D = os.path.join(os.path.dirname(__file__), "data")


@lru_cache(maxsize=None)
def _load(name):
    with open(os.path.join(_D, name)) as f:
        return json.load(f)


def eia():
    return _load("eia861_residential.json")


def policy():
    return _load("state_policy.json")


def _today():
    return datetime.date.fromisoformat(os.environ.get("APS_TODAY") or datetime.date.today().isoformat())


def fresh(entry):
    """Entries expire expire_after_days after verified_on (or compiled_on)."""
    d = entry.get("verified_on") or entry.get("compiled_on")
    if not d:
        return False
    return (_today() - datetime.date.fromisoformat(d)).days <= policy()["expire_after_days"]


def _expires(entry):
    d = entry.get("verified_on") or entry.get("compiled_on")
    return (datetime.date.fromisoformat(d) + datetime.timedelta(days=policy()["expire_after_days"])).isoformat() if d else None


def utility_for_zip(z, state=None, eiaid=None):
    """Pick the likely utility for a ZIP. Preference: explicit eiaid, then the candidate with most residential
    customers (EIA-861 2024). Returns None when the ZIP is not in the table."""
    zt = _load("zip_utilities.json")
    cands = zt["zips"].get(z, [])
    if eiaid:
        cands = [str(eiaid)] + [c for c in cands if c != str(eiaid)]
    if not cands:
        return None
    ut, e = zt["utilities"], eia()["utilities"]

    def info(c):
        u = ut.get(c, [None, state, None, None, None])
        st = u[1] or state
        row = e.get(f"{c}-{st}")
        return {"eiaid": c, "name": (row or u)[0], "state": st, "ownership": u[2],
                "service_type": u[4], "res_customers": row[3] if row else 0,
                "res_rate_eia2024": row[1] if row else None, "res_rate_2023": u[3] or None}
    infos = [info(c) for c in cands]
    pick = infos[0] if eiaid else max(infos, key=lambda i: i["res_customers"] or 0)
    return {**pick, "alternatives": [{"eiaid": i["eiaid"], "name": i["name"]} for i in infos if i is not pick],
            "source": _load("zip_utilities.json")["source_url"], "confidence": "medium" if len(infos) == 1 else "low"}


def escalation(state):
    p = policy(); lo, hi = p["escalation_clamp"]
    s = eia()["states"].get(state or "")
    if s and s.get("escalation") is not None:
        raw = s["escalation"]; val = min(max(raw, lo), hi)
        note = f"EIA-861 state residential price CAGR 2019-2024 = {raw:.1%}" + (f", clamped to {val:.0%} for 25-yr projection" if val != raw else "")
        return {"value": val, "raw_cagr": raw, "source": note, "basis": "auto_sourced", "confidence": "low"}
    return {"value": p["escalation_default"], "source": "default 3%/yr (no EIA state series)", "basis": "auto_sourced", "confidence": "low"}


def tariff(util, state):
    if util and util.get("res_rate_eia2024"):
        return {"rate_per_kwh": util["res_rate_eia2024"], "source": f"EIA-861 2024 residential average (revenue/sales), {util['name']}",
                "basis": "auto_sourced", "confidence": "medium"}
    if util and util.get("res_rate_2023"):
        return {"rate_per_kwh": util["res_rate_2023"], "source": f"NREL/OpenEI 2023 utility average, {util['name']}",
                "basis": "auto_sourced", "confidence": "medium"}
    s = eia()["states"].get(state or "")
    if s:
        return {"rate_per_kwh": s["rate"], "source": f"EIA-861 2024 {state} state residential average (utility rate unavailable; retail-choice or unmatched)",
                "basis": "auto_sourced", "confidence": "low"}
    return None


def export_policy(util, state):
    p = policy()
    o = p["utility_overrides"].get((util or {}).get("eiaid") or "")
    if o and fresh(o):
        return {**o, "basis": o["status"], "expires": _expires(o), "level": "utility"}
    s = p["net_metering"].get(state or "")
    if s:
        return {**s, "basis": s["status"], "expires": _expires(s), "level": "state",
                **({} if fresh(s) else {"confidence": "none", "note": s["note"] + " (EXPIRED: re-verify)"})}
    return {"export_policy": "unknown", "export_ratio_of_retail": 0.0, "basis": "auto_sourced", "confidence": "none",
            "note": "no export policy data; exports valued at $0"}


def incentives_for(util, state):
    out = []
    for i in policy()["incentives"]:
        if i["state"] != state or (i.get("utility_eiaid") and i["utility_eiaid"] != (util or {}).get("eiaid")):
            continue
        ok = fresh(i)
        out.append({**i, "basis": i["status"], "expires": _expires(i), "expired": not ok,
                    "counted_in_base_case": i["counted_in_base_case"] and ok})
    return out


def grid_programs_for(util, state):
    return [g for g in policy()["grid_services"]
            if g["state"] == state and g.get("utility_eiaid") in (None, (util or {}).get("eiaid")) and fresh(g)]


def federal():
    return policy()["federal"]


@lru_cache(maxsize=512)
def urdb_default_tariff(eiaid):
    """Reference only: OpenEI URDB default residential tariff for a utility (needs NLR/NREL key). None offline."""
    key = os.environ.get("NLR_API_KEY")
    if not key or not eiaid:
        return None
    q = urllib.parse.urlencode({"version": 8, "format": "json", "api_key": key, "eia": eiaid, "sector": "Residential",
                                "is_default": "true", "approved": "true", "detail": "minimal", "limit": 20, "orderby": "startdate", "direction": "desc"})
    try:
        with urllib.request.urlopen("https://api.openei.org/utility_rates?" + q, timeout=10) as r:
            items = json.load(r).get("items", [])
    except Exception:
        return None
    items = [i for i in items if not i.get("enddate")] or items
    if not items:
        return None
    i = items[0]
    return {"name": i.get("name"), "uri": i.get("uri"), "utility": i.get("utility"),
            "startdate": datetime.datetime.utcfromtimestamp(i["startdate"]).date().isoformat() if i.get("startdate") else None,
            "source": "OpenEI U.S. Utility Rate Database (reference; finance uses EIA-861 all-in average)", "basis": "auto_sourced"}
