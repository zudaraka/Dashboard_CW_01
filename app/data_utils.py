from pathlib import Path
import pandas as pd
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

def load_geo():
    gdf = gpd.read_file(DATA / "sri_lanka_districts.geojson")
    if "district" not in gdf.columns:
        gdf["district"] = gdf["shapeName"].astype(str)
    return gdf

def load_cases():
    df = pd.read_csv(DATA / "dengue_monthly.csv")
    df["district"] = df["district"].astype(str)
    # Fill incidence if blank
    if "incidence_per_100k" not in df.columns or df["incidence_per_100k"].isna().any():
        df["incidence_per_100k"] = (df["cases"] / df["population"] * 1e5).round(2)
    return df

def merge_for_month(year:int, month:int):
    gdf = load_geo()
    df = load_cases()
    sub = df[(df["year"]==year) & (df["month"]==month)][
        ["district","cases","population","incidence_per_100k"]
    ]
    merged = gdf.merge(sub, on="district", how="left")
    for col in ["cases","population","incidence_per_100k"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)
    return merged
