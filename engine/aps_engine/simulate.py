"""Hourly dispatch: PV -> load; surplus -> battery; deficit -> battery down to gen_start_soc;
then generator. Sol-Ark: gen carries load + capped charging until gen_stop_soc. Tesla PW3: gen
serves load only (no battery charging)."""
from .equipment import inverter, battery, generator, fuel_gph
from .solar import daily_profile
from .load import build_load

WEATHER = {"average": None, "storm": "storm_design", "blizzard": "blizzard", "overcast": "light_overcast"}


def psh_for(region, weather_case):
    c = region["climate"]
    if weather_case == "average":
        return c["psh_average"]
    return c["storm_psh"][WEATHER[weather_case]]


def simulate(cfg, design, load, region, weather_case="storm", outage_days=7, hourly=False):
    inv = inverter(cfg, design["inverter"])
    n_inv = design.get("n_inverters", 1)
    rules = lambda k: cfg.val(f"design_rules/battery/{k}")
    rte = rules("round_trip_eff"); eff = rte ** 0.5
    if inv["platform"] == "tesla":
        units = design.get("battery_units", 1)
        cap = inv["integrated_kwh"] * units
        max_ch = (cfg.val("catalog/inverters/tesla-powerwall-3/max_charge_w") or 5000) * units / 1000
        dis_cap = inv["battery_side_w"] * units / 1000
        pv_inv_cap = inv["pv_max_w"] * units / 1000
    else:
        b = battery(cfg, design["battery"])
        units = design["battery_units"]
        cap = b["kwh"] * b["usable_fraction"] * units
        max_ch = min(b["max_charge_w"] * units, inv["max_ac_charge_w"] * n_inv) / 1000
        dis_cap = inv["battery_side_w"] * n_inv / 1000
        pv_inv_cap = inv["pv_max_w"] * n_inv / 1000
    gen = generator(cfg, design.get("generator")) if design.get("gen_allowed", True) else None
    gen_start = rules("gen_start_soc"); gen_stop = rules("gen_stop_soc")
    soc = rules("outage_start_soc") * cap
    pv_kw = min(design.get("pv_kw_new", 0) + design.get("pv_kw_existing", 0), pv_inv_cap)
    psh = psh_for(region, weather_case)
    pv_day = daily_profile(pv_kw, psh)
    gen_avail = 0.0
    if gen:
        port = inv["gen_port_max_w"] * n_inv / 1000 if inv["platform"] != "tesla" else 1e9
        gen_avail = min(gen["rated_kw"], port)
    gen_on = False
    rows, gen_h, fuel, unserved = [], [0] * outage_days, [0.0] * outage_days, 0.0
    gen_kwh = 0.0
    free_run = longest_free = 0
    charges = inv["gen_charges_battery"]
    floor = gen_start * cap if gen else 0.0
    for t in range(24 * outage_days):
        h = t % 24; d = t // 24
        L = load["hourly_kw"][h]; P = pv_day[h]
        net = P - L
        g_out = 0.0
        ch_used = 0.0
        if net >= 0:
            ch_used = min(net, max_ch, max(0.0, cap - soc) / eff)
            soc += ch_used * eff
            need = 0.0
        else:
            need = -net
            if not gen_on:
                can = min(need, dis_cap, max(0.0, soc - floor) * eff)
                soc -= can / eff; need -= can
                if gen and need > 1e-9:
                    gen_on = True  # manual portable: owner starts it at gen_start_soc
        if gen_on:
            serve = min(need, gen_avail); need -= serve; g_out = serve
            if charges:
                room = max(0.0, gen_stop * cap - soc) / eff
                chg = max(0.0, min(gen_avail - serve, max_ch - ch_used, room))
                soc += chg * eff; g_out += chg
            if need > 1e-9:  # generator saturated: battery may dip below start SOC
                extra = min(need, max(0.0, soc) * eff, dis_cap)
                soc -= extra / eff; need -= extra
        unserved += max(0.0, need)
        if g_out > 0:
            gen_h[d] += 1
            fuel[d] += fuel_gph(gen, g_out / gen["rated_kw"])
            gen_kwh += g_out
            free_run = 0
        else:
            free_run += 1; longest_free = max(longest_free, free_run)
        if gen_on:
            if charges and soc >= gen_stop * cap - 1e-6:
                gen_on = False
            if not charges and net >= 0:
                gen_on = False
        if hourly:
            rows.append({"h": t, "pv_kw": round(P, 3), "load_kw": round(L, 3), "soc_kwh": round(soc, 2),
                         "gen_kw": round(g_out, 2)})
    total = sum(fuel)
    hours = 24 * outage_days
    out = {"weather_case": weather_case, "psh": psh, "outage_days": outage_days,
           "usable_kwh": round(cap, 2), "gen_hrs_per_day": [int(x) for x in gen_h],
           "avg_gen_hrs_per_day": round(sum(gen_h) / outage_days, 2),
           "fuel_gal_per_day": [round(x, 2) for x in fuel], "total_gal": round(total, 2),
           "gen_kwh": round(gen_kwh, 1),
           "gen_free_hours": hours - sum(gen_h), "longest_gen_free_stretch_h": longest_free, "resilience_hours": longest_free, "resilience_metric": "longest battery+solar stretch with no generator (h); total gen-free hours is NOT monotonic because each gen run recharges to 90%",
           "unserved_kwh": round(unserved, 2), "feasible": unserved < 0.01,
           "gen_effective_kw": round(gen_avail, 2) if gen else 0,
           "solar_note": "SYNTHETIC hourly PV profile scaled to PSH (PVWatts TMY used only when keyed/online)"}
    if gen and "propane_lbph_75" in (cfg.raw(f"catalog/generators/{gen['id']}") or {}):
        out["propane_lb"] = round(cfg.val(f"catalog/generators/{gen['id']}/propane_lbph_75") * sum(gen_h), 1)
    if hourly:
        out["hourly"] = rows
    return out


def battery_only_hours(cfg, design, load):
    """Hours the battery alone carries the AVERAGE load (F-1: never peak watts)."""
    b = battery(cfg, design["battery"])
    usable = b["kwh"] * b["usable_fraction"] * design["battery_units"]
    rte = cfg.val("design_rules/battery/round_trip_eff")
    return usable * rte ** 0.5 / load["avg_kw"]
