"""Catalog accessors with datasheet-derived limits."""

def inverter(cfg, iid):
    r = cfg.raw(f"catalog/inverters/{iid}")
    if r is None:
        raise KeyError(iid)
    g = lambda k: cfg.val(f"catalog/inverters/{iid}/{k}") if k in r else None
    cont = g("continuous_ac_w")
    batt = g("continuous_battery_w")
    if isinstance(cont, dict):
        batt = cont.get("battery_only", batt); cont = cont.get("with_pv")
    pv = g("pv_max_w")
    if isinstance(pv, dict):
        pv = pv.get("usable")
    platform = r.get("platform")
    flags = cfg.raw(f"catalog/platforms/{platform}/flags") or {}
    fl = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in flags.items()}
    tesla = platform == "tesla"
    return {"id": iid, "platform": platform, "name": g("name"),
            "continuous_ac_w": cont, "battery_side_w": batt or cont, "surge_w": g("surge_10s_w"),
            "pv_max_w": pv, "gen_port_max_w": g("gen_port_max_w") or 0,
            "max_ac_charge_w": g("max_ac_charge_w") or (g("max_charge_w") or 0),
            "gen_charges_battery": bool(fl.get("gen_charges_battery")) and not tesla,
            "gen_autostart": fl.get("gen_autostart"),
            "integrated_kwh": g("usable_kwh") if tesla else None,
            "max_units": g("max_units") if tesla else 1,
            "datasheet_url": r.get("datasheet_url")}


def battery(cfg, bid):
    r = cfg.raw(f"catalog/batteries/{bid}")
    kwh, meta = cfg.leaf(f"catalog/batteries/{bid}/kwh")
    uf = cfg.val(f"catalog/batteries/{bid}/usable_fraction", default=0.90) if "usable_fraction" in r else 0.90
    mc = cfg.val(f"catalog/batteries/{bid}/max_charge_w") if "max_charge_w" in r else kwh * 1000 * 0.5
    price, pm = cfg.leaf(f"catalog/batteries/{bid}/price_cost")
    return {"id": bid, "kwh": kwh, "usable_fraction": uf, "max_charge_w": mc, "price": price,
            "price_status": pm["status"]}


def generator(cfg, gid):
    if not gid:
        return None
    base = f"catalog/generators/{gid}"
    r = cfg.raw(base)
    g = lambda k: cfg.val(f"{base}/{k}") if k in r else None
    price = g("price_cost") or g("price_cost_installed")
    curve = g("fuel_curve_gph")
    return {"id": gid, "type": g("type"), "rated_kw": g("rated_kw") or 20.0, "max_kw": g("max_kw"),
            "auto_start": bool(g("auto_start")), "tank_gal": g("tank_gal"),
            "fuel_curve": {float(k): v for k, v in curve.items()} if curve else {0.5: 1.5, 0.75: 2.0, 1.0: 2.6},
            "price": price}


def fuel_gph(gen, load_frac):
    """Linear interpolation across 0.25/0.50/0.75/1.00 points (0.25 point = 0.65 x the 0.50 point)."""
    pts = dict(gen["fuel_curve"])
    pts.setdefault(0.25, pts[0.5] * 0.65)
    xs = sorted(pts)
    f = max(xs[0], min(1.0, load_frac))
    for a, b in zip(xs, xs[1:]):
        if a <= f <= b:
            return pts[a] + (pts[b] - pts[a]) * (f - a) / (b - a)
    return pts[xs[-1]]
