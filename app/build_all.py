#!/usr/bin/env python3
import os, glob, sys, subprocess, calendar
import pandas as pd

csv_path = "data/dengue_monthly.csv"

# Load CSV and ensure types
df = pd.read_csv(csv_path)
for c in ("year", "month"):
    df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")

# Compute incidence if any are missing
if "incidence_per_100k" not in df.columns:
    df["incidence_per_100k"] = pd.NA
need = df["incidence_per_100k"].isna()
df.loc[need, "incidence_per_100k"] = (df.loc[need, "cases"] / df.loc[need, "population"]) * 1e5

# Use a single color scale across months so colors are comparable
global_vmax = float(df["incidence_per_100k"].quantile(0.99)) if not df.empty else 1.0

# Build a map for every (year, month) present
pairs = sorted({(int(y), int(m)) for y, m in zip(df["year"], df["month"]) if pd.notna(y) and pd.notna(m)})
for y, m in pairs:
    subprocess.run(
        [sys.executable, "app/build_map.py", "--year", str(y), "--month", str(m), "--vmax", str(global_vmax)],
        check=True
    )

# Rebuild the index page with links to all generated maps
pages = sorted(glob.glob("docs/choropleth_*.html"))
with open("docs/index.html", "w") as f:
    f.write('<!doctype html><meta charset="utf-8"><title>Dengue maps</title><h1>Dengue maps</h1><ul>')
    for p in pages:
        base = os.path.basename(p).replace("choropleth_", "").replace(".html", "")
        y, m = base.split("_")
        label = f"{calendar.month_name[int(m)]} {y}"
        f.write(f'<li><a href="{os.path.basename(p)}">{label}</a></li>')
    f.write("</ul>")
print("Built all months and updated docs/index.html")
