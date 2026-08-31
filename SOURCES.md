# Data sources and licences

Every source below is open. No paid API, no scraping, no licensed archive.
That constraint is deliberate: it keeps the project reproducible by a reviewer
and keeps it legally clean.

---

## Core risk measure

| Source | Content | Licence | Access |
|---|---|---|---|
| Caldara & Iacoviello GPR | Country-specific GPR, 44 countries, monthly 1900/1985–present | **CC-BY** | [matteoiacoviello.com/gpr.htm](https://www.matteoiacoviello.com/gpr.htm) — direct `.xls` / `.dta` download |
| GPR daily recent | Global GPR, daily, updated Mondays | CC-BY | Same site |
| AI-GPR | LLM-scored GPR, daily, 1960–2025 | Check on release | [Iacoviello & Tong (2026)](https://www.matteoiacoviello.com/research_files/AI_GPR_PAPER.pdf) — country-level series not confirmed available |

**Citation is mandatory under CC-BY.** See `METHODOLOGY.md` §6.

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

## Dependency weights

| Channel | Source | Licence | Notes |
|---|---|---|---|
| Trade | UN Comtrade | Free tier, rate-limited | Global coverage, annual/monthly |
| Trade (EU) | Eurostat Comext | Open | Finer product detail, monthly, better for EU-focused analysis |
| Energy | Eurostat `nrg_ti_*`, `nrg_bal_*` | Open | EU importers only |
| Energy (non-EU) | IEA energy balances | Partly paywalled | Free subset covers aggregates; check before relying on it |
| Critical raw materials | JRC RMIS | Open | Aligned to EU CRM Act list |
| Chokepoint volumes | EIA World Oil Transit Chokepoints | Public domain | Oil and LNG; not general cargo |
| Maritime trade | UNCTADstat | Open | Aggregate seaborne volumes |

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

| Library | Licence | Note |
|---|---|---|
| MapLibre GL JS | BSD-3-Clause | No token, no billing |
| D3 (d3-geo, d3-scale) | ISC | For projections and colour scales |

---

## Explicitly out of scope

- **Licensed newspaper archives** (ProQuest, Factiva, LexisNexis). Full-text
  historical archives are the binding constraint on any independent attempt to
  reconstruct or extend GPR. Not available to an individual on acceptable terms.
- **GDELT** as a GPR substitute. Free and multilingual, but noisy, with unstable
  event coding and known duplication problems. Usable as a cross-check on
  specific episodes; not as a primary series.
- **Commercial risk indices** (BlackRock, Verisk Maplecroft, Control Risks).
  Proprietary, unreproducible, cannot be redistributed. Useful only as
  qualitative benchmarks for face validity.
