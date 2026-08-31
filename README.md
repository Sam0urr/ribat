# Ribat

**A watchpost for geopolitical exposure.**

An interactive map of **who bears geopolitical risk**, rather than where it
originates. Built on the Caldara–Iacoviello country-specific GPR indices
(CC-BY), weighted by trade, energy, critical-raw-material and
maritime-chokepoint dependency.

*Ribāṭ* (رباط): a frontier watchpost — a garrison stationed at the edge to
observe what is approaching. The project measures the **Intensity** index: what
each economy actually feels, as opposed to GPR, which measures what each
country emits.

See [`METHODOLOGY.md`](METHODOLOGY.md) for index construction and limitations.
See [`SOURCES.md`](SOURCES.md) for the data manifest and licences.

---

## Why this and not a GPR choropleth

A direct map of country GPR already exists in at least two public forms
(Iacoviello's own country charts; Saadaoui, November 2025). The measurement
frontier is also closed: Iacoviello and Tong's **AI-GPR Index** (Federal Reserve
Board, March 2026) applies LLM scoring to ~5 million archived articles. That
work rests on institutional newspaper-archive licensing, which is the actual
barrier to entry — not model access.

Exposure incidence is the part nobody has built publicly, it is answerable with
open data, and it is the question EU policy actually asks.

---

## Roadmap

The four purposes this project serves have partly conflicting requirements. They
are satisfied by sequencing, not by building four things.

| Phase | Output | Serves |
|---|---|---|
| **1. Prototype** | Trade-weighted Intensity, 44 source countries, ~40 exposed economies, monthly 1985–present, time slider, adjustable channel weights | Portfolio |
| **2. Full channels** | Energy, CRM and chokepoint layers; covered-trade-share reporting; rebased/level toggle | Portfolio, research |
| **3. Value-added weights** | OECD TiVA FDVA weights as a gross/value-added toggle on the trade channel; addresses limitation 5.2 | Research, academic |
| **4. Methods note** | Short paper documenting construction, validation against known episodes, replication files | Academic |
| **5. Scheduled refresh** | Monthly pipeline run on GPR update (first business day of month), automated deploy | Public tool |

Phases 1–2 are the shippable artefact. Phase 3 is where an original contribution
would sit, and it is optional. Phase 5 is the only phase that creates ongoing
maintenance obligation — do not start it before 1–2 are stable.

---

## Stack

**Rendering: MapLibre GL JS, not Mapbox GL JS.**

MapLibre is the open-source fork of Mapbox GL JS (forked at v1, when Mapbox moved
to a proprietary licence in December 2020). It has the same API and supports globe
projection. The difference that matters here:

| | Mapbox GL JS | MapLibre GL JS |
|---|---|---|
| Access token in client code | Required | None |
| Usage-based billing | Yes, above free tier | None |
| Account dependency for reviewers | Yes | No |
| Works from a local file / any host | With token | Yes |

For a country-level choropleth you do not need a tile basemap at all — country
polygons rendered as a GeoJSON source are sufficient, which removes the tile
dependency entirely. If the design later needs a basemap, Protomaps or a
self-hosted style covers it without a vendor account.

**Pipeline:** Python (pandas, requests). Exports static JSON consumed directly
by the front end. No server, no database, no API keys, no build step.
Country polygons are vendored, so the published page makes zero third-party
requests at runtime.

---

## Structure

```
.
├── METHODOLOGY.md          index construction and limitations
├── SOURCES.md              data manifest, licences, citation requirements
├── data/
│   ├── raw/                downloaded source data, never edited
│   ├── reference/          hand-maintained lookups (chokepoints, ISO codes)
│   └── processed/          pipeline output consumed by the web layer
├── pipeline/
│   ├── 01_load_gpr.py               parse GPR workbook, validate coverage
│   ├── 02_build_weights.py          WITS gross trade weights
│   ├── 02b_build_channel_weights.py WITS fuels + ores/metals weights
│   ├── 02c_build_va_weights.py      OECD TiVA value-added weights
│   └── 03_build_intensity.py        join GPR x weights, export web payload
└── web/
    ├── data/                    payload + vendored country polygons
    └── index.html               MapLibre front end
```

---

## Getting started

**Step 1 — GPR data.** Already downloaded to `data/raw/data_gpr_export.xls`
(2.6 MB, legacy `.xls`, retrieved 31 August 2026). To refresh:

```bash
curl -sSL -o data/raw/data_gpr_export.xls \
  https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls
```

Record the download date — the CC-BY citation requires it, and the latest months
are preliminary and subject to revision.

**Step 2 — run the pipeline.**

```bash
pip install pandas xlrd openpyxl requests
python3 pipeline/01_load_gpr.py               # GPR workbook -> tidy series
python3 pipeline/02_build_weights.py          # WITS gross trade weights
python3 pipeline/02b_build_channel_weights.py # energy + raw-material weights
python3 pipeline/02c_build_va_weights.py      # value-added weights (OECD TiVA)
python3 pipeline/03_build_intensity.py        # join -> web/data/intensity.json
```

`02` fetches 264 WITS responses on first run (~5 min) and caches them under
`data/raw/wits/`; reruns are free.

`xlrd` is required, not optional: the workbook is legacy OLE2 (`CDFV2 Microsoft
Excel`), which `openpyxl` cannot read.

**Step 3 — serve the map.**

```bash
python3 -m http.server 8000 --directory web
```

Opening `web/index.html` as a `file://` URL will not work — the page fetches
its payload, which `file://` blocks. Use the server.

## Deployment

`.github/workflows/pages.yml` publishes `web/` to GitHub Pages on every push to
`main`. Enable it once under **Settings → Pages → Source: GitHub Actions**; the
map is then served from the repository root URL rather than `/web/`.

---

## Data currency

GPR monthly data update on the first business day of each month; daily data every
Monday. As of 31 August 2026 the monthly file was last updated 3 August 2026 and
the daily file 24 August 2026. The most recent months are preliminary.
