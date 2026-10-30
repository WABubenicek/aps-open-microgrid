"""National baseline (non-MA): utility by ZIP, EIA-861 rate, export policy, incentives, labels."""
from aps_engine.api import design_system
from aps_engine import baseline as B

REQ = {"tier": "critical", "kwh_day": 20, "pv_kw_new": 6, "outage_days": 3}


def run(addr):
    return design_system({**REQ, "address": addr})


def test_tx_austin_energy():
    o = run("100 Congress Ave, Austin, TX 78701"); f = o["finance"]
    assert o["region"]["utility"] == "Austin Energy"
    assert f["finance_available"] and f["npv"] is not None
    assert "value-of-solar" in f["solar_value_method"]
    ids = {p["id"]: p for p in f["incentives"]["incentives"]["programs"]}
    assert ids["austin-energy-solar-rebate"]["amount"] == 4000
    assert f["incentives"]["total_incentives"] == 4500
    assert any(g["program"] == "austin-power-partner-battery" and g["included_in_payback"] for g in f["grid_services"])
    assert f["labels"]["tariff_rate"]["basis"] == "auto_sourced" and f["labels"]["export_credit"]["basis"] == "verified"


def test_ca_pge_net_billing():
    o = run("1 A St, Davis, CA 95616"); f = o["finance"]
    assert "Pacific Gas" in o["region"]["utility"]
    assert o["region"]["tariff"]["export_credit"]["export_policy"] == "net_billing"
    assert f["finance_available"] and f["incentives"]["total_incentives"] == 0  # SGIP waitlisted -> not counted
    assert f["labels"]["escalation"]["confidence"] == "low"


def test_fl_fpl():
    o = run("1 Main, Miami, FL 33101"); f = o["finance"]
    assert "Florida Power" in o["region"]["utility"]
    assert o["region"]["tariff"]["export_credit"]["export_ratio_of_retail"] == 1.0
    progs = f["incentives"]["incentives"]["programs"]
    assert progs and not any(p["counted_in_base_case"] for p in progs)  # tax exemptions info-only


def test_rural_coop_tx():
    u = B.utility_for_zip("78636", "TX")
    assert "Coop" in u["name"] and u["alternatives"] and u["confidence"] == "low"
    o = run("1 Rd, Dripping Springs, TX 78636")
    assert o["finance"]["finance_available"] and o["finance"]["labels"]["export_credit"]["basis"] == "auto_sourced"


def test_federal_25d_zero_48e_not_counted():
    inc = run("1 Main, Miami, FL 33101")["finance"]["incentives"]["incentives"]
    assert inc["federal_25d"]["amount"] == 0 and inc["federal_48e_tpo"]["status"] == "unverified"


def test_expired_entries_excluded(monkeypatch):
    monkeypatch.setenv("APS_TODAY", "2028-01-01")
    o = run("100 Congress Ave, Austin, TX 78701"); f = o["finance"]
    assert f["incentives"]["total_incentives"] == 0 and not f["grid_services"]


def test_ma_pack_unchanged():
    f = run("1 Main St, Brewster, MA 02631")["finance"]
    assert f["labels"]["pack"] == "curated MA pack" and "curated" in f["solar_value_method"]
