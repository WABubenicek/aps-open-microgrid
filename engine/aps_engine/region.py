"""Region resolution. ZIP parsing ignores house numbers. Offline fallback: ZIP3 -> state table,
curated MA overrides; national baseline packs (URDB/HIFLD) are only used when online + keyed."""
import re, json, urllib.request
from functools import lru_cache


@lru_cache(maxsize=1024)
def geocode_zip(z):
    """ZIP -> (lat, lon) centroid via api.zippopotam.us (no key, no PII sent beyond the ZIP). None on failure."""
    try:
        with urllib.request.urlopen(f"https://api.zippopotam.us/us/{z}", timeout=8) as r:
            p = json.load(r)["places"][0]
        return float(p["latitude"]), float(p["longitude"])
    except Exception:
        return None

# ZIP3 prefix ranges -> state (USPS allocation, inclusive)
_ZIP3 = [(5,5,"NY"),(6,9,"PR"),(10,27,"MA"),(28,29,"RI"),(30,38,"NH"),(39,49,"ME"),(50,59,"VT"),
 (60,69,"CT"),(70,89,"NJ"),(100,149,"NY"),(150,196,"PA"),(197,199,"DE"),(200,205,"DC"),(206,219,"MD"),
 (220,246,"VA"),(247,268,"WV"),(270,289,"NC"),(290,299,"SC"),(300,319,"GA"),(320,349,"FL"),(350,369,"AL"),
 (370,385,"TN"),(386,397,"MS"),(398,399,"GA"),(400,427,"KY"),(430,459,"OH"),(460,479,"IN"),(480,499,"MI"),
 (500,528,"IA"),(530,549,"WI"),(550,567,"MN"),(570,577,"SD"),(580,588,"ND"),(590,599,"MT"),(600,629,"IL"),
 (630,658,"MO"),(660,679,"KS"),(680,693,"NE"),(700,714,"LA"),(716,729,"AR"),(730,749,"OK"),(750,799,"TX"),
 (800,816,"CO"),(820,831,"WY"),(832,838,"ID"),(840,847,"UT"),(850,865,"AZ"),(870,884,"NM"),(889,898,"NV"),
 (900,961,"CA"),(967,968,"HI"),(970,979,"OR"),(980,994,"WA"),(995,999,"AK")]

STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA PR RI SC SD TN TX UT VT VA WA WV WI WY".split())


def parse_zip(address=None, zip_field=None):
    """Explicit zip field wins; else the LAST 5-digit/ZIP+4 token that follows a 2-letter state
    (or ends the string). A leading house number is never a ZIP."""
    if zip_field:
        m = re.fullmatch(r"\s*(\d{5})(?:-\d{4})?\s*", str(zip_field))
        if m:
            return m.group(1)
    if not address or not address.strip():
        return None
    a = address.upper()
    hits = re.findall(r"\b([A-Z]{2})[\s,]+(\d{5})(?:-\d{4})?\b", a)
    hits = [z for st, z in hits if st in STATES]
    if hits:
        return hits[-1]
    tokens = re.findall(r"\b\d{5}(?:-\d{4})?\b", a)
    # accept a trailing token only if it is not the first token of the address (house number)
    if tokens:
        last = tokens[-1]
        if not re.match(r"^\s*" + re.escape(last), a) and a.rstrip().endswith(last):
            return last[:5]
    return None


def state_for_zip(z):
    p = int(z[:3])
    for lo, hi, st in _ZIP3:
        if lo <= p <= hi:
            return st
    return None


def _in_clc(z, cfg):
    n = int(z)
    excl = {"02538", "02558", "02571", "02576", "02554", "02564", "02584"}
    return 2532 <= n <= 2675 and z not in excl


NANTUCKET = {"02554", "02564", "02584"}
TURNKEY_ZIP3 = {"025", "026", "027"}  # Cape, Islands, SouthCoast (New Bedford/Fall River 027)


def _conf(meta):
    st = meta.get("status")
    return {"verified": "high", "auto_sourced": "medium", "unverified": "low"}.get(st, "none")


def resolve_region(cfg, address=None, zip_field=None, online=False):
    z = parse_zip(address, zip_field)
    if not z:
        return {"zip": None, "state": None, "pack_id": None, "status": "unknown",
                "message": "Region unknown: enter a ZIP code", "tariff": None,
                "tariff_confidence": "none", "grid_services": [], "incentives": {}, "climate": _climate(cfg, None)}
    st = state_for_zip(z)
    reg = {"zip": z, "state": st, "status": "resolved", "online": online}
    if online:
        ll = geocode_zip(z)
        if ll:
            reg["lat"], reg["lon"] = ll
    if st == "MA":
        pack = "ma-clc" if _in_clc(z, cfg) else "ma-other"
        root = cfg.raw(f"regions/overrides/{pack}")
        rate, rmeta = cfg.leaf("retail_tariff/rate_per_kwh", root)
        esc, _ = cfg.leaf("retail_tariff/escalation", root)
        exp, _ = cfg.leaf("net_metering/export_credit_per_kwh", root)
        reg.update(pack_id=pack, utility="cape-light-compact" if pack == "ma-clc" else "ma-utility (unresolved offline)",
                   tariff={"rate_per_kwh": rate, "escalation": esc, "export_credit": exp, "source": rmeta["source"]},
                   tariff_confidence=_conf(rmeta), grid_services=list(root.get("grid_services", [])),
                   incentives=_incentives(cfg, root), climate=_climate(cfg, root))
    else:
        # Offline: no URDB/HIFLD -> baseline pack stub, tariff unknown -> finance hidden.
        reg.update(pack_id=f"baseline-{(st or 'xx').lower()}", utility=None, tariff=None,
                   tariff_confidence="none", grid_services=[], incentives={},
                   climate=_climate(cfg, None),
                   message="No curated pack; national data layer offline -> resilience only, finance not available for this region")
    area = cfg.val("fees/turnkey_service_area")
    reg["turnkey_service_area"] = z[:3] in TURNKEY_ZIP3
    reg["turnkey_area_text"] = area
    reg["nantucket"] = z in NANTUCKET
    return reg


def _incentives(cfg, root):
    out = {}
    v, m = cfg.leaf("incentives/ma_state_credit", root)
    if m["status"] == "verified":
        out["ma_state_credit"] = {**v, "confidence": "high", "source": m["source"]}
    v, m = cfg.leaf("incentives/smart", root)
    out["smart"] = {"enabled": False, "reason": "disabled until verified (C20)"}
    out["federal_25d"] = {"enabled": False, "reason": cfg.val("regions/_federal/25D")}
    return out


def _climate(cfg, root):
    if root and isinstance(root.get("climate"), dict) and "psh_annual" in root["climate"]:
        c = root["climate"]
        return {"psh_average": c["psh_annual"]["value"], "storm_psh": c["storm_psh"]["value"],
                "psh_monthly": c["psh_monthly"]["value"], "confidence": "low", "source": "pack climate (E table)"}
    storm = cfg.val("regions/climate_defaults/storm_psh_national", default=1.0)
    return {"psh_average": 4.5, "storm_psh": {"blizzard": 0.5, "storm_design": storm, "light_overcast": 1.5},
            "confidence": "low", "source": "national fallback (PVWatts/NSRDB unavailable offline)"}
