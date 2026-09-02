# Methodology — Ribat Intensity Index

**Status:** draft v0.1, 31 August 2026
**Author:** S.

---

## 1. The gap this addresses

The Caldara–Iacoviello Geopolitical Risk (GPR) index and its country-specific
variants measure risk **emanating from or involving** a country, as recorded in
anglophone newspaper coverage. They are *source-side* measures.

Existing visualisations — including Saadaoui's November 2025 world map and the
country charts on Iacoviello's own site — map that source-side quantity directly
onto country polygons. This is informative but analytically incomplete: it tells
you where instability is reported, not who bears its economic consequences.

The open question is the **incidence** of geopolitical risk. A shock in the
Strait of Hormuz is a risk *in* Iran and Oman; it is a cost *to* Japan, Korea,
India and, through refined product and LNG channels, the European Union. This
project constructs and maps that second quantity.

---

## 2. Definition

For an exposed economy *i*, a source country *j*, and month *t*:

```
INT_i,t  =  Σ_c  θ_c  ·  Σ_j  w^c_ij,t-k  ·  G_j,t
```

where

| Term | Meaning |
|---|---|
| `G_j,t` | Country-specific GPR of source country *j* in month *t* (44 countries available) |
| `w^c_ij,t-k` | Dependency weight of *i* on *j* through channel *c*, lagged *k* periods |
| `θ_c` | Channel weight, `Σ_c θ_c = 1`, **user-adjustable in the interface** |
| `c` | Channel index: trade, energy, critical raw materials, chokepoint |

The channel weights `θ_c` are deliberately exposed as controls rather than fixed.
There is no defensible single answer to how energy dependency trades off against
raw-material concentration; presenting one would be false precision. Making the
weights movable converts the interface from a claim into a sensitivity analysis,
which is both more honest and more useful.

---

## 3. Channels

### 3.1 Trade exposure

```
w^trade_ij = (M_ij + X_ij) / (M_i + X_i)
```

Bilateral goods trade as a share of *i*'s total goods trade.

**Source:** UN Comtrade, accessed via the World Bank WITS API (same underlying
data, no API key, and no 500-record truncation cap — the Comtrade free preview
caps at 500 rows, which is almost exactly one reporter's partner count).
Eurostat Comext remains the upgrade path for EU members (finer product detail,
monthly frequency).

Two construction details verified against the raw data (Aug 2026):

- **Denominator.** WITS `partner/all` responses include World Bank region and
  income aggregates (ECS, EAS, NAC, …) alongside countries; summing partners
  double-counts total trade by roughly 2x. The denominator is therefore the
  reported `WLD` total, and the numerator is restricted to the 44 GPR
  countries.
- **Taiwan.** Comtrade reports Taiwan only as "Other Asia, nes" (OAS). That
  bucket is overwhelmingly Taiwan and is remapped to TWN, so Taiwan enters Intensity
  as a risk *source*. It cannot enter as an exposed economy: it is not a
  Comtrade reporter.
- **Non-reporters.** Russia has no 2023 benchmark; an exact-year join drops it
  from the map for every month from 2024 onward, which reads to a viewer as a
  rendering fault rather than a data limitation. Weights are therefore carried
  forward from each economy's last reported benchmark, and the affected
  economies are named in the payload (`stale_weights`) and flagged in the
  detail panel. Carried-forward weights become less representative the further
  they are extrapolated — for Russia specifically, 2021 shares predate the
  reorientation of its trade, so its Intensity is best read as *exposure under
  its pre-invasion trade structure*, not its current one. Verified against the
  August 2026 data, Russia is the only affected economy.

**Benchmark years.** Weights are cross-sections at 2019 (pre-Covid), 2021
(pre-invasion) and 2023 (latest available in WITS; 2024 not yet published).
Each month *t* uses the latest benchmark strictly before *t*, implementing the
lag required by section 5.3.

### 3.2 Energy exposure

```
w^energy_ij = E_ij / E_i
```

Share of *i*'s net energy imports sourced from *j*, computed separately for crude
oil, refined products, natural gas (pipeline), and LNG, then aggregated by
gross inland consumption share.

**Implemented (Phase 2):** WITS/Comtrade product group `Fuels` (SITC section
3), import side only — dependency through a supply channel is an import
concept, so exports do not enter. Same benchmark years, denominator and Taiwan
treatment as the trade channel. Mean GPR-covered share of fuel imports is
~0.69, lower than the trade channel because major energy exporters (Nigeria,
Kazakhstan, Qatar, UAE, Iraq, Algeria) have no GPR series — the energy channel
therefore *understates* exposure for their customers, and the covered share is
reported so the reader can see by how much. The fuel-type decomposition above
is the upgrade path.

**Source (upgrade path):** Eurostat `nrg_ti_*` and `nrg_bal_*`; IEA energy balances for non-EU.

### 3.3 Critical raw materials

```
w^crm_ij = Σ_m  s_m,i  ·  (I_ijm / I_im)
```

where *m* indexes materials on the EU Critical Raw Materials Act list, `I_ijm` is
*i*'s imports of material *m* from *j*, and `s_m,i` is a criticality weight for
material *m*. Supply concentration is reported alongside as a
Herfindahl–Hirschman index so that concentration and risk can be read separately
rather than conflated.

**Implemented (Phase 2):** WITS/Comtrade product group `OresMtls` (SITC 27 +
28 + 68: ores, minerals and non-ferrous metals), import side only. This is a
**proxy**: broader than the EU CRM Act list (it includes bulk commodities such
as iron ore) and blind to criticality weighting. It is used because it is the
finest open cut available from the same source as the other channels; the
material-level construction above is the upgrade path.

**Source (upgrade path):** JRC Raw Materials Information System (RMIS); Comext at HS-6.

### 3.4 Chokepoint transit

Not a bilateral weight. For each maritime chokepoint *p* (Hormuz, Bab el-Mandeb,
Suez, Malacca, Taiwan Strait, Panama, Danish Straits, Bosphorus):

```
w^choke_ip = (volume of i's seaborne imports transiting p) / (total seaborne imports of i)
G_p,t      = weighted mean GPR of p's littoral states
```

**Implemented (Phase 2):** per-importer transit volumes do not exist as open
data, so the transit share is approximated from bilateral trade weights and a
coarse, hand-coded region-level routing table (in `03_build_intensity.py`,
auditable as code): `w^choke_ip = Σ_j w^trade_ij · 1{route(i,j) transits p}`,
with intra-regional pairs assumed to transit nothing (largely overland or
short-sea). Six chokepoints are tracked — the Red Sea corridor (Suez + Bab
el-Mandeb as one), Hormuz, Malacca, the Taiwan Strait, the Bosphorus and the
Danish Straits. Panama is *excluded*: no littoral or proximate state has a GPR
series. `G_p,t` is the mean GPR of each chokepoint's GPR-covered littoral
states (`data/reference/chokepoints.csv`); several true littorals (Iran, Oman,
UAE, Yemen, Singapore) lack GPR series, so the channel systematically
**understates** — most severely for Hormuz, which is proxied by Saudi GPR
alone.

**Source (upgrade path):** EIA chokepoint volumes; UNCTADstat maritime; IMF
PortWatch transit calls; littoral mapping maintained in
`data/reference/chokepoints.csv`.

---

## 4. Normalisation — and why it is a user choice

`G_j,t` is a share of newspaper articles. Two rescalings answer different
questions, and the interface should expose both rather than silently pick one:

| Mode | Formula | Question answered |
|---|---|---|
| **Rebased** | `G_j,t / mean(G_j, 1985–2023) × 100` | Is country *j* unusually risky *relative to its own history*? |
| **Level** | raw article share, common scale | Is country *j* riskier *than country k* right now? |

A further caution applies to **Intensity** (as opposed to source-side GPR): rebased
Intensity is a *weighted sum* of partner-rebased series, so it has no natural
"100 = normal" anchor — an economy trading mostly with chronically elevated
partners sits structurally above 100. The map therefore colours Intensity by
percentile rank across economies, and reserves fixed breaks (anchored at 100)
for source-side GPR only.

Rebasing removes persistent level differences between countries. That is
desirable when detecting deterioration, and misleading when comparing across
countries: a chronically high-risk state rebases to ~100 in normal times and
therefore looks calm. Saadaoui's map uses rebasing. Defaulting to it without
saying so is the single most common error in this literature's visual output.

---

## 5. Known limitations

These belong in the interface, not buried in a footnote. Each is a real
constraint on interpretation.

**5.1 Media vantage bias.** GPR is constructed from ten anglophone newspapers.
It measures the *salience of geopolitical risk to a Western readership*, not
risk in any objective sense. Events in states with thin Western press coverage
are systematically understated. Intensity inherits this bias fully; weighting by trade
does not correct it. The frequently proposed remedy — scraping multilingual
regional archives — substitutes one vantage point for another rather than
removing the problem, and full-text archive licensing makes it impractical for
an individual researcher in any case.

**5.2 Direct exposure only.** Bilateral trade weights capture first-order
dependency. They miss exposure routed through third countries: a German
manufacturer importing intermediate goods from Poland which embody Russian
inputs registers as exposure to Poland. The correction is to compute weights
from value-added rather than gross flows, using OECD ICIO or WIOD
input–output tables.
**Implemented (Phase 3):** the interface offers a gross / value-added toggle
for the trade channel. Value-added weights are OECD TiVA `FDVA` ("origin of
value added in final demand", annual, currently to 2022):
`w^va_ij = FDVA_{j→i} / FDVA_{W→i}`. Unlike the Comtrade-based weights, TiVA
covers Taiwan, Russia and Venezuela as final-demand economies, so the
value-added basis has no carried-forward weights. Its benchmark years (2019,
2021, 2022) are mapped to month vintages by the same latest-benchmark-before-t
rule. Divergence between the two bases is itself informative: where
value-added exposure exceeds gross exposure, dependency is being routed
through intermediary economies.

**5.3 Endogeneity of the weights.** Trade shares respond to risk. An economy
that has successfully de-risked shows *low* exposure precisely because risk was
*high* — the measure inverts where it should be most informative. Mitigation:
lag weights by *k* periods and report results against pre-shock benchmark
shares (e.g. 2019 or 2021 for Russia-related exposure). Do not use contemporaneous
weights.

**5.4 Coverage.** Country-specific GPR exists for 44 countries. Trade partners
outside that set enter with zero weight, biasing Intensity downward for economies
with heavily non-covered partners — notably in Sub-Saharan Africa and Central
Asia. Report covered-trade share alongside every Intensity value so the reader can see
how much of a country's dependency the index actually observes.

**5.5 Not a forecast.** GPR is a contemporaneous measure of reported risk.
Intensity is a contemporaneous measure of reported exposure. Neither predicts.

**5.6 How far the source attribution reconciles.** The reverse view decomposes
an economy's Intensity into bilateral contributions `theta_c * w^c_ij * G_j,t /
sum_c theta_c`, and the routing Sankey shows each of them as a band. Two
identities hold, and the interface asserts both, so both are stated here.

*Contributions sum to the attributed share, exactly.* Every band, the per-source
totals and the `attributedShare` figure are the same sum taken at different
levels of aggregation, so they agree to floating-point precision. What they do
*not* sum to is Intensity: the chokepoint channel carries no bilateral source
(§3.4) and is excluded from the numerator while remaining in the denominator, so
the attribution falls short by exactly `theta_choke * c_choke_i,t / sum_c
theta_c`. That residual is displayed as its own figure, marked on the diagram at
the point where it occurs, and is the quantity by which the Sankey's source
column ends short of its channel column.

*Attributed plus chokepoint recovers Intensity, to the payload's stored
precision.* The two are equal in construction but not bit-for-bit in the shipped
data: `web/data/intensity.json` stores the channel series rounded to two
decimals, whereas the bilateral weights reconstruct those channels unrounded.
Measured across 43 economies at several months, the resulting discrepancy is at
most about 1 part in 10,000 (worst observed: HUN 2005-11, 9.4e-5 relative).
It is invisible at the one-decimal percentages shown and is a rounding artefact
of the payload, not a coverage gap: no source is dropped, and the per-channel
weight blocks reconstruct their channel value to the same tolerance.

Percentages in the routing tooltips use adaptive precision for this reason. At a
fixed two decimals the smallest of 43 un-pooled sources round to `0.00%`, and the
displayed contributions then visibly failed to sum to the displayed attributed
share — a chart whose subject is an unreconciled residual cannot afford a second,
accidental one.

---

## 6. Export contract

The interface offers two downloads: a **cross-section** (every exposed economy
at the selected month) and a **time series** (one economy, all months), in CSV
or JSON. Both share one column set, so the two shapes cannot drift apart:

`iso3, name, month, intensity, c_trade, c_va, c_energy, c_crm, c_choke,
covered_trade, covered_va, covered_energy, covered_crm, covered_choke,
weights_stale`

`intensity` is the mixed index under the channel weights and normalisation in
force when the file was written; `c_*` are the per-channel components *before*
the mix, so a reader can re-derive `intensity` or re-weight it themselves.

A downloaded file leaves this interface and loses every caveat the panels
carry, so each one opens with a header block (`#`-prefixed lines in CSV, a
`meta` object in JSON) restating: the normalisation, the trade basis, the
channel mix actually applied, the data vintage and download date, the
lagged-benchmark weight rule, the coverage semantics below, the
not-a-forecast caution, and the Caldara–Iacoviello CC-BY citation. Attribution
is a licence obligation, not a courtesy; `ribat-verify` fails if the header is
stripped.

The two panel charts — the Intensity series and the channel decomposition —
export as standalone SVG. The page styles them with CSS custom properties and
puts their key and caption in sibling elements, none of which survive the file
leaving the page, so the export resolves the variables to literals and redraws
the key, the normalisation, the weight-vintage rule, the stale-weight warning
where it applies, the not-a-forecast caution and the citation as text inside
the figure. A chart that travels without its caveats is the failure mode §5
exists to prevent, so the figure is self-describing or it is not shipped.

The cross-section is also available as **GeoJSON**, built from the boundary
features the map already holds, so no second copy of the geometry ships and the
polygons are exactly those on screen. Properties reuse the CSV column names.
Two deviations are deliberate: attribution is repeated on every feature, because
RFC 7946 parsers may drop the top-level `metadata` member and losing the licence
line is not a cosmetic failure; and economies that Natural Earth carries as
several features (Australia) are merged into one MultiPolygon, so a join cannot
double-count them. There is no GeoJSON time series — the same polygon repeated
across 500 months is not a useful artefact.

The map is also exportable as **PNG**, as it appears. A bare canvas grab would
be a picture of colours with no scale, so a footer composites the ramp with the
break values actually displayed, the unit line, the channel mix, the
not-a-forecast caution and the citation; the footer sizes itself to the wrapped
text so nothing is clipped at any capture width. Reading pixels back from a
WebGL canvas requires `preserveDrawingBuffer`, which costs memory on every page
load whether or not anyone exports — a standing charge accepted for this
convenience, and the reason the PNG was the last of the export formats to be
built rather than the first.

**Why `covered_choke` is always empty.** For trade, value added, energy and raw
materials, `covered_*` is the share of that channel's *denominator* observed by
the GPR-44 source set — a genuine fraction of a measured flow. The chokepoint
weight has no such denominator: it is a routing indicator derived from a coarse
hand-coded route table (§3.4), not a share of observed trade. Emitting a number
in that column would invite a comparison the construction does not support, so
the column is written blank and the header states the reason. The channel
understates by construction, most severely at Hormuz, whose true littorals are
almost entirely outside the GPR set. This is a documented absence, not a gap in
the pipeline.

## 6. Attribution

GPR data are open access under Creative Commons BY. Required citation:

> Caldara, Dario and Matteo Iacoviello (2022), "Measuring Geopolitical Risk,"
> *American Economic Review*, 112(4), pp. 1194–1225.

> Caldara, Dario, Sarah Conlisk, Matteo Iacoviello and Maddie Penn (2023),
> "Do Geopolitical Risks Raise or Lower Inflation?" (extends country coverage
> to 44 countries).

Data downloaded from https://www.matteoiacoviello.com/gpr.htm on 31 August 2026.

Note for the record: Iacoviello and Tong (2026) published the **AI-GPR Index**,
which applies GPT-4o-mini to roughly 5 million NYT, Washington Post and Chicago
Tribune articles, 1960–2025, producing graded rather than binary risk scores.
Should AI-GPR country-level series be released, they substitute directly for
`G_j,t` in the formula above with no change to the exposure framework.
