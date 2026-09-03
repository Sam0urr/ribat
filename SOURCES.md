# Data sources and licences

Every source the pipeline reads is accessible without a paid API key, without
scraping and without a licensed archive. That constraint is deliberate: it
keeps the project reproducible by a reviewer. It is not the same as every
source being openly licensed — the licences differ and are stated per row, and
what this repository redistributes (derived shares, never raw records) follows
from them.

---

## Core risk measure

| Source | Content | Licence | Access |
|---|---|---|---|
| Caldara & Iacoviello GPR | Country-specific GPR, 44 countries, monthly 1900/1985–present | **CC-BY** | [matteoiacoviello.com/gpr.htm](https://www.matteoiacoviello.com/gpr.htm) — direct `.xls` / `.dta` download |
| GPR daily recent | Global GPR, daily, updated Mondays | CC-BY | Same site |
| AI-GPR | LLM-scored (GPT-4o mini) GPR from about 4.6 million NYT, Washington Post and Chicago Tribune articles, 1960–2025; country and directed country-pair decompositions in the paper | Check on release | [Iacoviello & Tong (2026)](https://www.matteoiacoviello.com/research_files/AI_GPR_PAPER.pdf) — public availability of country-level series unconfirmed |

**Citation is mandatory under CC-BY.** See `METHODOLOGY.md` §7.

Countries covered (44): Canada, Mexico, USA · Argentina, Brazil, Chile, Colombia,
Peru, Venezuela · Denmark, Finland, Hungary, Norway, Poland, Russia, Sweden,
Ukraine, United Kingdom · Belgium, France, Germany, Italy, Netherlands, Portugal,
Spain, Switzerland · Egypt, Israel, Saudi Arabia, South Africa, Tunisia, Turkey ·
Australia, China, Hong Kong, Japan, South Korea, Philippines, Taiwan, Indonesia,
India, Malaysia, Thailand, Vietnam.

Note the gaps: no Sub-Saharan Africa beyond South Africa, no Central Asia, no
Iran, no Iraq, no Nigeria. This constrains which exposure channels are
measurable — see `METHODOLOGY.md` §5.4.

---

## Dependency weights — joined

What the pipeline actually reads. Two sources, three scripts.

| Source | Used by | Content | Access | Licence and redistribution |
|---|---|---|---|---|
| **World Bank WITS (UN Comtrade data)** | `02_build_weights.py` (gross goods trade, `M+X`, WLD denominator), `02b_build_channel_weights.py` (product groups `Fuels` SITC 3 and `OresMtls` SITC 27+28+68, imports only) | Bilateral goods trade by reporter, partner, year and product group; benchmark years 2019, 2021, 2023 | WITS SDMX API, no key; 528 responses (264 by `02`, 264 by `02b`) cached under `data/raw/wits/` (gitignored) | UN Comtrade data are copyrighted by the United Nations and "made available for internal use only and may not be re-disseminated in any form without written permission of UNSD" ([WITS Terms and Conditions](https://wits.worldbank.org/WITS/wits/registration/PrintTermsAndCondition.htm); [UN Comtrade Policy on use and re-dissemination](https://uncomtrade.org/docs/policy-on-use-and-re-dissemination/)). Transformed data — "calculating new indicators … arithmetic calculations" — "is no longer subject to copyright restrictions", and free-of-charge visualisation and analytics applications need no permission ([UN Comtrade Help Center, FAQs on Use and Re-dissemination](https://uncomtrade.org/docs/faqs-on-use-and-re-dissemination/)). **What this repository does:** commits only derived bilateral shares (`data/processed/trade_weights.csv`, `channel_weights.csv`), never the raw records, which are gitignored and re-fetchable by the documented command. Cite as "UN Comtrade via World Bank WITS". **Decision (2026-09-03):** the same FAQ also says that re-disseminating transformed data should be backed by an active premium subscription; the maintainer decided not to seek confirmation from UNSD. The repository relies on the transformed-data clause and publishes derived shares only. |
| **OECD TiVA 2025 edition** | `02c_build_va_weights.py` | Origin of value added in final demand (`FDVA`), ICIO 1995–2022; benchmark years 2019, 2021, 2022 (2022 serves the 2023 vintage) | Dataflow `DSD_TIVA_FDVA@DF_FDVA` on `sdmx.oecd.org` (agency `sti-public`), no key; responses cached under `data/raw/` (gitignored) | OECD Open Access Policy: material published from 1 July 2024 is by default **Creative Commons Attribution 4.0 (CC BY 4.0)** ([OECD open-by-default policy](https://www.oecd.org/en/about/oecd-open-by-default-policy.html)). The [OECD Terms and Conditions](https://www.oecd.org/en/about/terms-conditions.html) (updated 1 July 2024) note that some data may carry third-party rights; TiVA is OECD-produced. Derived shares committed as `data/processed/va_weights.csv`. Citation: "OECD (2025), Trade in Value Added (TiVA) 2025 edition" and "Guide to OECD Trade in Value Added (TiVA) Indicators, 2025 edition, OECD 2025". |

The chokepoint channel joins no further source: it is derived from the WITS
trade weights and the hand-maintained littoral table
`data/reference/chokepoints.csv` (`METHODOLOGY.md` §3.4).

## Dependency weights — upgrade path

Not read by the pipeline. Each row is named in `METHODOLOGY.md` as the
construction that would replace or refine a shipped proxy.

| Channel | Source | Licence | Notes |
|---|---|---|---|
| Trade (EU) | Eurostat Comext | Open | Finer product detail, monthly; would replace WITS for EU reporters (§3.1) |
| Energy | Eurostat `nrg_ti_*`, `nrg_bal_*` | Open | Net imports by fuel type, EU importers only (§3.2) |
| Energy (non-EU) | IEA energy balances | Partly paywalled | Free subset covers aggregates; check before relying on it (§3.2) |
| Critical raw materials | JRC RMIS | Open | Material-level, aligned to the EU CRM Act list; would make the CRM slider independent of gross trade (§3.3, §5.8) |
| Chokepoint volumes | EIA World Oil Transit Chokepoints | Public domain | Oil and LNG; not general cargo (§3.4) |
| Maritime trade | UNCTADstat | Open | Aggregate seaborne volumes (§3.4) |
| Chokepoint transit calls | IMF PortWatch | Open (check terms) | Vessel-level transit counts per strait; would replace the hand-coded routing table (§3.4) |
| Value added, production side | OECD TiVA 2025, dataflow `DSD_TIVA_IMGRVA@DF_IMGRVA`, indicator `IMGR_BSCI` | CC BY 4.0 (as above) | Origin of value added in gross imports — the backward-linkage quantity §5.2 motivates; FDVA (joined) is the absorption-side one |
| National-press GPR | Banco de España, "Geopolitical Risk: A Database of General and Bilateral Indices" (Documentos Ocasionales 2603, 2026; doi 10.53479/42445) | "Reproduction for educational and non-commercial purposes permitted provided the source is acknowledged" — **not an open licence**; redistribution inside a payload not clearly permitted | 34 economies, national press in 15 languages via Factiva; monthly general and quarterly bilateral indices. Prior art for perceiving-side incidence and the input to a T5 vantage-bias check (§5.1) |

---

## Geometry

| Source | Content | Licence |
|---|---|---|
| Natural Earth 1:50m Admin 0 | Country polygons | **Public domain** |
| Natural Earth 1:110m | Lower-resolution alternative for faster load | Public domain |

Natural Earth is the correct choice over GADM or Eurostat GISCO here: public
domain, no attribution requirement, and it ships a disputed-boundaries treatment
that avoids taking a position the project does not need to take. Note that any
world map encodes contested claims — Crimea, Western Sahara, Kashmir, Taiwan.
State the boundary source in the interface and do not silently adjudicate.

---

## Rendering

Exactly what the two pages under `web/` load, and from where: everything is
served from the site's own origin, out of `web/vendor/`. Each file's byte
count and SHA-256 are recorded in `web/vendor/MANIFEST.json`, which the
verifier checks on every run. The library files are upstream's bytes,
unmodified, so their hashes can be recomputed against the source URL.

| Package | Version | Licence | Source URL | SHA-256 (vendored file) | Fetched |
|---|---|---|---|---|---|
| MapLibre GL JS (`maplibre-gl-5.24.0.js`, `maplibre-gl-5.24.0.css`) — a script and a stylesheet tag in `web/index.html` | 5.24.0 (what the unpinned `@5` tag resolved to on the fetch date) | BSD-3-Clause — `web/vendor/maplibre-gl-LICENSE.txt` | `https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.js`, `https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css` | js: `45a9b07a9189ce56054c620a947ccf41e291e58c95e9b61533b740aaa65ee5cb`<br>css: `ab1e70d59ec40465bae7e7030da2f3ccf28133fd502e62bd598eefbadfd7a732` | 2026-09-03 |
| topojson-client (`topojson-client-3.1.0.min.js`) — a script tag in `web/index.html`; decodes the vendored TopoJSON country file into GeoJSON features | 3.1.0 (what the unpinned `@3` tag resolved to) | ISC — `web/vendor/topojson-client-LICENSE` | `https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js` | `25cd02ae486cc5063e0215a4e4cfb15de83700c87ac48bac4d57dc6aaf3ebb89` | 2026-09-03 |
| Fraunces — variable (wght 300–900, opsz 9–144), roman and italic, `latin` + `latin-ext`; `web/story.html` only | Google Fonts API font version v38 | SIL Open Font License 1.1 — `web/vendor/fonts/Fraunces-OFL.txt` | CSS2 endpoint `https://fonts.googleapis.com/css2?family=Fraunces:…` (the full query is in `web/vendor/fonts.css`), files from `fonts.gstatic.com` (one URL per file, recorded in `web/vendor/MANIFEST.json`) | `Fraunces-italic-300-900-latin-ext.woff2`: `1e0d114a72921799f06413d3673a80c316fa77d8d344df6de7c8659302ece2dc`<br>`Fraunces-italic-300-900-latin.woff2`: `4af9c759c8059b53923b4b50ba377ba51029876e1af1ea757efb07bc67d97896`<br>`Fraunces-normal-300-900-latin-ext.woff2`: `f120089b9440f3e35a980a2137347b1851ad46ee4b8ad5c63b6c07e053fa40e2`<br>`Fraunces-normal-300-900-latin.woff2`: `48282a415ec22e31beaf0a0666e6fae0c8cbddcd0b1f6e729f27c3ade8a64e43` | 2026-09-03 |
| IBM Plex Sans — 300/400/500/600 roman (one shared file per subset: Google served identical bytes for the four weights), 400 italic, `latin` + `latin-ext`; `web/story.html` only | Google Fonts API font version v23 | SIL Open Font License 1.1 — `web/vendor/fonts/IBM-Plex-LICENSE.txt` | same CSS2 endpoint, files from `fonts.gstatic.com` (one URL per file, recorded in `web/vendor/MANIFEST.json`) | `IBMPlexSans-italic-400-latin-ext.woff2`: `f0d521828c0d91f2857f001f0ede42adb7b2c12520b00f1cbc1af16ae4fa1eeb`<br>`IBMPlexSans-italic-400-latin.woff2`: `134dc0ee94e70cf5d52f608a7ac4b864c9b00bdf69779b8919712ce89da253b1`<br>`IBMPlexSans-normal-300-600-latin-ext.woff2`: `ae1d854fefa1167a79071f1afe01d4d51b60c5840c1be36dd74bd5fe7375b405`<br>`IBMPlexSans-normal-300-600-latin.woff2`: `056e4e2459f57a0033c8c9c844ff19d6e42ac8602027803d4345823bcc939818` | 2026-09-03 |
| IBM Plex Mono — 400 and 500, `latin` + `latin-ext`; `web/story.html` only | Google Fonts API font version v20 | SIL Open Font License 1.1 — `web/vendor/fonts/IBM-Plex-LICENSE.txt` | same CSS2 endpoint, files from `fonts.gstatic.com` (one URL per file, recorded in `web/vendor/MANIFEST.json`) | `IBMPlexMono-normal-400-latin-ext.woff2`: `f1050dc5317b43434c0aeda599d4624c774ffc162e87a8cf204b949b6a85816d`<br>`IBMPlexMono-normal-400-latin.woff2`: `c36f509c0a8f9f85f29cb44bc8701d8a9e0b14c499e77a884f789ead7093a7ac`<br>`IBMPlexMono-normal-500-latin-ext.woff2`: `77f03e26f981c582bdba3a7abed4baa2d3149211c01366bb3ab3ba7622ec4ae5`<br>`IBMPlexMono-normal-500-latin.woff2`: `a76f53ca6612e7b3828eec2311098675b7f9849ae4169a8bcef6302aec02a6c0` | 2026-09-03 |

The map page loads no web font. The story page loads the three families
through `web/vendor/fonts.css`, which repeats Google's `@font-face`
declarations — `font-display: swap`, the variable axes, each block's
`unicode-range` — against the local files. Only the `latin` and `latin-ext`
subsets are vendored: the page's visible text stays within `latin` except for
the two marked letters of "Ribāṭ", which need `latin-ext`, and one rightwards
arrow (U+2192) that no Google subset covers and that falls through to the
fallback font as it did when Google served the fonts. MapLibre's script ends
with a relative `sourceMappingURL=maplibre-gl.js.map` comment; the map is not
vendored, so a browser with developer tools open makes at most a same-origin
404 and no request leaves the site. D3 is not used anywhere in `web/`.

Consequently neither page makes any third-party request at runtime — no CDN,
no font service, no tile server, API or tracker — which is the claim README
and `CLAUDE.md` (invariant 1) make. Upgrades happen by replacing the vendored
file and its manifest entry, never by a CDN or Google Fonts tag; the verifier
fails on any `http(s)://` script, stylesheet, preconnect, `@import` or `url()`
in either page, on any file under `web/vendor/` missing from the manifest, and
on any hash that no longer matches.

---

## Explicitly out of scope

- **Licensed newspaper archives** (ProQuest, Factiva, LexisNexis). Full-text
  historical archives are the binding constraint on any independent attempt to
  reconstruct or extend GPR. Not available to an individual on acceptable terms.
  (The Banco de España database above was built on Factiva by a central bank;
  the point stands for this project, which consumes published indices, never
  archives.)
- **GDELT** as a GPR substitute. Free and multilingual, but noisy, with unstable
  event coding and known duplication problems. Usable as a cross-check on
  specific episodes; not as a primary series.
- **Commercial risk indices** (BlackRock, Verisk Maplecroft, Control Risks).
  Proprietary, unreproducible, cannot be redistributed. Useful only as
  qualitative benchmarks for face validity.
