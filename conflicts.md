# APS config v0.5.0 - conflicts

PRELIMINARY. **Open: 0** (config 0.6.0). C28 resolved 2026-10-30: turnkey area = Cape Cod, the Islands incl. Nantucket, and SouthCoast. Consent C1 approved; 15K-2P-N default inverter. Resolved 2026-10-30 by owner: inverter prices researched, 12K pick, generator, datasheet items, suggested picks accepted. Earlier: C11 design fee $0, C12 markup 0%, C15 CS 3-h formula.

| ID | Field | Resolution | Source |
|---|---|---|---|
| C01 | 12K-2P-N cost | $4,350 (street median; until distributor invoice) | ShopSolar $4,299 / Current Connected $4,350 (chargedreviews price log 2026-10-28); American Solar $4,750 |
| C02 | 15K-2P-N cost | $5,350 | Stella Volta $4,999; EVonomy $5,150; US Solar Supplier $5,526; altE $7,071 |
| C03 | 18K-2P-N cost | $6,050 | Stella Volta $5,829; US Solar Supplier $6,267 |
| C04 | Dual 12K | $8,700 (2x; 1x bug fixed) | derived |
| C05 | EG4 14.3 kWh | $3,250 per SKU | owner accepted |
| C06a/b | Default gen | DuroMax XP13000HXT, $1,600 | owner |
| C07 | Generac 22 kW installed | $11,500 | owner accepted |
| C08 | BOS | tiered 1,000/1,200/1,500 | owner accepted |
| C09 | Permit | $500 + separate interconnection line | owner accepted |
| C10 | Partner labor (private) | [redacted: private overlay] | owner accepted |
| C13 | Rest-of-MA CS | $225 flagged, not in payback (unverified) | owner accepted |
| C14 | C&I CS | null, verify 200 vs 275; not in payback | owner accepted |
| C16 | Usable fraction | 0.90 per SKU | owner accepted |
| C17 | MA rate | $0.315 per utility | owner accepted |
| C18 | Escalation | 3% + sensitivity | owner accepted |
| C19 | NEM export | retail | owner accepted |
| C20 | SMART | disabled until verified | owner accepted |
| C21 | MA credit | 15% cap $1,000, MA only | owner accepted |
| C22 | Gen start SOC | 20% | owner accepted |
| C23 | 12K gen port | 9,600 W (40 A cont.; bigger gens to GRID input) | 12K manual |
| C24a | 12K PV | 12,000 W usable / 13,000 W STC | 12K datasheet Rev 3 |
| C24b | 15K PV | 19,500 W usable / 23,400 W STC | 15K datasheet Rev 5 |
| C25 | 12K continuous | 9,000 W AC (+3 kW DC to battery); 12K-P = 12K-2P-N | 12K datasheet |
| C26 | 18K gen port | 19,200 W (80 A cont., manual; datasheet Rev 7 says 28.8 kW) | 18K manual / datasheet |
| C30 | 18K AC charge | 17,920 W (350 A x 51.2 V) | 18K datasheet |
| C31 | 15K continuous | 15 kW with PV, 12 kW battery-only (13 kW 30 min) | 15K datasheet Rev 5 |
| C32 | EG4 closed loop | open-loop default (Sol-Ark doesn't certify; EG4 claims support) | EG4 LifePower4 V2 doc |
| C28 | Turnkey service area / Nantucket | Cape Cod, the Islands incl. Nantucket, and SouthCoast | owner 2026-10-30 |

Datasheets: 12K https://sol-ark.com/wp-content/uploads/2024/06/SK150-0003_Rev-3_12K_Datasheet_EN_18June2025.pdf · 15K https://sol-ark.com/wp-content/uploads/2024/06/SK150-0001_Rev5_15K-Datasheet_EN-18June2025.pdf · 18K https://sol-ark.com/wp-content/uploads/2025/09/18KDatasheet_PS-00036_Rev_7_15July2026.pdf
