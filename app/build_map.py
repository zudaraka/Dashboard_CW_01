import argparse, calendar
from pathlib import Path
from bokeh.io import output_file, save
from bokeh.plotting import figure
from bokeh.models import GeoJSONDataSource, LinearColorMapper, ColorBar, HoverTool
from bokeh.palettes import Viridis256
from data_utils import merge_for_month

def main(year:int, month:int):
    gdf = merge_for_month(year, month)
    geo_source = GeoJSONDataSource(geojson=gdf.to_json())

    high = float(max(gdf["incidence_per_100k"].max(), 0.01))
    mapper = LinearColorMapper(palette=Viridis256, low=0.0, high=high)

    p = figure(
        title=f"Dengue incidence per 100k — {calendar.month_name[month]} {year}",
        match_aspect=True,
        toolbar_location="above",
        tools="pan,wheel_zoom,reset,save,hover",
        x_axis_label="Longitude", y_axis_label="Latitude",
    )
    p.grid.visible = False

    patches = p.patches(
        "xs", "ys",
        source=geo_source,
        fill_color={"field":"incidence_per_100k", "transform": mapper},
        fill_alpha=0.85,
        line_color="#444", line_width=0.5,
    )

    hover = p.select_one(HoverTool)
    hover.tooltips = [
        ("District", "@district"),
        ("Incidence/100k", "@incidence_per_100k{0.00}"),
        ("Cases", "@cases{0}"),
        ("Population", "@population{0,0}"),
    ]
    hover.renderers = [patches]

    color_bar = ColorBar(color_mapper=mapper, title="Incidence/100k", width=8)
    p.add_layout(color_bar, "right")

    out = Path(__file__).resolve().parents[1] / "docs" / f"choropleth_{year}_{month:02d}.html"
    output_file(out.as_posix(), title=p.title.text)
    save(p)
    print(f"Wrote {out}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--month", type=int, default=1)
    args = ap.parse_args()
    main(args.year, args.month)
