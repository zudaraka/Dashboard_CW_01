# Sri Lanka Geo Dashboard

**Interactive Bokeh app** that maps monthly **dengue burden** across Sri Lankan districts.

* **Metrics:** *Incidence per 100k* ↔ *Cases* (toggle)
* **Time range:** **Jan 2023 → Sep 2025** (demo data)
* **Hosting:** Live on Render • Works locally with `bokeh serve`

**Live demo:** [https://sri-lanka-dengue.onrender.com/app](https://sri-lanka-dengue.onrender.com/app)
*(Free tier may take ~30–60s to wake up.)*

---

## Features

* 🗺️ Choropleth of 25 districts (Viridis, fixed per-metric scale).
* 🧭 Month selector to browse time.
* 🔁 Metric toggle.
* 🎯 “High-risk” slider to fade low-incidence districts.
* 🧷 Hover tooltips: district, cases, incidence/100k, population.
* 📄 Optional static monthly HTMLs for easy sharing.

---

## Data

* **GeoJSON:** `data/sri_lanka_districts.geojson`
* **CSV:** `data/dengue_monthly.csv` with columns
  `year,month,district,cases,population,incidence_per_100k`
* If `incidence_per_100k` is missing, it’s computed as `(cases/population)*1e5`.
* Zeros render **grey** (still visible in tooltip).
* Color scale fixes to the **95th percentile** (per metric) across all months.

### Make demo data (quick)

```bash
python app/data_utils.py pop-template --pop-out data/district_population.csv
python app/data_utils.py make-demo --start 2023-01 --end 2025-09 --pop-csv data/district_population.csv
```

Replace `dengue_monthly.csv` with real data any time (keep the same columns).

---

## Run locally

```bash
# Python 3.11+ recommended (see runtime.txt)
pip install -r requirements.txt

# Open http://localhost:5006/app
bokeh serve --show app
```

---

## Deploy on Render (free)

Already set up with **render.yaml** + **runtime.txt**.

1. Push to GitHub.
2. Render → **New** → **Blueprint** → select the repo → **Free** plan.
3. Auto-deploys on every push.

Build: `pip install -r requirements.txt`
Start: `bokeh serve --allow-websocket-origin=$RENDER_EXTERNAL_HOSTNAME --port $PORT app`
Health check: `/app`

> Tip: First request after sleep is slow on the free tier.

---

## Static pages (optional)

```bash
python app/build_all.py
```

Writes `docs/choropleth_YYYY_MM.html` for each month plus `docs/index.html`.

---

## Troubleshooting

* **Only a few districts colored?** Your CSV likely has zeros—use the demo generator or fill values.
* **Blank page on Render?** Check **Logs**; ensure `render.yaml`, `requirements.txt`, and `runtime.txt` are committed.
* **Slow first load?** Free tier cold start; give it ~30–60s.

---

## License & credits

* MIT License (see `LICENSE`).
* Built with **Bokeh 3.x** and **Pandas**.
* Ideas for future work: add a time-series panel, district search, and mobile layout tweaks.
