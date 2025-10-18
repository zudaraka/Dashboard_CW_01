#!/usr/bin/env python3
"""
Bokeh server app: interactive dengue choropleth with month selector, metric toggle,
and a simple high-risk filter.

Run locally:
  bokeh serve --show app

Deploy on Render:
  bokeh serve --allow-websocket-origin=$RENDER_EXTERNAL_HOSTNAME --port $PORT app
"""

import json, calendar
from copy import deepcopy
import pandas as pd
from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models import (
    GeoJSONDataSource, LinearColorMapper, ColorBar, HoverTool,
    Select, Div, Slider
)
from bokeh.palettes import Viridis256
from bokeh.plotting import figure

# ---------- name helpers ----------
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
    if "incidence_per_100k" not in df.columns:
        df["incidence_per_100k"] = pd.NA
    need = df["incidence_per_100k"].isna()
    df.loc[need, "incidence_per_100k"] = (df.loc[need, "cases"] / df.loc[need, "population"]) * 1e5
    df["district_norm"] = df["district"].map(norm)
    return df

def month_key(y: int, m: int) -> str:
    return f"{int(y)}-{int(m):02d}"

def attach_metrics(gj_base: dict, mdf: pd.DataFrame, metric: str, threshold_incidence: float) -> dict:
    """
    Return a NEW geojson with properties set from mdf (one month slice).
    Adds:
      - color_value: value used for coloring (None => grey)
      - alpha: 1.0 if incidence >= threshold, else 0.2 (fade)
    """
    gj = deepcopy(gj_base)
    metrics = mdf.set_index("district_norm")[["incidence_per_100k", "cases", "population"]].to_dict("index")
    for feat in gj["features"]:
        p = feat["properties"]
        v = metrics.get(p["_district_norm"], {})
        inc = v.get("incidence_per_100k")
        cases = v.get("cases")
        pop = v.get("population")

        p["incidence_per_100k"] = float(inc) if pd.notna(inc) else None
        p["cases"] = float(cases) if pd.notna(cases) else None
        p["population"] = float(pop) if pd.notna(pop) else None

        # color value by chosen metric; grey out zeros by using None
        if metric == "incidence_per_100k":
            val = p["incidence_per_100k"]
            p["color_value"] = (float(val) if (val is not None and val > 0) else None)
        else:  # "cases"
            val = p["cases"]
            p["color_value"] = (float(val) if (val is not None and val > 0) else None)

        # highlight by incidence threshold (independent of current metric)
        inc_val = p["incidence_per_100k"]
        p["alpha"] = 1.0 if (inc_val is not None and inc_val >= float(threshold_incidence)) else 0.2 if threshold_incidence > 0 else 1.0

        # tooltip text
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

months_sorted = (
    df_all[["year","month"]].dropna()
    .drop_duplicates().sort_values(["year","month"])
    .astype(int)
    .apply(lambda r: month_key(r["year"], r["month"]), axis=1)
    .tolist()
) or ["2024-01"]

# consistent color scales per metric
vmax_inc = float(df_all["incidence_per_100k"].dropna().quantile(0.95)) if df_all["incidence_per_100k"].notna().any() else 1.0
vmax_cases = float(df_all["cases"].dropna().quantile(0.95)) if df_all["cases"].notna().any() else 1.0
vmax_map = {"incidence_per_100k": vmax_inc, "cases": vmax_cases}

# initial state
current_metric = "incidence_per_100k"
risk_threshold = 0

start_key = months_sorted[0]
start_year, start_month = map(int, start_key.split("-"))
mdf0 = df_all[(df_all["year"] == start_year) & (df_all["month"] == start_month)].copy()
gj0 = attach_metrics(gj_base, mdf0, current_metric, risk_threshold)

source = GeoJSONDataSource(geojson=json.dumps(gj0))
mapper = LinearColorMapper(palette=Viridis256, low=0, high=vmax_map[current_metric])
mapper.nan_color = "#eeeeee"

title = Div(text=f"<h2>Dengue incidence per 100k — {calendar.month_name[start_month]} {start_year}</h2>")

p = figure(width=900, height=600, match_aspect=True, toolbar_location="above")
p.grid.visible = False
p.axis.visible = False

r = p.patches(
    "xs", "ys",
    source=source,
    fill_color={"field": "color_value", "transform": mapper},
    fill_alpha="alpha",
    line_color="#666", line_width=0.5
)

p.add_tools(HoverTool(
    tooltips=[("District","@district"),
              ("Cases","@cases_text"),
              ("Incidence/100k","@inc_text"),
              ("Population","@pop_text")],
    renderers=[r]
))
p.add_layout(ColorBar(color_mapper=mapper, label_standoff=8, title="Value"), "right")

# ---------- widgets ----------
month_select = Select(title="Month", value=start_key, options=months_sorted, width=160)
metric_select = Select(
    title="Metric",
    value=current_metric,
    options=[("incidence_per_100k", "Incidence/100k"), ("cases", "Cases")],
    width=160,
)
risk_slider = Slider(
    title="Min incidence/100k to highlight",
    start=0, end=int(max(1, vmax_inc)), step=1, value=risk_threshold, width=280
)

# ---------- callbacks ----------
def update():
    y, m = map(int, month_select.value.split("-"))
    field = metric_select.value
    thr = float(risk_slider.value)

    mdf = df_all[(df_all["year"] == y) & (df_all["month"] == m)].copy()
    updated = attach_metrics(gj_base, mdf, field, thr)

    mapper.high = vmax_map[field]
    r.glyph.fill_color = {"field": "color_value", "transform": mapper}

    source.geojson = json.dumps(updated)
    metric_label = "incidence per 100k" if field == "incidence_per_100k" else "cases"
    title.text = f"<h2>Dengue {metric_label} — {calendar.month_name[m]} {y}</h2>"

def on_change(attr, old, new):
    update()

month_select.on_change("value", on_change)
metric_select.on_change("value", on_change)
risk_slider.on_change("value", on_change)

curdoc().add_root(column(title, row(month_select, metric_select, risk_slider), p))
curdoc().title = "Sri Lanka Dengue Dashboard"
