"""Two-load model: energy (kWh/day -> avg kW) and diversified peak W. Peak is never a 24/7 load."""
# Default residential shape (fraction of daily kWh per hour, evening peak). Sums to 1.
_SHAPE = [0.030, 0.027, 0.026, 0.026, 0.027, 0.032, 0.040, 0.045, 0.042, 0.038, 0.036, 0.036,
          0.037, 0.037, 0.038, 0.041, 0.047, 0.056, 0.062, 0.062, 0.058, 0.052, 0.045, 0.038]
_s = sum(_SHAPE)
SHAPE = [x / _s for x in _SHAPE]
DUTY = {"critical": "critical", "essential": "essential", "whole_home": "whole_home"}


def build_load(cfg, tier="bare_minimum", kwh_day=None, peak_w=None, appliances=None,
               adders=None, profile=None):
    tiers = cfg.raw("design_rules/load_tiers")
    app_tbl = cfg.val("design_rules/appliances")
    if tier == "bare_minimum":
        base = cfg.val("design_rules/load_tiers/bare_minimum/kwh_day")
        add_tbl = cfg.val("design_rules/load_tiers/bare_minimum/adders_kwh_day")
        k = base + sum(add_tbl.get(a, 0) for a in (adders or []))
        names = ["lights", "fridge", "wifi_tv"] + [a for a in (adders or []) if a in app_tbl]
        p = sum(app_tbl[n][0] for n in names if n in app_tbl)
        if kwh_day is not None:
            k = min(k, kwh_day)  # spec 3.5: lower wins
        src = "owner default 6.5 kWh/day (+adders)"
    elif tier == "emergency":
        k = cfg.val("design_rules/load_tiers/emergency/kwh_day"); p = 800 * 1.0; src = "0.8 kW continuous"
    else:
        duty = cfg.val(f"design_rules/load_tiers/{tier}/duty_factor")
        names = appliances or ["lights", "fridge", "wifi_tv"]
        bundle_k = sum(app_tbl[n][1] for n in names)
        bundle_p = sum(app_tbl[n][0] for n in names)
        k = kwh_day if kwh_day is not None else bundle_k
        p = bundle_p * duty if peak_w is None else peak_w
        src = f"{tier}: bundle kWh, peak x duty {duty}"
    if peak_w is not None:
        p = peak_w
    shape = profile or SHAPE
    tot = sum(shape)
    hourly = [k * x / tot for x in shape]
    return {"tier": tier, "kwh_day": round(k, 3), "avg_kw": k / 24, "peak_w": p,
            "hourly_kw": hourly, "source": src}
