"""Solar: PVWatts v8 (developer.nlr.gov) when NLR_API_KEY is set and online; otherwise a clearly
labelled SYNTHETIC hourly profile scaled to PSH. Existing and new kW counted once each."""
import os, json, math, urllib.request, urllib.parse
from functools import lru_cache

PVWATTS_URL = "https://developer.nlr.gov/api/pvwatts/v8.json"
SYSTEM_LOSS = 0.86 * 0.93  # system 0.86 x inverter/temperature 0.93 -> ~0.80 AC/DC-STC


def _bell():
    # daylight 6..18, sine shape, normalized to 1.0 kWh per kW per PSH
    w = [max(0.0, math.sin(math.pi * (h - 6 + 0.5) / 12)) if 6 <= h < 18 else 0.0 for h in range(24)]
    s = sum(w)
    return [x / s for x in w]

BELL = _bell()


@lru_cache(maxsize=512)
def _pvwatts_1kw(lat, lon):
    """PVWatts v8 for a 1 kW-DC reference array (cached per rounded lat/lon). None on any failure."""
    key = os.environ.get("NLR_API_KEY")
    if not key:
        return None
    q = urllib.parse.urlencode({"api_key": key, "lat": lat, "lon": lon, "system_capacity": 1, "module_type": 0,
                                "losses": 14, "array_type": 1, "tilt": 30, "azimuth": 180, "timeframe": "monthly"})
    try:
        with urllib.request.urlopen(PVWATTS_URL + "?" + q, timeout=15) as r:
            d = json.load(r)
        o = d["outputs"]
        return {"kwh_per_kw_yr": o["ac_annual"], "ac_monthly_kwh_per_kw": o.get("ac_monthly"),
                "solrad_annual": o.get("solrad_annual"), "station": (d.get("station_info") or {}).get("city"),
                "source": "PVWatts v8 (developer.nlr.gov), TMY"}
    except Exception:  # network/API failure -> synthetic fallback
        return None


def pvwatts_annual(lat, lon, kw, online=False):
    if not (online and kw > 0 and lat is not None and lon is not None):
        return None
    ref = _pvwatts_1kw(round(float(lat), 2), round(float(lon), 2))
    if not ref:
        return None
    return {**ref, "ac_annual_kwh": ref["kwh_per_kw_yr"] * kw}


def solar_info(lat, lon, online=False):
    """Location solar summary for outputs; always labels its source."""
    ref = _pvwatts_1kw(round(float(lat), 2), round(float(lon), 2)) if (online and lat is not None and lon is not None) else None
    if ref:
        return {**ref, "lat": lat, "lon": lon, "confidence": "medium"}
    return {"source": "SYNTHETIC (no PVWatts key, offline, or lookup failed)", "confidence": "low"}


def daily_profile(pv_kw, psh):
    """Hourly AC kW for one day at a given PSH. SYNTHETIC (not PVWatts)."""
    e = pv_kw * psh * SYSTEM_LOSS
    return [e * b for b in BELL]


def annual_kwh(new_kw, psh_average, lat=None, lon=None, online=False, degradation_yr=0):
    """Year-1 production of the NEW array only (F-3 / F-27)."""
    if not new_kw:
        return 0.0, {"source": "no new PV in design", "confidence": "n/a"}
    pv = pvwatts_annual(lat, lon, new_kw, online) if lat is not None else None
    if pv:
        return pv["ac_annual_kwh"], {"source": pv["source"], "confidence": "medium"}
    return new_kw * psh_average * 365 * SYSTEM_LOSS, {
        "source": "SYNTHETIC profile: kW x annual PSH x 365 x 0.80 (no PVWatts key / offline)", "confidence": "low"}
