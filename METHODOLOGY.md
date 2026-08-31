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
input–output tables. This is a Phase 2 upgrade and is where the academic
contribution, if any, would sit.

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

---

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
