#!/usr/bin/env python3
import argparse, json, os, calendar
import pandas as pd
from bokeh.io import output_file, save
from bokeh.models import GeoJSONDataSource, LinearColorMapper, ColorBar, HoverTool
from bokeh.palettes import Viridis256
from bokeh.plotting import figure
from bokeh.models import HoverTool
from bokeh.models import LinearColorMapper, ColorBar, HoverTool   # add HoverTool

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
        feat["properties"]["_district_norm"] = norm(pick_geo_name(feat["properties"]))
    return gj

def load_month(csv_path: str, year: int, month: int) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # make sure year/month are numeric
    for c in ("year", "month"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    # compute incidence if missing
    if "incidence_per_100k" not in df.columns:
        df["incidence_per_100k"] = pd.NA
    need = df["incidence_per_100k"].isna()
    df.loc[need, "incidence_per_100k"] = (df.loc[need, "cases"] / df.loc[need, "population"]) * 1e5
    df["district_norm"] = df["district"].map(norm)
    return df[(df["year"] == int(year)) & (df["month"] == int(month))].copy()

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", required=True, type=int)
    ap.add_argument("--month", required=True, type=int)
    ap.add_argument("--vmax", type=float, default=None, help="upper bound for color scale")
    args = ap.parse_args()

    gj = load_geojson("data/sri_lanka_districts.geojson")
    mdf = load_month("data/dengue_monthly.csv", args.year, args.month)

    # attach metrics into feature properties
    metrics = mdf.set_index("district_norm")[["incidence_per_100k", "cases", "population"]].to_dict("index")
    for feat in gj["features"]:
        key = feat["properties"]["_district_norm"]
        vals = metrics.get(key)
        if vals:
            feat["properties"].update(vals)
        else:
            feat["properties"].setdefault("incidence_per_100k", 0.0)

    source = GeoJSONDataSource(geojson=json.dumps(gj))
    vmax = args.vmax or (mdf["incidence_per_100k"].quantile(0.95) if not mdf.empty else 1.0)
    mapper = LinearColorMapper(palette=Viridis256, low=0, high=float(vmax))

    hover = HoverTool(tooltips=[
        ("District", "@shapeName"),
        ("Incidence/100k", "@incidence_per_100k{0.00}"),
        ("Cases", "@cases{0}"),
        ("Population", "@population{0,0}")
    ])

    p = figure(width=900, height=600,
               title=f"Dengue incidence per 100k — {calendar.month_name[args.month]} {args.year}",
               match_aspect=True, toolbar_location="above")
    p.grid.visible = False
    p.axis.visible = False
    p.add_tools(hover)

    p.patches("xs", "ys", source=source,
              fill_color={'field': 'incidence_per_100k', 'transform': mapper},
              line_color="#444", line_width=0.5)

    p.add_layout(ColorBar(color_mapper=mapper, label_standoff=8, title="Incidence/100k"), 'right')

    os.makedirs("docs", exist_ok=True)
    outfile = f"docs/choropleth_{args.year}_{args.month:02d}.html"
    output_file(outfile, title=f"Dengue {args.year}-{args.month:02d}")
    save(p)
    print(f"Wrote {os.path.abspath(outfile)}")

if __name__ == "__main__":
    main()
color_mapper = LinearColorMapper(palette=palette, low=0, high=vmax)
color_mapper.nan_color = "#eeeeee"   # grey for districts with no data
r = p.patches(
    "xs", "ys",
    source=source,
    fill_color={"field": "incidence_per_100k", "transform": color_mapper},
    line_color="#666", line_width=0.5
)

p.add_tools(HoverTool(
    tooltips=[
        ("District", "@district"),
        ("Cases", "@cases{0,0}"),
        ("Incidence/100k", "@incidence_per_100k{0.0}")
    ],
    renderers=[r]   # limits hover to the map polygons
))
