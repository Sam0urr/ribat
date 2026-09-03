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
| **World Bank WITS (UN Comtrade data)** | `02_build_weights.py` (gross goods trade, `M+X`, WLD denominator), `02b_build_channel_weights.py` (product groups `Fuels` SITC 3 and `OresMtls` SITC 27+28+68, imports only) | Bilateral goods trade by reporter, partner, year and product group; benchmark years 2019, 2021, 2023 | WITS SDMX API, no key; 528 responses (264 by `02`, 264 by `02b`) cached under `data/raw/wits/` (gitignored) | UN Comtrade data are copyrighted by the United Nations and "made available for internal use only and may not be re-disseminated in any form without written permission of UNSD" ([WITS Terms and Conditions](https://wits.worldbank.org/WITS/wits/registration/PrintTermsAndCondition.htm); [UN Comtrade Policy on use and re-dissemination](https://uncomtrade.org/docs/policy-on-use-and-re-dissemination/)). Transformed data — "calculating new indicators … arithmetic calculations" — "is no longer subject to copyright restrictions", and free-of-charge visualisation and analytics applications need no permission ([UN Comtrade Help Center, FAQs on Use and Re-dissemination](https://uncomtrade.org/docs/faqs-on-use-and-re-dissemination/)). **What this repository does:** commits only derived bilateral shares (`data/processed/trade_weights.csv`, `channel_weights.csv`), never the raw records, which are gitignored and re-fetchable by the documented command. Cite as "UN Comtrade via World Bank WITS". **Open flag:** the same FAQ also says that re-disseminating transformed data should be backed by an active premium subscription — an ambiguity to confirm with UNSD (comtrade@un.org) before any wider redistribution. |
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

Exactly what the two pages under `web/` load, and from where.

| Library | Licence | Loaded from | Note |
|---|---|---|---|
| MapLibre GL JS 5 (`maplibre-gl.js`, `maplibre-gl.css`) | BSD-3-Clause | `cdn.jsdelivr.net` — a script and a stylesheet tag in `web/index.html` | No token, no billing, no account |
| topojson-client 3 | ISC | `cdn.jsdelivr.net` — a script tag in `web/index.html` | Decodes the vendored TopoJSON country file into GeoJSON features |
| Google Fonts: Fraunces, IBM Plex Sans, IBM Plex Mono | SIL Open Font License 1.1 (the typefaces) | `fonts.googleapis.com` (stylesheet) and `fonts.gstatic.com` (font files), served by Google — `web/story.html` only | The map page loads no web font. Loading these **is a third-party request**: Google receives the reader's request for the stylesheet and the font files |

D3 is not used anywhere in `web/` and was removed from this table. Everything
above **is fetched from a third party at page load** — that is what the script,
stylesheet and font `<link>` tags do — so both pages do make third-party
requests at runtime. README and `CLAUDE.md` (invariant 1) therefore make the
narrower claim that holds: the map page makes no third-party *data* requests —
the country polygons and every payload are vendored under `web/data/` and no
tile server, API or tracker is contacted — and the story page adds only the
fonts. Whether to vendor the two libraries and the fonts is an open decision
for the maintainer, not yet taken.

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
