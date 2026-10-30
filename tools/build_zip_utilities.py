"""Build engine/aps_engine/data/zip_utilities.json from NREL/OpenEI 'U.S. Electric Utility Companies and Rates:
Look-up by Zipcode (2023)' (https://data.openei.org/submissions/6225): iou_zipcodes_2023.csv, non_iou_zipcodes_2023.csv.
Output: {zips: {zip: [eiaid,...]}, utilities: {eiaid: [name, state, ownership, res_rate_2023, service_type]}}."""
import csv, json, sys
OUT = sys.argv[1] if len(sys.argv) > 1 else "engine/aps_engine/data/zip_utilities.json"
zips, ut = {}, {}
for f in ("iou_zipcodes_2023.csv", "non_iou_zipcodes_2023.csv"):
    for r in csv.DictReader(open(f)):
        eid = r["eiaid"]
        if not (r["service_type"] == "Delivery" and eid in ut):  # bundled row carries the all-in average
            ut[eid] = [r["utility_name"], r["state"], r["ownership"], round(float(r["res_rate"] or 0), 4), r["service_type"]]
        lst = zips.setdefault(r["zip"].zfill(5), [])
        if eid not in lst:
            lst.append(eid)
json.dump({"source": "NREL/OpenEI Utility Companies and Rates: Look-up by Zipcode (2023), derived from EIA-861 + ABB Velocity Suite",
           "source_url": "https://data.openei.org/submissions/6225", "data_year": 2023,
           "note": "ZIPs are 'likely' service areas; a ZIP may list several utilities.",
           "zips": zips, "utilities": ut}, open(OUT, "w"), separators=(",", ":"), sort_keys=True)
print(len(zips), "zips", len(ut), "utilities")
