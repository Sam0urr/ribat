# CLAUDE.md — Ribat

Instructions for AI assistants working in this repository. Read before editing.

## What this is

Ribat maps the **incidence** of geopolitical risk, not its origin. Vocabulary,
used consistently everywhere:

- **GPR** — Caldara–Iacoviello country-specific index: risk a country *emits*,
  as reported in ten anglophone newspapers. Source-side. Not ours; CC-BY.
- **Intensity** — our index: risk an economy *feels*, GPR weighted by
  dependency (trade, energy, raw materials, chokepoints). `INT_i,t = Σ_c θ_c ·
  Σ_j w^c_ij · G_j,t`.
- Never reintroduce the old name "GRE" (collides with the Graduate Record
  Examination and was renamed deliberately).

METHODOLOGY.md is the contract. If code and METHODOLOGY.md disagree, one of
them is a bug — fix the divergence, never paper over it. Every methodological
choice (normalisation, lagged weights, carry-forward, proxies) must be stated
there and, where it affects reading the map, surfaced in the interface.

## Invariants — do not undo these

1. **No build step.** `web/index.html` is one hand-readable file. No React, no
   bundler, no npm, no new runtime dependencies. Everything the three pages
   (map, story, method) load is vendored: every payload and the country
   polygons ship under `web/data/`, and the two libraries (MapLibre GL JS, topojson-client) and the story
   page's typefaces (Fraunces, IBM Plex Sans, IBM Plex Mono) ship under
   `web/vendor/` with a hash manifest (`web/vendor/MANIFEST.json`), so the
   published site makes **zero third-party requests at runtime** — no CDN, no
   font service, no tile server, API or tracker. Upgrade a library or a font
   by replacing the vendored file and its manifest entry (bytes and sha256),
   never by reintroducing a CDN or Google Fonts tag; the verifier fails on any
   `http(s)://` script, stylesheet, preconnect, `@import` or `url()` in any
   page. Do not add a third library.
2. **MapLibre GL JS, never Mapbox GL JS.** Documented in README (token,
   billing, reviewer dependency). Do not "upgrade" back.
3. **Weights are lagged.** Each month uses the latest benchmark year strictly
   before it (endogeneity, METHODOLOGY §5.3). Never join contemporaneous
   weights by choice. The one exception is structural, not optional: months
   before the first benchmark year have no prior vintage and fall back to the
   earliest benchmark, which postdates them (currently every month through
   2019-12, 84% of the slider). That fallback must stay **flagged**, never
   silent: 03 emits `weights_anachronistic_through` (derived from the vintage
   map, never hard-coded), the legend caption, detail panel and exports warn
   on every affected month, and 04 flags affected event studies (METHODOLOGY
   §5.7). Non-reporters carry forward their last benchmark and must be listed
   in `stale_weights` and flagged in the UI (currently: RUS, 2021).
4. **Both normalisations ship; neither is "the" default.** Rebased anchors
   100 = own 1985–2023 mean and applies to source-side GPR. Intensity has no
   natural anchor (weighted sum of rebased series) and is coloured by
   percentile rank. A legend must show real break values, never `0 ─ 100`.
5. **Colour: single-hue / CVD-safe sequential ramps only.** No rainbow ramps,
   no green-means-safe semantics, no "threat map" styling — the aesthetic must
   not claim real-time surveillance capability the data does not have
   (monthly, preliminary, media-salience-based; §5.1).
6. **CC-BY attribution is binding.** Caldara & Iacoviello (2022) AER 112(4)
   1194-1225 + download date, carried in LICENSE, SOURCES.md and the payload.
   Any new data source gets a SOURCES.md row with licence before it is joined.
7. **Known-gap honesty.** Taiwan: risk source only (Comtrade non-reporter,
   mapped from "Other Asia, nes"). WITS denominators use the reported `WLD`
   total, never the partner sum (region aggregates double-count ~2×).
   Because the numerator is GPR-44 and the denominator is `WLD`, the weights
   sum to the covered share, so each channel value = `covered_share × mean
   partner GPR over observed partners` — a ranking confound under percentile
   colouring, not just a downward bias (METHODOLOGY §5.4). Coverage
   (`covered_share`) is reported next to every value it qualifies, and the
   interface carries a coverage toggle ("as observed" default / "per observed
   dependency" divides each channel by its covered share; chokepoint has no
   coverage measure and is never divided). Exports record which mode produced
   the file (`coverage_normalisation`). Do not make the divided mode the
   default and do not remove the raw one.
8. **Raw data are never edited** (`data/raw/`), never committed (gitignored),
   and always re-fetchable by documented command. Weight CSVs in
   `data/processed/` ARE committed — benchmark cross-sections, not monthly
   artefacts; the refresh workflow must not re-fetch WITS/OECD monthly.

## Pipeline

Order is load-bearing:

```
01_load_gpr.py                GPR workbook -> tidy series + coverage report
02_build_weights.py           WITS gross trade weights      (cached, rarely re-run)
02b_build_channel_weights.py  WITS fuels + ores/metals      (cached, rarely re-run)
02c_build_va_weights.py       OECD TiVA value-added weights (cached, rarely re-run)
03_build_intensity.py         join GPR x weights -> web/data/intensity.json
04_validate.py                discriminant / channel / event-study tests
05_render_method.py           METHODOLOGY.md -> web/method.html (typeset copy)
```

`web/method.html` is generated, never hand-edited. It embeds the sha256 of the
METHODOLOGY.md it was rendered from and the verifier fails when that no longer
matches, so every edit to METHODOLOGY.md is followed by
`python3 pipeline/05_render_method.py`. The renderer is standard library only
and handles the Markdown subset the document uses; a construct it does not
know renders as plain text rather than failing, so look at the page after
adding one. The refresh workflow does not run 05: the method does not change
monthly.

Monthly refresh (`.github/workflows/refresh.yml`) re-runs only 01 → 03 → 04.
Change detection hashes `{months, countries}` — never file bytes, which differ
every build via timestamps.

Chokepoint channel (03, METHODOLOGY §3.4): the littoral mean **excludes the
exposed economy's own GPR** — the bilateral channels exclude it by
construction and the chokepoint channel must too, or an economy's own risk
feeds back through its own strait (this is what put SAU atop the 2023-10 Red
Sea event study). Where an economy is a strait's only covered littoral (SAU at
Hormuz, TUR at the Bosphorus) that strait contributes nothing to its channel;
03 computes those pairs and emits them as `choke_self_excluded`, alongside
`choke_littorals`, and the detail panel states them. Never hard-code the
list. `transit(i, j)` returns `{chokepoint: fraction}`; only CHN carries a
fraction below 1 (Taiwan Strait 0.7, port-throughput derivation in the code
comment). `top_sources` is gone from the payload — the reverse map derives it
from `weights.json` for any month, channel and mix; do not reintroduce it.

## Before any commit

Run the verification skill: `.claude/skills/ribat-verify/` (or directly:
`python3 .claude/skills/ribat-verify/verify.py`). It must pass. It checks
Python compilation, inline-JS syntax, payload contract, coverage counts,
banned-token residue, licence presence, the vendored assets (every file under
`web/vendor/` listed in `MANIFEST.json` with its recorded byte count and
sha256, every licence file present, and no `http(s)://` script, stylesheet,
preconnect, `@import` or `url()` in any page), the export contract
(CSV/JSON header,
SVG and GeoJSON), the reverse map's disclosures, the README provenance digest,
the 01/03 pipeline regression guards, the map export contract (PNG back
buffer), map coverage (every payload economy reaches a paintable feature), and
the methods-review contract, including the validation summary
(`web/data/validation.json` against the report, and the story page's hooks),
and the method page (rendered from the current METHODOLOGY.md, every numbered
section anchored, no script, the story linking it locally, issue forms present).

After changing 03 or the payload schema: bump/keep `kind` consistent with the
front end's loader (`web/index.html` reads `kind` to choose render paths), and
re-run 04 — a validation regression is a finding, not noise.

## Cowork skills worth invoking (not available in plain Claude Code)

| When | Skill |
|---|---|
| Pipeline or payload changed, before publishing | `data:validate-data` |
| Ingesting any new data source | `data:explore-data` |
| Palette / legend / chart work | `data:data-visualization` |
| Drafting the Phase 4 methods note | `doc-coauthoring` |

## Style

British-leaning academic English in docs; no marketing language. Comments
explain *why* (the WITS aggregate trap, the xlrd requirement) rather than
narrating code. Limitations are stated in the interface, not buried.
