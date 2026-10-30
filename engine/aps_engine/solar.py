"""Solar: PVWatts v8 (developer.nlr.gov) when NLR_API_KEY is set and online; otherwise a clearly
labelled SYNTHETIC hourly profile scaled to PSH. Existing and new kW counted once each."""
import os, json, math, urllib.request

PVWATTS_URL = "https://developer.nlr.gov/api/pvwatts/v8.json"
SYSTEM_LOSS = 0.86 * 0.93  # system 0.86 x inverter/temperature 0.93 -> ~0.80 AC/DC-STC


def _bell():
    # daylight 6..18, sine shape, normalized to 1.0 kWh per kW per PSH
    w = [max(0.0, math.sin(math.pi * (h - 6 + 0.5) / 12)) if 6 <= h < 18 else 0.0 for h in range(24)]
    s = sum(w)
    return [x / s for x in w]

BELL = _bell()


def pvwatts_annual(lat, lon, kw, online=False):
    key = os.environ.get("NLR_API_KEY")
    if not (online and key and kw > 0):
        return None
    q = f"?api_key={key}&lat={lat}&lon={lon}&system_capacity={kw}&module_type=0&losses=14&array_type=1&tilt=30&azimuth=180&timeframe=hourly"
    try:
        with urllib.request.urlopen(PVWATTS_URL + q, timeout=15) as r:
            d = json.load(r)["outputs"]
        return {"ac_annual_kwh": d["ac_annual"], "ac_hourly_w": d.get("ac"), "source": "PVWatts v8 (developer.nlr.gov)"}
    except Exception as e:  # network/API failure -> fallback
        return None


def daily_profile(pv_kw, psh):
    """Hourly AC kW for one day at a given PSH. SYNTHETIC (not PVWatts)."""
    e = pv_kw * psh * SYSTEM_LOSS
    return [e * b for b in BELL]


def annual_kwh(new_kw, psh_average, lat=None, lon=None, online=False, degradation_yr=0):
    """Year-1 production of the NEW array only (F-3 / F-27)."""
    pv = pvwatts_annual(lat, lon, new_kw, online) if lat is not None else None
    if pv:
        return pv["ac_annual_kwh"], {"source": pv["source"], "confidence": "medium"}
    return new_kw * psh_average * 365 * SYSTEM_LOSS, {
        "source": "SYNTHETIC profile: kW x annual PSH x 365 x 0.80 (no PVWatts key / offline)", "confidence": "low"}
