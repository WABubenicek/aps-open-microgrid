"""Equipment at cost (0% markup) + posted fees. Same payload -> same price on every surface."""
from .equipment import inverter, battery, generator


def _line(item, qty, unit, status, source):
    tot = None if unit is None else round(qty * unit, 2)
    return {"item": item, "qty": qty, "unit_cost": unit, "total": tot,
            "confidence": {"verified": "high"}.get(status, "low" if unit is not None else "none"),
            "status": status, "source": source}


def cost_design(cfg, design):
    L = []
    iid = design["inverter"]; inv = inverter(cfg, iid); n = design.get("n_inverters", 1)
    if inv["platform"] == "tesla":
        p, m = cfg.leaf(f"catalog/inverters/{iid}/price_cost")
        L.append(_line(inv["name"], design.get("battery_units", 1), p, m["status"] if p else "unknown",
                       m["source"] or "NEEDS RESEARCH"))
    else:
        key = "solark-12k-dual" if (iid == "solark-12k-2p-n" and n == 2) else iid
        p, m = cfg.leaf(f"prices/inverter_cost/{key}")
        L.append(_line(inv["name"] + (" x2" if n == 2 else ""), 1 if key.endswith("dual") else n, p, m["status"], m["source"]))
        b = battery(cfg, design["battery"])
        L.append(_line(f"Battery {b['id']} ({b['kwh']} kWh)", design["battery_units"], b["price"], b["price_status"],
                       cfg.raw(f"catalog/batteries/{b['id']}/price_cost").get("source")))
    if design.get("pv_kw_new", 0) > 0:
        p, m = cfg.leaf("prices/solar_installed_per_kw")
        L.append(_line("New solar (installed, per kW)", design["pv_kw_new"], p, m["status"], m["source"]))
    if design.get("generator") and design.get("gen_allowed", True) and design.get("include_generator_cost", True):
        g = generator(cfg, design["generator"]); gid = design["generator"]
        node = cfg.raw(f"catalog/generators/{gid}")
        pk = "price_cost" if "price_cost" in node else "price_cost_installed"
        p, m = cfg.leaf(f"catalog/generators/{gid}/{pk}")
        L.append(_line(f"Generator {gid}", 1, p, m["status"], m["source"]))
    units = design.get("battery_units", 1)
    tier = "small" if units <= 2 else "medium" if units <= 4 else "large"
    bos, m = cfg.leaf("prices/bos")
    L.append(_line(f"BOS ({tier})", 1, bos[tier], m["status"], m["source"]))
    for k, path in [("Permit (AHJ)", "prices/permit"), ("Permit-ready package", "fees/permit_ready_package"),
                    ("Remote commissioning", "fees/remote_commissioning"), ("Design fee", "fees/design_fee")]:
        v, m = cfg.leaf(path)
        L.append(_line(k, 1, v, m["status"], m["source"]))
    missing = [l["item"] for l in L if l["total"] is None]
    total = None if missing else round(sum(l["total"] for l in L), 2)
    return {"lines": L, "total_at_cost": total, "missing_prices": missing,
            "excluded": ["Turnkey install labor (fee schedule TBD, N5)", "Interconnection fees (separate line)"],
            "markup": cfg.val("fees/equipment_markup")}
