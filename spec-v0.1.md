# APS Open Microgrid Design Engine — Spec v0.1 (DRAFT, rev 4 — all US states & utilities, free public tool)

Hybrid solar + LFP battery + generator design engine. Antifragile Power Systems (Bill Bubenicek). Drafted 2026-10-29 from `APS-Design-Extract-2026-10-29`.
Rev 2 (2026-10-29, owner feedback): engine is **location-driven and nationwide**; Cape Cod/CLC becomes the first region pack (`ma-clc`). Config version 0.2.0 (file name kept).
Rev 3 (2026-10-30, owner): **all US states and utilities from day one** via an automated national data layer (§13); maintenance policy approved. Config 0.3.0.
Config: `aps-config.v0.1.json` (public) + `aps-config.private.json` (overlay, never committed). Open conflicts: `conflicts.md` (28).

Tags: **[KEPT]** carried from legacy as-is · **[CORRECTED – audit ref]** legacy rule fixed · **[NEW]** · **[NEEDS-DECISION]**.
Refs: S=`aps-specs.js`, E=`aps-estimator.html` (excerpts in `estimator-engine-extract.js`), D=`design.html`, L=`aps-design-link.js`, CAT=`aps_pricing_catalog.json`, MCP=`aps_quote_mcp.py`, PC=`getConfig-PRICING_CONFIG.js`, KB=`solark_technical_kb.md`, DOC=`DESIGN-ENGINE.md`, A01/A02/A03 = audit files.

---

## 1. Scope, disclaimers, licensed-review gate
- 1.1 [NEW – rev 2] Engine produces **preliminary** designs for residential/light-commercial hybrid systems **anywhere in the US**. Pipeline: `resolve_region(address|zip)` → load model → candidate platforms → `simulate()`/`explore_tradeoffs()` per platform → score → recommendation with pick/reject reasons. Sol-Ark is the *preferred* platform (tie-break), not a default. Every output carries "Preliminary — not licensed engineering."
- 1.2 [NEW] **Licensed-review gate:** `status` of any design is `preliminary` until a licensed electrician/PE records review (`review: {by, license_no, date}`). Permit package ($495) is only generated for a reviewed design.
- 1.3 [CORRECTED – rev 2] Any region without a verified pack degrades gracefully: equipment + resilience only; finance and grid services shown "not available for this region" (§13.4). Legacy "confirm locally" (OWNER §4) kept as copy. Electrician confirms main breaker, service size, feed (D:288).
- 1.4 [NEW] Publish rule: any config value with `status: conflict` blocks publication of every output that depends on it; `unverified` values render with a visible flag (A00 §5.1 "every claim needs a source").
- 1.5 [CORRECTED – A01 F-33, A00 §1.1] One engine module + one config; legacy price books #1–#6 and 5 CS-rate copies are retired.
- Out of scope v0.1: commercial 3-phase (S:943-1060 kept as reference only), NEC 120% busbar calc (not in sources — [NEEDS-DECISION] add later), wind/hydro (KB: DC-couple only).

## 2. Inputs schema
```
DesignInput {
  site: { address: string, zip?: string, state?: string, utility?: string, lat?, lon? }
  path: "new" | "has_solar" | "has_solark" | "has_gen" | "solar_gen"     // E step-1 paths [KEPT]
  usage: { monthly_kwh? | monthly_bill_usd? , hourly_profile?: number[24] }
  appliances: ApplianceId[]                    // E:1307-1323 table [KEPT]
  load_tier: "emergency"|"bare_minimum"|"critical"|"essential"|"whole_home"
  autonomy_goal: { outage_days: number, gen_allowed: boolean, fuel_on_hand_gal?: number }
  existing: { solar_kw?, solar_inverter?, solark_model?, generator?: {model|rated_kw, auto_start} }
  new_solar_kw?: number   roof?: { tilt, azimuth, max_kw }
  platform_preference?: "auto" (default; engine decides) | platform id
  goal_weights?: { resilience_first: true, maximize: "npv"|"lowest_cost" }
  finance: { mode: "cash"|"loan", discount_rate?, horizon_yrs? }
}
```
- [CORRECTED – A01 F-11] `has_solark` must state the model; do not assume 15K.
- [NEW] `zip` may be given separately; address is parsed only as fallback (§9).
- [CORRECTED – A02 E33] Full address never goes into a shareable URL; the design link carries ZIP only.

## 3. Load model
- 3.1 [KEPT] Appliance table [peak W, kWh/day] (E:1307-1323; config `design_rules.appliances`).
- 3.2 [CORRECTED – A01 F-1] Engine carries **two loads**: `avg_kw = kwh_day/24` (energy: battery, autonomy, fuel, recharge) and `peak_w` (diversified; inverter, surge, gen port only). Peak watts are never treated as a 24/7 load.
- 3.3 [NEW] Hourly profile: user-supplied 24-h shape or default residential shape (evening peak) scaled to tier kWh/day; used by `simulate()`.
- 3.4 Tiers:
  | Tier | Definition | Tag |
  |---|---|---|
  | emergency | 0.8 kW continuous = 19.2 kWh/day (E:2971, E:2770) | [KEPT as separate tier – owner decision (b)] |
  | bare_minimum | **6.5 kWh/day** (lights 3.5 + fridge 1.5 + Wi-Fi 1.5) + well 1.5 + sump 1.0 if present; heat zone +5.0 optional (D:125-134) | [NEW default – owner (b); config status "owner default, open"] |
  | critical | user-selected bundle × duty 0.55 (E:1734) | [KEPT] |
  | essential | bundle × 0.40 (E:1734) | [KEPT] |
  | whole_home | bill/usage-derived kWh, duty 0.35 for peak (E:1734) | [KEPT] |
- 3.5 [KEPT] If user backup kWh/day < tier value, lower wins (D:203).
- 3.6 [NEEDS-DECISION] Duty factors 0.55/0.40/0.35 are unsourced design choices.

## 4. Solar
- 4.1 [KEPT] PVWatts via proxy (AL nrelProxy); losses: inverter 0.88, system 0.86, degradation 0.5%/yr (E:1127-1131). [NEW] Use hourly TMY output for `simulate()`.
- 4.2 [CORRECTED – A01 F-3] **Existing and new arrays counted once each**: `pv_kw_total = existing_kw + new_kw`; savings only on `new_kw` for an add-on; when existing=0, yr-1 kWh is new-array kWh only (fix of E:2124-2134).
- 4.3 [CORRECTED – A01 F-4] Two weather cases: `average` (monthly PSH table, 4.3 annual, E:1127-1146) for economics; `storm` (PSH 1.0 design, 0.5 blizzard, 1.5 overcast) for every resilience/fuel headline. `calculateFuelAutonomy` default 4.3 (S:1455) is retired.
- 4.4 [CORRECTED – A01 F-23] PV over inverter check uses datasheet `pv_max_w` (C24a/b open).
- 4.5 [CORRECTED – A01 F-27] Existing array savings never included in add-on payback.

## 5. Platform & inverter selection (engine decision) [NEW – rev 2]
- 5.1 Candidates = every `catalog.platforms` entry (Sol-Ark preferred, EG4, Tesla PW3, Enphase, FranklinWH, extensible) × its models/battery SKUs. Each has capability flags `{value, source, verified_on, status}`: gen_autostart, gen_charges_battery, off_grid_microgrid, max_continuous_w, surge, pv_max_w, battery_skus, grid_services_eligibility (per program), financeable, installer_cert_required. Only Sol-Ark and PW3 flags are sourced today; EG4/Enphase/FranklinWH = NEEDS RESEARCH.
- 5.2 **Hard filter (resiliency first):** continuous battery-side W ≥ peak_w at chosen tier; surge ≥ largest motor LRA; pv_max_w ≥ pv_kw; autonomy goal met in `simulate()` at **storm** weather (if goal needs a generator: gen_autostart / gen_charges_battery as the goal requires — PW3 fails any goal that needs generator recharge); off_grid if requested. A required flag that is `unknown` → "needs research", never recommended. [CORRECTED – F-1, F-2, F-22: forced 12K→15K upgrade E:1669-1681 removed]
- 5.3 **Score survivors** with the region pack: lifetime cost at cost + fees − incentives − grid-services income (only eligible + verified programs; pending → shown, excluded), NPV, payback, financeability (pack loans). Lowest net cost / highest NPV wins; Sol-Ark wins ties within `policy.preferred_tie_band` (proposal 5%, needs-decision).
- 5.4 Output `platform_report[]`: each candidate → `picked | rejected | needs_research` + reasons (e.g. "PW3 rejected: cannot recharge battery from generator; 7-day goal needs 22 gal with no gen charging", "Sol-Ark 15K: CS pending eligibility in ma-clc, excluded from payback").
- 5.5 [KEPT] Soft-start on 4–5 t fixed-speed compressors (KB). Interconnection risk flag 12K low/15K med/18K high (E:1675) → moves into pack `interconnection` rules.
- 5.6 Tesla PW3 sourced facts (2026-10-29): 11.5 kW continuous, 13.5 kWh, 185 LRA, 20 kW PV; no AGS, no gen charging, not off-grid. Price + program eligibility NEEDS RESEARCH.

## 6. Battery sizing
- 6.1 [CORRECTED – A03 F3, A01 F-32] **Per-SKU kWh** from catalog (14.3, 5.12, 15.36, 14.4, 13.5); 14.3 is never assumed.
- 6.2 [KEPT] Outage targets 12 / **24 default** / 48 h battery-only (S:116-145). Floor = `target_h × avg_kw(tier) / usable / rte` (DOC) — sized and reported on the **same** load (F-1).
- 6.3 [CORRECTED – A01 F-14] One `usable_fraction` per SKU (C16 open; proposal 0.90).
- 6.4 [CORRECTED – A01 F-25] Income optimizer kept (S:1365-1431) with fixes: unit cost includes install/BOS share; CS income only when eligible & verified; hurdle default 8 yr **[NEEDS-DECISION D4: 8 yr vs 5-yr CS lock]**; self-consumption value at MA NEM ≈ retail → ~0 (F-9).
- 6.5 [KEPT] Min 2 units for serious designs (S:1125); CS dispatch `paid_kw = min(batt_side_kw × n_inv, usable_kwh/3)` (S:1342 formula, one copy).
- 6.6 [CORRECTED – A03 F1] CS kW per battery is never a flat 5 kW; always the capped formula above.
- 6.7 [CORRECTED – A01 F-26] Battery family choice = cheapest SKU set meeting floor (no forced LP4→WallMount flip at 15 kWh, S:1220-1315).

## 7. Generator
- 7.1 [KEPT] Default **portable** (OWNER). Size = largest gen with `rated ≤ gen_port_max_w × 1.1` (S:1172-1180); C06a open on default model.
- 7.2 [CORRECTED – A01 F-5] Copy branches on `auto_start`; manual portable says "you start it at X% SOC".
- 7.3 [CORRECTED – A01 F-29] Fuel curve = linear interpolation across 25/50/75/100% points (config), not step.
- 7.4 [CORRECTED – A01 F-6, F-20] Infeasible-gen flag when `rated×0.85 < avg_kw + min_useful_charge`; never show "∞".
- 7.5 [CORRECTED – owner (a)] **No runtime target.** Proposed "~2 h/day, 4 h ceiling" (OWN §1, NOT FOUND) is dropped; runtime is an output of §8 `simulate()`.
- 7.6 [CORRECTED – A01 F-16, A03 6.1] Generator cost = selected model's price (estimator priced 13 kW class but picked XP16000iH).

## 8. Autonomy & fuel — `simulate()` and `explore_tradeoffs()` [NEW – owner (a)]
```
simulate(design, load_tier, weather_case: "average"|"storm"|"blizzard", outage_days) -> {
  hourly: [{h, pv_kw, load_kw, batt_soc, gen_kw, gen_on, unserved_kwh}],
  gen_hrs_per_day[], fuel_gal_per_day[], total_gal, propane_lb,
  gen_free_hours, longest_gen_free_stretch_h, unserved_kwh, feasible: bool
}
```
Hourly dispatch, `t = 0..24×outage_days`, start SOC 0.95 (E):
1. PV → load; surplus → battery (cap: battery max charge, inverter max charge).
2. Deficit → battery down to `gen_start_soc` (C22 open: 0.10 vs 0.20); then generator.
3. Generator (Sol-Ark): runs at `min(rated, load + charge_cap)`, where `charge_cap = min(max_ac_charge_w, gen_port_max_w − load, Σ battery charge)` (fixes F-4 uncapped rate, F-15); stops at `gen_stop_soc` 0.90 (S:46-49). Fuel from interpolated curve at actual load fraction.
4. Generator (Tesla PW3, `generator_charges_battery=false`): gen serves load directly via transfer switch only while battery ≤ reserve; no battery charging from gen; fuel at load fraction.
5. Unserved energy logged; design infeasible if > 0.

Fuel plan [KEPT – OWNER/D:199-219]: plan 7 days at bare_minimum, storm weather; round to 5-gal cans, min 10 gal; propane 20-lb tank alternative; stabilizer + rotate 6–12 mo. Fuel headline always at **storm** (fixes F-4, A00 #13).

```
explore_tradeoffs(base_design, vary = {battery_units: [..], pv_kw: [..], gen_kw: [..], load_tier: [..]},
                  weather_case="storm", outage_days=goal) -> grid[] of
  {battery_units, pv_kw, gen_kw, load_tier, cost_at_cost, gen_hrs_per_day, total_gal, gen_free_hours,
   annual_value, simple_payback, npv, meets_goal}
```
**Recommendation** [NEW]: the lowest `cost_at_cost` row with `meets_goal = true` (feasible, outage_days at chosen tier within user fuel limit, or gen-free if `gen_allowed=false`). The grid feeds UI sliders and AI reasoning. Hard-coded runtime constants (E:2788 20 gal / 4.3 PSH, S:1455-1456) removed.

## 9. Region context, incentives & grid services [rev 2]
- 9.1 [CORRECTED – A01 F-7, A02 E8, A03 F4] ZIP parser: explicit `zip` field; else **last** 5-digit/ZIP+4 token after a 2-letter state; never a leading house number. Blank → `region: unknown` (prompt). Tests: "10234 Main St, Brewster, MA 02631" → 02631.
- 9.2 `resolve_region(zip)` → `{state, utility, ahj, climate{psh_avg, psh_storm, pvwatts}, retail_tariff{rate, tou, escalation}, net_metering, interconnection, incentives[], grid_services[], pack_id, completeness}` via `regions.packs` (utility pack > state pack > `_default`). Utility lookup per §13.1 (HIFLD polygon + EIA-861), not ZIP tables.
- 9.3 **Grid services module** — generic program: `{id, type: capacity_dr|vpp|capacity_market|tou_arbitrage|demand_charge|export_credit, pay_basis: $/kW-season|$/kW-yr|$/kWh|$/event, rate, event_hours, season, eligible_equipment{model: true|pending|unknown}, enrollment_cap, lock_in_years, performance_formula, stacking_rules}`. Income = `min(batt_side_kw × n_inv, usable_kwh / event_hours) × rate` for capacity types [KEPT S:1342]; TOU arbitrage from pack tariff via hourly dispatch.
- 9.4 Instances: `cs-clc` ($275/kW-summer, 3 h, Jun–Sep, 5-yr lock, verified Jul 2026; 12K eligible, 15K/18K pending, PW3 unknown) [KEPT]; `cs-ma-other` ($225 estimate, conflict C13); `cs-ma-ci` (C14). Other regions' VPPs plug in as new instances.
- 9.5 [CORRECTED – F-10, F-19, E4/E6/E7] SMART, MA credit, NEM all live in the MA packs only; no flat −$1,000; no residential MACRS; 25D not promised. Federal items in `_federal` pack.

## 10. Costs & margin
- 10.1 [CORRECTED – A00 #11, A03 F5/F6, A02 E10 — margin inconsistency] Public model = **equipment at cost (0% markup) + posted fees**: design $0, permit package $495, remote commissioning $395, turnkey install = posted flat fee (**[NEEDS-DECISION D2]** schedule not defined). Any internal analysis values live only in the private overlay.
- 10.2 [CORRECTED – A03 §6.3] One price book; same payload → same price in every surface (X5).
- 10.3 [KEPT] Fuel bought locally, $0 line (D). New solar: "local quote" or $2,800–3,200/kW estimate flagged (PC).
- 10.4 [CORRECTED – A01 F-36] Round all money to $1. Show low–high only where sources legitimately span; conflicts block.
- 10.5 [NEEDS-DECISION D5] Partner labor on public designs requires partner consent (A00 §6.4); kept in private overlay.

## 11. Finance
- 11.1 [NEW] Outputs: simple payback, NPV (explicit discount rate, default 6%; sensitivity 8%), 25-yr cash flow; rate escalation from config (C18 open) — CS **flat** for the 5-yr lock (fixes E30), then 0 unless renewed (conservative).
- 11.2 [CORRECTED – A01 F-28] Payback on mid cost, not low.
- 11.3 [CORRECTED – A02 E31] No "monthly finance equivalent" unless a real product (HEAT loan 0%/84 mo/$25k, battery-only eligibility unverified).
- 11.4 [NEW – rev 2, owner] Missing/stub pack → equipment + resilience only; finance flagged "not available for this region" (no payback/NPV). Partial pack → only verified fields used.

## 12. Outputs
Design JSON + page: BOM at cost (per SKU), fees, inverter rationale, battery kWh (per SKU), CS line (verified / estimate / pending), simulate() summary at storm for chosen tier (gen hrs/day, gal/day, total gal for goal, gen-free hours), fuel plan, tradeoff grid, economics (policy-gated), narrative (why gen oversized, fuel storage, single app — OWNER), caveats, config version + source of every number. "Copy for AI" brief [KEPT D:435-472].

## 13. National data layer, baseline packs & overrides [NEW – rev 3, owner-approved]
- 13.1 **Resolution pipeline:** address → US Census geocoder (lat/lon, county FIPS) → HIFLD retail-territory polygon → EIA utility id (cross-checked with EIA-861 county list; if more than one utility, ask the user) → **baseline pack** (state × EIA id) → curated **override** layered on top (ma-clc first) → `RegionContext` with per-field `status` + `confidence`.
- 13.2 **Sources** (access verified 2026-10-30; details in config `data_layer`):

| Need | Source / access | License · cost · limits | Refresh |
|---|---|---|---|
| Utility territory | HIFLD Electric Retail Service Territories (HIFLD Next/PEDP, updated 2026-08-17; ICPSR archive) + EIA-861 Service_Territory (2025 final, released 2026-10-07) | public, bulk; host in PostGIS | quarterly / annual |
| Tariffs | OpenEI URDB API `api.openei.org/utility_rates?version=latest` (by EIA id or lat/lon) | free key; 500 records/call | weekly |
| Tariff fallback | EIA-861 sales / EIA API v2 avg $/kWh | public; free key | monthly/annual |
| NEM / export / interconnection policy | DSIRE API (paid annual subscription, price unpublished) + URDB sell rates + EIA-861 Net_Metering (presence) + state PUC | paid / public | weekly / semiannual |
| Incentives | DSIRE API (ZIP association) ; federal: IRS OBBB FAQ — 25D ended for expenditures after 2025-12-31; 48E for third-party/business storage | paid / public | weekly / quarterly |
| Solar resource | PVWatts v8 `developer.nlr.gov` (NREL is now National Laboratory of the Rockies; old domain retired 2026-05-29) | free key, 1,000 req/h | cache per grid cell |
| Storm-day PSH | NSRDB multi-year GHI: P10 of worst consecutive 3/5/7-day Dec–Feb windows | free key; 2,000 req/day, 1 req/2 s | one-time + yearly |
| Grid services | Utility DR/BYOB/VPP pages + EIA-861 Demand_Response (presence) + ISO/RTO (ISO-NE, PJM, NYISO, CAISO, ERCOT, MISO, SPP) | public pages; bot-parsed | quarterly |
| Permitting / AHJ | SolarAPP+ jurisdiction table (350+ AHJs; Storage-Only in ~20) + Census places | public | monthly |
| Outage / resilience defaults | EIA-861 Reliability (SAIDI/SAIFI ±MED) + ORNL EAGLE-I county outages 2014–2025 | public, bulk | annual |

- 13.3 **Baseline packs** auto-generated for every EIA utility × state (~3,000), status `auto_sourced`, never `verified`. **Confidence**: high = curated/Bill-approved within 180 d; medium = structured federal data (current URDB tariff, PVWatts, EIA reliability); low = parsed text (DSIRE, program pages) or fallback averages; none = missing → degrade. Every output line shows its confidence badge.
- 13.4 **Overrides**: curated packs (`ma-clc` full; `ma-other`, `commercial-ci-ma` seeds with MA conflicts) win field-by-field over baseline.
- 13.5 **Degrade**: resilience always shown; finance only if tariff confidence ≥ medium; grid-services income only from verified or Bill-approved programs (auto-sourced programs listed as "possible, unverified", excluded from payback); conflicts never published.
- 13.6 **Maintenance (APPROVED by owner 2026-10-30):** Technical bot (catalog, flags, eligible-equipment lists) and Financial bot (tariffs, NEM, incentives, grid services) open sourced diffs (URL + retrieved date per value); **Bill approves before `verified`**; `verified_on` older than **180 days** → reverts to unverified and is flagged. Refresh cadence per source in `policy.refresh_cadence` (table above).
- 13.7 Resiliency defaults: default `outage_days` = round-up of county P90 EAGLE-I outage duration (min 1 day), shown as "typical long outage here"; user can override.
- 13.8 **Gaps — no national machine-readable source:** utility DR/VPP program terms and eligible-equipment lists; interconnection rules (size limits, fees, timelines); AHJ fees and NEC code year outside SolarAPP+; ISO/RTO residential participation paths; DSIRE NEM/incentive detail is text (structured only via paid API, still needs parsing); hourly residential load shapes per utility (proposal: NREL ResStock/EULP — needs research); equipment pricing by region.

## 14. Front end [NEW – rev 2]
- 14.1 Human web UI with the existing APS look/feel, hosted at antifragilepower.com `/estimate` and `/design`, calling the **same HTTP API the MCP server wraps** (`resolve_region`, `design`, `simulate`, `explore_tradeoffs`, `platform_report`) — one engine, no front-end math (fixes F-33/X5).
- 14.2 Keep slider trade-off UX: battery units, PV kW, gen kW, load tier → runtime (gen hrs/day, gen-free hours), fuel, cost, return; region badge showing pack status; platform pick/reject panel.
- 14.3 Legacy site (estimator, design.html, landing calculators) is **replaced**; until cutover it is only minimally secured (no full addresses in URLs, rate limits, legacy price books unpublished) — not hardened.

## 15. Reference test homes + known-error regressions
| ID | Home (from A01 §6) | Must hold in v0.1 |
|---|---|---|
| A | Brewster 02631, 15.38 kWh/d, lights+fridge+wifi | yr-1 solar 5,048 kWh not 10,108 (F-3); CS on 15K = pending |
| B | Provincetown, 20.5 kWh/d, peak 7,350 W | autonomy computed on 0.85 kW avg → ≥24 h for sized bank (F-1) |
| C/C2 | New Bedford / Falmouth, 33 kWh/d, peak 14.5 kW, 10 kW existing | no 99 h recharge; gen-feasibility flag; existing PV not double counted |
| E | Austin TX | no TX pack → resilience only; CS/SMART/MA credit 0; finance "not available" |
| T | Brewster, 7-day goal needs gen recharge | PW3 rejected with reason; Sol-Ark picked |
| F | "10234 Main St, Brewster, MA 02631" | region = CLC (house-number bug) |
| G | blank address | region unknown, not outside-MA |
| H | Chatham, 29.5 kWh/d, peak 12,975 W | 15K not chosen (12 kW batt-side); no 1,372 h recharge |
| BM | bare minimum 6.5 kWh/d, XP13000HXT, 7 days storm | ≈45.5 kWh → 10 gal plan (D worked example) |
| LP4 | 3× 5.12 kWh design link | 15.36 kWh, not 42.9 (A03 F3) |

Known-error regressions (must fail CI if reintroduced): autonomy vs peak watts (F-1); double-counted new solar (F-3); fuel headline at average sun (F-4); region parser house numbers (F-7); 14.3 kWh assumed for every battery (A03 F3/F-32); CS income on unconfirmed 15K/18K (F-2); CS kW per battery overstatement (A03 F1); margin inconsistency (A03 F5/F6, E10).

Property invariants [KEPT – A00 §5.2]: CS = 0 outside CS regions; adding a battery never lowers resilience; recharge finite when gen > load; same payload → same price on all surfaces.

## 16. Business model & origination [NEW – rev 4, owner]
- 16.1 Free to the public: open GitHub repo, free API + MCP server, free site (antifragilepower.com /estimate, /design).
- 16.2 Licensing: code Apache-2.0; public config/region data CC-BY-4.0 (upstream licenses kept); APS / WABD names and logos trademarked, not licensed. The hosted service, brand and lead flow stay the owner's.
- 16.3 Every surface (site, API, MCP) returns attribution plus a "Get a firm quote / financing" handoff to an owner endpoint.
- 16.4 Origination: explicit opt-in consent (site checkbox; `consent` tool argument). Without consent no PII leaves the session. Lead record: lead_id, created_at, consent {given, text_version, timestamp}, contact (only with consent), ZIP (address only with consent), region {state, EIA utility id, pack, confidence}, design {platform, inverter, battery kWh, PV kW, gen, tier, outage days, mid cost}, financing interest {cash | loan | lease/TPO | unsure}, timeline {asap | 3 mo | 6–12 mo | researching}, source surface, config version. Routing: POST to the owner-controlled CRM webhook (WABD/Bill) with retries; no resale.
- 16.5 Privacy: PII kept in a separate store/project, deny-by-default, no public reads; public data has no PII; retention limit and deletion on request (lesson from the earlier Firebase exposure).
- 16.6 Finance paths: cash, loan, **lease/TPO** (owner R4); 48E eligibility for business/TPO storage: unverified, never promised.

## 17. Hosting (R5 DECIDED — Google)
- Firebase Hosting serves only a dedicated `public/` folder (no config, data or source). API + MCP on Cloud Run (or Functions). GitHub Actions refresh. Geodata in Cloud Storage + SQLite. Keys in Secret Manager. Rough cost ~$0–15/mo.
- PII leads in a SEPARATE locked-down GCP project: deny-by-default, no hosting access, write-only service account from the API.
- Engine stays platform-neutral; Cloudflare Workers is a future migration option.

## 18. Lead routing (R6 DECIDED)
- Consented leads go to hello@antifragilepower.com and the locked lead project.
- A lead-inbox bot may monitor and draft replies; outbound replies need Bill's approval or an explicit owner-defined auto-reply rule.
- Proposed consent text (DRAFT): "Yes, send my design and contact details to Antifragile Power Systems (hello@antifragilepower.com) so they can contact me about a firm quote or financing. I can ask to have my information deleted at any time. My information will not be sold."

## 19. Config 0.5.0 resolutions (2026-10-30)
- Inverter costs (street medians, Oct 2026): 12K $4,350 · 15K $5,350 · 18K $6,050 · dual 12K $8,700. Replace with distributor invoice when available.
- 12K: only one current variant (12K-2P-N = model 12K-P). 9 kW AC continuous, 9.6 kW gen port, 12 kW usable PV. Engine default for generator-backed microgrids is the **15K** (12 kW battery-only, 19.2 kW gen port, 275 A charge, 200 A pass-through) because the 12K's gen port cannot take the full output of the default XP13000HXT. 12K stays a candidate for loads ≤ 9 kW with a smaller gen. Owner P1 (CLC model) still governs the ma-clc override.
- Default generator: DuroMax XP13000HXT, $1,600.
- Open conflict: none as of 0.6.0 (C28 resolved).

## 20. Config 0.6.0 + Engine v0.1 (2026-10-30)
- Owner: Sol-Ark 15K-2P-N is the DEFAULT inverter (rapid recharge with oversized generator); 12K optional for loads ≤9 kW, smaller generator, or CLC CS eligibility (`prefer_12k`).
- C28 resolved: turnkey area = Cape Cod, the Islands incl. Nantucket, and SouthCoast (engine approximates with ZIP3 025/026/027). Nantucket stays utility pack ma-other.
- Consent C1 approved (consent-v1).
- Engine: Python package `aps_engine` at engine/; public API design_system, get_incentives, model_financing, explore_tradeoffs. Regression suite engine/tests (32 tests, all pass).
- Resilience metric for the monotonic invariant = longest generator-free stretch (h) with zero unserved energy. Total gen-free hours is not monotonic because each generator run recharges to 90%.
- explore_tradeoffs never recommends fewer than the minimum of 2 battery units.

## Needs-decision summary (rev 6)
Open: auto-reply rules · N4 platforms + tie band · N5 turnkey fee · N6 hurdle 8 vs 5 yr · N8 front-end cutover · P3 6.5 kWh/day · distributor invoice to replace street prices.
