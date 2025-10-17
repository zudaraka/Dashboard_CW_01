#!/usr/bin/env python3
import argparse, json, math, os, random, shutil
import pandas as pd

# --- name helpers (match build_map.py/main.py) ---
DISTRICT_KEYS = ["shapeName", "NAME_2", "name", "district", "DISTRICT"]
def norm(s): return (s or "").lower().replace("district", "").replace(" ", "").strip()
def pick(props):
    for k in DISTRICT_KEYS:
        if k in props:
            return str(props[k])
    raise KeyError("No district-like key in GeoJSON properties")

def districts_from_geo(geo_path: str):
    with open(geo_path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    seen, labels = set(), []
    for feat in gj["features"]:
        label = pick(feat["properties"])
        n = norm(label)
        if n not in seen:
            labels.append(label)
            seen.add(n)
    labels.sort(key=lambda s: norm(s))
    return labels

def month_iter(start: str, end: str):
    y1, m1 = map(int, start.split("-"))
    y2, m2 = map(int, end.split("-"))
    y, m = y1, m1
    while (y < y2) or (y == y2 and m <= m2):
        yield y, m
        m += 1
        if m == 13:
            m = 1
            y += 1

# ---------- NEW: optional population CSV ----------
def load_pops_csv(path: str):
    """
    Read a CSV containing columns: district,population
    Returns a dict keyed by normalized district name -> float(population)
    """
    if not path:
        return {}
    if not os.path.exists(path):
        print(f"[warn] population CSV not found: {path} (using defaults)")
        return {}
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    if not {"district", "population"}.issubset(df.columns):
        raise ValueError("Population CSV must have columns: district,population")
    # coerce population to numeric, drop bad rows
    df["population"] = pd.to_numeric(df["population"], errors="coerce")
    df = df.dropna(subset=["district", "population"])
    pops = {norm(str(r["district"])): float(r["population"]) for _, r in df.iterrows()}
    print(f"[ok] loaded {len(pops)} population rows from {path}")
    return pops

def write_pop_template(out_path: str, geo_path: str, prefill_col_gam: bool = True):
    """
    Create a 'district,population' CSV template from the GeoJSON districts.
    Optionally pre-fill Colombo/Gampaha with known values to guide editing.
    """
    labels = districts_from_geo(geo_path)
    base = {}
    if prefill_col_gam:
        base = {"colombo": 2_415_000, "gampaha": 2_394_000}

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("district,population\n")
        for d in labels:
            v = base.get(norm(d), "")
            f.write(f"{d},{v}\n")
    print(f"[ok] wrote population template: {out_path} ({len(labels)} districts)")

# ---------- DEMO DATA GENERATOR ----------
def make_demo(csv_out: str,
              geo_path: str = "data/sri_lanka_districts.geojson",
              start: str = "2024-01",
              end: str = "2024-12",
              seed: int = 42,
              pop_csv: str = None):
    """
    Generate a full monthly dataset with plausible incidence & cases.

    If --pop-csv is provided, populations are taken from that file (by district).
    Otherwise: Colombo/Gampaha use built-ins, others fall back to 600,000.
    """
    labels = districts_from_geo(geo_path)
    rng = random.Random(seed)

    # 1) Start with a tiny built-in map (Colombo/Gampaha)
    pop_map = {
        "colombo": 2_415_000,
        "gampaha": 2_394_000,
    }
    # 2) Overlay anything from CSV (if provided)
    pop_map.update(load_pops_csv(pop_csv))

    default_pop = 600_000  # used only if district not in pop_map

    rows = []
    for y, m in month_iter(start, end):
        # mild seasonality (peaks mid-year), plus district variation
        season = 0.75 + 0.75 * math.sin(2 * math.pi * (m - 1) / 12.0 + 0.5)
        for label in labels:
            n = norm(label)
            pop = float(pop_map.get(n, default_pop))
            district_factor = 0.6 + 0.9 * rng.random()      # 0.6–1.5
            incidence = max(0.0, (18 + 22 * season) * district_factor)  # ~18–40 per 100k
            cases = int(round(pop * incidence / 1e5))

            rows.append({
                "year": y, "month": m, "district": label,
                "cases": cases, "population": pop,
                "incidence_per_100k": incidence
            })

    df = pd.DataFrame(rows, columns=["year","month","district","cases","population","incidence_per_100k"])

    # backup if file exists
    if os.path.exists(csv_out):
        shutil.copyfile(csv_out, csv_out + ".bak")
        print(f"[ok] backed up existing CSV to {csv_out}.bak")

    df.to_csv(csv_out, index=False)
    print(f"[ok] wrote {csv_out} with {len(df)} rows "
          f"({len(labels)} districts × {len(list(month_iter(start, end)))} months).")

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="Utilities for dengue_monthly.csv and populations")
    ap.add_argument("cmd", choices=["make-demo", "pop-template"])
    ap.add_argument("--start", default="2024-01", help="YYYY-MM inclusive (for make-demo)")
    ap.add_argument("--end", default="2024-12", help="YYYY-MM inclusive (for make-demo)")
    ap.add_argument("--out", default="data/dengue_monthly.csv", help="Output CSV for make-demo")
    ap.add_argument("--geo", default="data/sri_lanka_districts.geojson", help="GeoJSON path")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed (make-demo)")
    ap.add_argument("--pop-csv", default=None, help="CSV with district,population to override defaults (make-demo)")
    ap.add_argument("--pop-out", default="data/district_population.csv",
                    help="Output path for pop-template (ignored by make-demo)")
    ap.add_argument("--no-prefill", action="store_true",
                    help="When writing pop-template, do not prefill Colombo/Gampaha")
    args = ap.parse_args()

    if args.cmd == "make-demo":
        make_demo(args.out, args.geo, args.start, args.end, args.seed, args.pop_csv)
    elif args.cmd == "pop-template":
        write_pop_template(args.pop_out, args.geo, prefill_col_gam=not args.no_prefill)

if __name__ == "__main__":
    main()
