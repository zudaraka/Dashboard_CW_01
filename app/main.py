#!/usr/bin/env python3
"""
Bokeh server app: interactive dengue choropleth with month selector, metric toggle,
and a simple high-risk filter (alpha based on incidence threshold).

Run locally:
  bokeh serve --show app

Deploy on Render:
  bokeh serve --allow-websocket-origin=$RENDER_EXTERNAL_HOSTNAME --port $PORT app
"""

import json, calendar
from pathlib import Path
import pandas as pd
from bokeh.io import curdoc
from bokeh.layouts import column, row
from bokeh.models import (
    GeoJSONDataSource, LinearColorMapper, ColorBar, HoverTool,
    Select, Div, Slider, CustomJSTransform
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
    gj = json.loads(Path(path).read_text(encoding="utf-8"))
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

def attach_static_metrics(gj_base: dict, mdf: pd.DataFrame) -> dict:
    """
    Return a NEW geojson with *static* fields per district from the month slice:
      incidence_per_100k, cases, population
      + preformatted tooltip strings
    No color/alpha fields here — those are computed client-side with transforms.
    """
    # IMPORTANT: we don't deepcopy geometry-heavy parts; we build a new dict
    # and reuse coordinates from base (safe because we don't mutate them).
    gj = {"type": gj_base["type"], "features": []}
    metrics = mdf.set_index("district_norm")[["incidence_per_100k", "cases", "population"]].to_dict("index")

    for feat in gj_base["features"]:
        # shallow copy geometry reference; new properties dict
        props_base = feat["properties"]
        v = metrics.get(props_base["_district_norm"], {})
        inc = v.get("incidence_per_100k")
        cases = v.get("cases")
        pop = v.get("population")

        p = {
            **{k: props_base[k] for k in ("_district_norm", "district")},
            "incidence_per_100k": float(inc) if inc is not None and pd.notna(inc) else None,
            "cases": float(cases) if cases is not None and pd.notna(cases) else None,
            "population": float(pop) if pop is not None and pd.notna(pop) else None,
        }

        # nice tooltip strings
        def _fmt_int(x): return "" if x is None or pd.isna(x) else f"{int(x):,}"
        def _fmt_float1(x): return "" if x is None or pd.isna(x) else f"{float(x):.1f}"
        p["cases_text"] = _fmt_int(p["cases"])
        p["inc_text"]  = _fmt_float1(p["incidence_per_100k"])
        p["pop_text"]  = _fmt_int(p["population"])

        gj["features"].append({
            "type": feat.get("type", "Feature"),
            "geometry": feat["geometry"],   # reuse reference; we never mutate geometry
            "properties": p
        })

    return gj

# ---------- load data ----------
CSV = "data/dengue_monthly.csv"
GEO = "data/sri_lanka_districts.geojson"
df_all = load_all(CSV)
gj_base = load_geojson(GEO)

# month list from data
months_sorted = (
    df_all[["year","month"]].dropna()
    .drop_duplicates().sort_values(["year","month"])
    .astype(int)
    .apply(lambda r: month_key(r["year"], r["month"]), axis=1)
    .tolist()
) or ["2024-01"]

# consistent color scales across all months (per-metric)
vmax_inc = float(df_all["incidence_per_100k"].dropna().quantile(0.95)) if df_all["incidence_per_100k"].notna().any() else 1.0
vmax_cases = float(df_all["cases"].dropna().quantile(0.95)) if df_all["cases"].notna().any() else 1.0
vmax_map = {"incidence_per_100k": vmax_inc, "cases": vmax_cases}

# ---------- precompute a compact GeoJSON string per month (static metrics only) ----------
GEOJSON_BY_MONTH = {}
for key in months_sorted:
    y, m = map(int, key.split("-"))
    mdf = df_all[(df_all["year"] == y) & (df_all["month"] == m)].copy()
    gj = attach_static_metrics(gj_base, mdf)
    # compact serialization to reduce payload size
    GEOJSON_BY_MONTH[key] = json.dumps(gj, separators=(",", ":"))

# ---------- initial state ----------
current_metric = "incidence_per_100k"
risk_threshold = 0  # incidence threshold for highlighting

start_key = months_sorted[0]
start_year, start_month = map(int, start_key.split("-"))

source = GeoJSONDataSource(geojson=GEOJSON_BY_MONTH[start_key])

# color mapper
mapper = LinearColorMapper(palette=Viridis256, low=0, high=vmax_map[current_metric])
mapper.nan_color = "#eeeeee"

# UI title
title = Div(text=f"<h2>Dengue incidence per 100k — {calendar.month_name[start_month]} {start_year}</h2>")

# ---------- figure ----------
p = figure(
    width=900, height=600, match_aspect=True,
    toolbar_location="above",
    output_backend="webgl",   # faster rendering
)
p.grid.visible = False
p.axis.visible = False

# ---------- client-side transforms ----------
# 1) map <=0 to NaN so zeros render as grey via nan_color
zero_to_nan = CustomJSTransform(code="""
  // xs is the column array; return same length
  const out = new Array(xs.length);
  for (let i = 0; i < xs.length; i++) {
    const v = Number(xs[i]);
    out[i] = (isFinite(v) && v > 0) ? v : NaN;
  }
  return out;
""")

# 2) alpha by threshold based on incidence_per_100k
#    We pass the slider as an arg; transform reevaluates on slider change
#    (no server recompute needed).
# Placeholder slider object; defined below and then wired via .args update.
alpha_by_threshold = CustomJSTransform(code="""
  const thr = Number(threshold.value || 0);
  const out = new Array(xs.length);
  for (let i = 0; i < xs.length; i++) {
    const v = Number(xs[i]);
    out[i] = (isFinite(v) && v >= thr) ? 1.0 : (thr > 0 ? 0.2 : 1.0);
  }
  return out;
""", args={})  # we'll inject the slider after creating it

# ---------- glyph ----------
# Start with incidence metric; mapping will be flipped when the user selects "Cases".
r = p.patches(
    "xs", "ys",
    source=source,
    fill_color={"field": current_metric, "transform": zero_to_nan},
    # alpha always based on incidence column:
    fill_alpha={"field": "incidence_per_100k", "transform": alpha_by_threshold},
    line_color="#666", line_width=0.5
)

p.add_tools(HoverTool(
    tooltips=[("District","@district"),
              ("Cases","@cases_text"),
              ("Incidence/100k","@inc_text"),
              ("Population","@pop_text")],
    renderers=[r]
))

color_bar = ColorBar(color_mapper=mapper, label_standoff=8, title="Incidence/100k")
p.add_layout(color_bar, "right")

# ---------- widgets ----------
month_select = Select(title="Month", value=start_key, options=months_sorted, width=160)
metric_select = Select(
    title="Metric", value=current_metric,
    options=[("incidence_per_100k", "Incidence/100k"), ("cases", "Cases")],
    width=160,
)
risk_slider = Slider(
    title="Min incidence/100k to highlight",
    start=0, end=int(max(1, vmax_inc)), step=1, value=risk_threshold, width=280
)

# wire slider into the alpha transform (so it updates purely on the client)
alpha_by_threshold.args = {"threshold": risk_slider}

# ---------- callbacks (lightweight) ----------
def on_month_change(attr, old, new):
    key = month_select.value
    source.geojson = GEOJSON_BY_MONTH[key]
    y, m = map(int, key.split("-"))
    metric_label = "incidence per 100k" if metric_select.value == "incidence_per_100k" else "cases"
    title.text = f"<h2>Dengue {metric_label} — {calendar.month_name[m]} {y}</h2>"

def on_metric_change(attr, old, new):
    field = metric_select.value  # "incidence_per_100k" or "cases"
    # switch color field (zero->NaN transform reused)
    r.glyph.fill_color = {"field": field, "transform": zero_to_nan}
    # update color scale + colorbar title
    mapper.high = vmax_map[field]
    color_bar.title = "Incidence/100k" if field == "incidence_per_100k" else "Cases"
    # refresh title text (month unchanged)
    y, m = map(int, month_select.value.split("-"))
    metric_label = "incidence per 100k" if field == "incidence_per_100k" else "cases"
    title.text = f"<h2>Dengue {metric_label} — {calendar.month_name[m]} {y}</h2>"

# Note: risk_slider changes do NOT require a Python callback — the transform
# reads threshold.value directly in the browser for instant updates.

month_select.on_change("value", on_month_change)
metric_select.on_change("value", on_metric_change)

curdoc().add_root(column(title, row(month_select, metric_select, risk_slider), p))
curdoc().title = "Sri Lanka Dengue Dashboard"
