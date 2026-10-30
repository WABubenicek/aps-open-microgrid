"""Build engine/aps_engine/data/eia861_residential.json from EIA-861 (public domain).
Download: https://www.eia.gov/electricity/data/eia861/zip/f8612024.zip and .../archive/zip/f8612019.zip,
unzip Sales_Ult_Cust_<year>.xlsx here, then: python tools/build_eia861.py  (needs pandas, openpyxl)."""
import json, sys, pandas as pd
OUT = "engine/aps_engine/data/eia861_residential.json"
NEW, OLD = 2024, 2019

def load(y):
    d = pd.read_excel(f"Sales_Ult_Cust_{y}.xlsx", header=None, skiprows=3)
    off = 1 if y <= 2019 else 0  # 2019 file has an extra 'Short Form' column
    d = d.iloc[:, list(range(9)) + [9 + off, 10 + off, 11 + off]]
    d.columns = ["yr", "id", "name", "part", "stype", "dtype", "st", "own", "ba", "rev", "mwh", "cust"]
    d = d[pd.to_numeric(d.id, errors="coerce").notna()]
    for c in ["rev", "mwh", "cust"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    return d

def state_rates(d):
    o = {}
    for s, g in d.groupby("st"):
        mwh = g[g.stype != "Delivery"].mwh.sum()  # avoid double-counting delivery-only kWh
        if mwh > 0:
            o[s] = float(g.rev.sum() / mwh)
    return o

a, b = load(NEW), load(OLD)
sa, sb = state_rates(a), state_rates(b)
states = {s: {"rate": round(sa[s], 4), f"rate_{OLD}": round(sb[s], 4) if s in sb else None,
              "escalation": round((sa[s] / sb[s]) ** (1 / (NEW - OLD)) - 1, 4) if sb.get(s) else None} for s in sa}
ut = {}
for (i, s), g in a.groupby(["id", "st"]):
    bund = g[g.stype == "Bundled"]
    if bund.mwh.sum() > 0 and bund.cust.sum() > 0:
        ut[f"{int(i)}-{s}"] = [g.name.iloc[0], round(float(bund.rev.sum() / bund.mwh.sum()), 4), g.own.iloc[0], int(bund.cust.sum())]
json.dump({"source": f"EIA Form 861 ({NEW} final, Sales_Ult_Cust): residential revenue/sales, bundled service. "
                     f"Escalation = state residential price CAGR {OLD}->{NEW} (EIA-861 {OLD}).",
           "source_url": "https://www.eia.gov/electricity/data/eia861/", "data_year": NEW, "retrieved": sys.argv[1] if len(sys.argv) > 1 else None,
           "fields_utility": ["name", "res_rate_per_kwh", "ownership", "res_customers"], "states": states, "utilities": ut},
          open(OUT, "w"), separators=(",", ":"), sort_keys=True)
print(len(ut), "utilities;", {k: states[k] for k in ("TX", "CA", "FL", "MA")})
