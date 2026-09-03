---
name: ribat-verify
description: >
  Verify the Ribat repository before any commit, push, or publish: compile all
  pipeline stages, syntax-check the inline front-end JS, validate the web
  payload contracts (kind, month grid, country arrays, coverage, stale-weight
  flags), scan for banned residual tokens from the GRE-era naming, confirm
  licence/attribution files are intact, and check every vendored library and
  font under web/vendor/ against its hash manifest. Use whenever pipeline/, web/, or the
  payload schema changed, when preparing a commit, or when asked to "verify",
  "check", or "run the checks" on this project.
---

# ribat-verify

Run the deterministic check suite:

```bash
python3 .claude/skills/ribat-verify/verify.py
```

Exit code 0 with `ALL CHECKS PASSED` is the only acceptable pre-commit state.

## What it checks, and what a failure means

1. **Python compilation** — every `pipeline/*.py` byte-compiles. Failure:
   syntax error; fix before anything else.
2. **Inline JS syntax** — the last `<script>` block of `web/index.html` and of
   `web/story.html` passes `node --check`. Failure: the map will not load at all,
   or the story page silently keeps its typed fallback figures.
3. **Payload contract** — for each JSON payload in `web/data/`:
   `kind` is one of the values the front-end loader dispatches on; `months`
   strictly increasing `YYYY-MM`; every per-country series has exactly
   `len(months)` entries of numbers/nulls; `covered` in [0, 1] where present;
   `stale_weights` entries name real countries. Failure: the front end will
   silently mis-render — this is the class of bug (silent fallback, dropped
   countries) that has bitten this project before.
4. **Coverage counts** — expected number of GPR source series (44) and a sane
   number of exposed economies (>= 40). Failure: a join regressed.
5. **Banned tokens** — no residual GRE-era names (word-bounded GRE, gre.json,
   gre_monthly) and no Mapbox GL imports anywhere in tracked source. Failure:
   naming or stack regression.
6. **Licence and attribution** — LICENSE and SOURCES.md exist and still carry
   the Caldara-Iacoviello citation. Failure: CC-BY obligation broken; blocks
   publish.
7. **Vendored assets** — every file `web/vendor/MANIFEST.json` lists exists
   under `web/vendor/` with the recorded byte count and sha256, every licence
   file the manifest names is present, nothing under `web/vendor/` is
   missing from the manifest, and neither `index.html` nor `story.html`
   carries a `<script src>`, `<link href>`, preconnect, `@import`, `url()`
   or `fetch()` pointing at `http(s)://`. Failure: a library or font was
   upgraded or altered without its manifest entry, or a CDN / Google Fonts
   tag crept back — either way the zero-third-party-request claim in
   README and `CLAUDE.md` (invariant 1) no longer holds.
8. **Export contract** — `index.html` still has the CSV/JSON export machinery,
   its header block declares the citation, normalisation, channel mix,
   coverage and caution keys, the export columns cover every channel, the
   chart SVG export resolves CSS variables and burns in the citation and the
   not-a-forecast caution, and the GeoJSON export repeats attribution per
   feature and merges multi-feature economies. Failure: a downloaded file
   leaves the page without its caveats or its licence line.
9. **Reverse map (source attribution)** — the attribution function, the
   lazily fetched `weights.json`/`gpr.json`, the month-grid guard, the
   chokepoint residual disclosed on the panel, in exports, in the PNG and in
   the Sankey (middle column, shared scale and gap budget, expanded dialog,
   focus handling, aria-labels). Failure: an attribution presented as complete
   when the chokepoint share is unattributable.
10. **Provenance** — README's generated block carries the series digest of
   `web/data/gpr.json`, the data month and the workbook digest (or says it is
   not recorded), and states that it is generated. Failure: the README
   describes a payload other than the one published.
11. **Pipeline guards** — 03 has `guard_no_regression`, `--allow-regression`
    and a non-zero exit; 01 refuses to publish a shorter `gpr.json`, offers
    `--allow-regression` and `--stamp-only`. Failure: a stale working tree can
    silently shorten the published data.
12. **Export contract (map)** — `preserveDrawingBuffer` is set only inside
    `canvasContextAttributes` (where MapLibre 5 reads it), the PNG export
    exists and its footer copies the legend's real breaks and the citation.
    Failure: the PNG export returns a blank canvas or an unsourced picture.
13. **Map coverage** — every economy in every payload maps to a paintable
    feature id in the vendored TopoJSON, no `NUM_TO_A3` entry is dead, and the
    render loop skips id-less features. Failure: an economy silently stops
    being coloured.
14. **Methods-review contract** — `intensity.json` carries
    `weights_anachronistic_through` (YYYY-MM, derived from `weight_years` by
    the vintage rule), `choke_littorals` (equal to `chokepoints.csv` filtered
    to states with a GPR series, recomputed here from the CSV and `gpr.json`)
    and `choke_self_excluded` (exactly the sole-covered-littoral pairs among
    trade-channel economies, recomputed the same way), and no `top_sources`;
    `index.html` has the coverage toggle (`btnCovRaw`/`btnCovNorm`/`covNote`),
    the legend `vintageNote`, the `coverage_normalisation` and
    `anachronistic_weights` export headers, the `weight_vintage`/
    `weights_anachronistic` columns, and `covnorm: false` inside the state
    block; METHODOLOGY has unique `## N.` headings, 5.7 and 5.8, and lists the
    export columns in the order `EXPORT_CHANNELS` in `index.html` implies;
    SOURCES names WITS, TiVA and UN Comtrade; the committed validation report
    agrees with the payload; and **the validation summary**
    `web/data/validation.json` (kind `validation_summary`, written by 04)
    carries the report's T1, T2, T4 and anachronism figures to three decimals,
    while `story.html` fetches it and carries the `data-stat` hooks (T1 mean
    and month count, each T2 pair above 0.9, T4 residual and mobility) that
    it fills. Failure: a documented number or field drifted from the code — fix
    the divergence, never the check.

## Rules

- Never mark work done while this fails; fix or explicitly report the failure.
- If a check is wrong because the schema legitimately evolved, update
  verify.py and CLAUDE.md in the same commit as the schema change.
- After changing 03_build_intensity.py, also re-run
  `python3 pipeline/04_validate.py` and read the report — a validation
  regression is a finding to surface, not noise to suppress.
