#!/usr/bin/env python3
"""
Bokeh server app: interactive dengue choropleth with month selector.
Run locally:  bokeh serve --show app
Deploy on Render: see README notes at bottom of this file.
"""

import json, calendar
from copy import deepcopy
import pandas as pd
from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models import (
    GeoJSONDataSource, LinearColorMapper, ColorBar, HoverTool, Select, Div
)
from bokeh.palettes import Viridis256
from bokeh.plotting import figure

# ---------- name helpers (same as build_map.py) ----------
DISTRICT_KEYS = ["shapeName", "NAME_2", "name", "district", "DISTRICT"]

def norm(name: str) -> str:
    return (name or "").lower().replace("district", "").replace(" ", "").strip()

def pick_geo_name(props: dict) -> str:
    for k in DISTRICT_KEYS:
        if k in props:
            return str(props[k])
    raise KeyError("No district-like key found in GeoJSON properties")

# ---------- data loaders ----------
def load_geojson(path: str):
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj["features"]:
        props = feat["properties"]
        label = pick_geo_name(props)
        props["_district_norm"] = norm(label)
        props["district"] = label
    return gj

def load_all(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    for c in ("year", "month"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    # compute incidence if missing
    if "incidence_per_100k" not in df.columns:
        df["incidence_per_100k"] = pd.NA
    need = df["incidence_per_100k"].isna()
    df.loc[need, "incidence_per_100k"] = (df.loc[need, "cases"] / df.loc[need, "population"]) * 1e5
    df["district_norm"] = df["district"].map(norm)
    return df

def month_key(y: int, m: int) -> str:
    return f"{int(y)}-{int(m):02d}"

def attach_metrics(gj_base: dict, mdf: pd.DataFrame) -> dict:
    """Return a NEW geojson with properties set from mdf (one month slice)."""
    gj = deepcopy(gj_base)
    metrics = mdf.set_index("district_norm")[["incidence_per_100k", "cases", "population"]].to_dict("index")
    for feat in gj["features"]:
        p = feat["properties"]
        v = metrics.get(p["_district_norm"], {})
        inc = v.get("incidence_per_100k")
        cases = v.get("cases")
        pop = v.get("population")

        # numeric fields (None => JSON null)
        p["incidence_per_100k"] = float(inc) if pd.notna(inc) else None
        p["cases"] = float(cases) if pd.notna(cases) else None
        p["population"] = float(pop) if pd.notna(pop) else None

        # color-only field: zeros => None so they render as grey
        try:
            inc_num = float(p["incidence_per_100k"]) if p["incidence_per_100k"] is not None else None
        except (TypeError, ValueError):
            inc_num = None
        p["inc_for_color"] = inc_num if (inc_num is not None and inc_num > 0) else None

        # nice tooltip strings
        def _fmt_int(x): return "" if x is None or pd.isna(x) else f"{int(x):,}"
        def _fmt_float1(x): return "" if x is None or pd.isna(x) else f"{float(x):.1f}"
        p["cases_text"] = _fmt_int(p["cases"])
        p["inc_text"]  = _fmt_float1(p["incidence_per_100k"])
        p["pop_text"]  = _fmt_int(p["population"])
    return gj

# ---------- load data ----------
CSV = "data/dengue_monthly.csv"
GEO = "data/sri_lanka_districts.geojson"
df_all = load_all(CSV)
gj_base = load_geojson(GEO)

# month list from data (works with only-2024 or full 2023-2025)
months_sorted = (
    df_all[["year","month"]].dropna()
    .drop_duplicates().sort_values(["year","month"])
    .astype(int)
    .apply(lambda r: month_key(r["year"], r["month"]), axis=1)
    .tolist()
)
if not months_sorted:
    months_sorted = ["2024-01"]

# consistent color scale across all months
vmax = float(df_all["incidence_per_100k"].dropna().quantile(0.95)) if df_all["incidence_per_100k"].notna().any() else 1.0

# initial month
start_key = months_sorted[0]
start_year, start_month = map(int, start_key.split("-"))
mdf0 = df_all[(df_all["year"] == start_year) & (df_all["month"] == start_month)].copy()
gj0 = attach_metrics(gj_base, mdf0)

source = GeoJSONDataSource(geojson=json.dumps(gj0))
mapper = LinearColorMapper(palette=Viridis256, low=0, high=vmax)
mapper.nan_color = "#eeeeee"

title = Div(text=f"<h2>Dengue incidence per 100k — {calendar.month_name[start_month]} {start_year}</h2>")

p = figure(width=900, height=600, match_aspect=True, toolbar_location="above")
p.grid.visible = False
p.axis.visible = False

r = p.patches(
    "xs", "ys",
    source=source,
    fill_color={"field": "inc_for_color", "transform": mapper},  # <- use color-only field
    line_color="#666", line_width=0.5
)
p.add_tools(HoverTool(
    tooltips=[("District","@district"),
              ("Cases","@cases_text"),
              ("Incidence/100k","@inc_text"),
              ("Population","@pop_text")],
    renderers=[r]
))
p.add_layout(ColorBar(color_mapper=mapper, label_standoff=8, title="Incidence/100k"), "right")

month_select = Select(title="Month", value=start_key, options=months_sorted, width=180)

def on_change(attr, old, new):
    y, m = map(int, month_select.value.split("-"))
    mdf = df_all[(df_all["year"] == y) & (df_all["month"] == m)].copy()
    updated = attach_metrics(gj_base, mdf)
    source.geojson = json.dumps(updated)
    title.text = f"<h2>Dengue incidence per 100k — {calendar.month_name[m]} {y}</h2>"

month_select.on_change("value", on_change)

curdoc().add_root(column(title, row(month_select), p))
curdoc().title = "Sri Lanka Dengue Dashboard"

# --- Render deployment notes (summary) ---
# Start command on Render:
#   bokeh serve --allow-websocket-origin=$RENDER_EXTERNAL_HOSTNAME --port $PORT app
# Make sure requirements.txt includes: bokeh, pandas
