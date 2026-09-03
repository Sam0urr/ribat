# Methodology — Ribat Intensity Index

**Status:** draft v0.2, 2 September 2026
**Author:** S.

---

## 1. The gap this addresses

The Caldara–Iacoviello Geopolitical Risk (GPR) index and its country-specific
variants measure risk **emanating from or involving** a country, as recorded in
anglophone newspaper coverage. They are *source-side* measures.

Existing visualisations — including Saadaoui's November 2025 world map (the
January–September 2025 mean GPR, rebased to the 1985–2023 mean = 100; §7) and
the country charts on Iacoviello's own site — map that source-side quantity
directly onto country polygons. This is informative but analytically
incomplete: it tells you where instability is reported, not who bears its
economic consequences.

The second quantity is the **incidence** of geopolitical risk. A shock in the
Strait of Hormuz is a risk *in* Iran and Oman; it is a cost *to* Japan, Korea,
India and, through refined product and LNG channels, the European Union.
Incidence is not an open question: it is actively measured, but delivered as
regression coefficients in working papers rather than as an inspectable
instrument. Mulabdic and Yotov (World Bank Policy Research Working Paper 11219)
build trade-weighted partner GPR; the IMF's April 2025 *Global Financial
Stability Report*, chapter 2, traces cross-border GPR transmission through
trade and financial links; an ECB blog post of 28 November 2025 measures
central and eastern European exposure through Russian links and energy
reliance; Bank of England Staff Working Paper 1159 offers a regional
supply-chain exposure toolkit; Florence Working Paper 02/2026 constructs a
regional exposure index; Verschuur et al. (*Nature Communications*, 2025) and
IMF PortWatch measure physical chokepoint exposure; and Banco de España
Documentos Ocasionales 2603 (2026) measures bilateral geopolitical risk from
the perceiving side (§5.1). What this project adds is the same structure
delivered as an open, reproducible, multi-channel instrument: movable channel
weights, reverse attribution from an exposed economy back to its sources, and
displayed residuals wherever a construction falls short of its own identity.

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

The default mix the page opens with — 55 trade / 25 energy / 10 raw materials /
10 chokepoint — is an **illustrative starting point, not a derived weighting**.
Nothing in the data selects it; it is stated as such beside the sliders, and
the export header records the mix actually in force when a file was written.

Nor are the four sliders four independent channels. Validation test T2
(§5.8) finds that the raw-material proxy (WITS ores-and-metals import shares)
is near-collinear with gross trade: Spearman 0.922 between the CRM and trade
channels over economy-months, 0.937 between the trade channel's gross and
value-added bases, and 0.900 between CRM and value added. Gross import shares
of ores and metals track gross import shares of everything. The instrument
therefore has **three distinguishable channels** — a trade/value-added/CRM
bloc, energy, and chokepoint — and the fourth slider mostly re-labels the
first. The material-level CRM construction described as the upgrade path in
§3.3 is what would make that slider informative.

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
  countries. A consequence worth stating as an identity: the weights of a
  channel sum not to one but to the covered share, `Σ_j w^c_ij =
  covered_share^c_i`, so each channel value equals the covered share times the
  mean partner GPR over the partners GPR observes. §5.4 sets out what that does
  to the ranking and how the interface lets the reader undo it.
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
lag required by section 5.3. That rule has no answer for months before the
first benchmark year, and the pipeline then **falls back to the earliest
benchmark, which postdates them**: every month from January 1985 to December
2019 — 420 of the 500 months on the slider, 84.0% — is computed with 2019
weights, and 2019 itself is contemporaneous rather than lagged. Such months
answer "who would be exposed given the 2019 structure", not "who was exposed".
The payload records the last affected month in `weights_anachronistic_through`
(derived from the vintage map, never typed in) and the interface, the exports
and the validation report all flag it; §5.7 states the consequences.

### 3.2 Energy exposure

**Implemented (Phase 2):**

```
w^energy_ij = M^fuels_ij / M^fuels_i
```

*i*'s gross imports of fuels from *j* as a share of *i*'s gross fuel imports
from the world: WITS/Comtrade product group `Fuels` (SITC section 3 — coal,
oil, gas and electricity, undifferentiated), import side only, `WLD`
denominator, numerator restricted to the GPR-44. Dependency through a supply
channel is an import concept, so exports do not enter; otherwise the benchmark
years, denominator and Taiwan treatment are those of the trade channel. Mean
GPR-covered share of fuel imports is ~0.70, lower than the trade channel
because major energy exporters (Nigeria, Kazakhstan, Qatar, UAE, Iraq,
Algeria) have no GPR series — the energy channel therefore *understates*
exposure for their customers, and the covered share is reported so the reader
can see by how much (it falls to 0.09 for the thinnest economy; §5.4).

Two things the implemented measure gets wrong in a known direction. It is
**gross**, so it overstates dependency for refining and transit hubs — the
Netherlands and Belgium import crude and products they re-export, and the
share registers as their own exposure. And it is **undifferentiated**, so a
pipeline-gas dependency and a seaborne-crude dependency, which respond to very
different shocks, are summed as one.

**Upgrade path:**

```
w^energy_ij = E_ij / E_i
```

the share of *i*'s **net** energy imports sourced from *j*, computed separately
for crude oil, refined products, natural gas (pipeline) and LNG, then
aggregated by gross-inland-consumption share. Sources would be Eurostat
`nrg_ti_*` and `nrg_bal_*` for EU members and IEA energy balances for the rest.

### 3.3 Critical raw materials

**Implemented (Phase 2):**

```
w^crm_ij = M^ores_ij / M^ores_i
```

*i*'s gross imports of ores, minerals and non-ferrous metals from *j* as a
share of *i*'s gross imports of the same from the world: WITS/Comtrade product
group `OresMtls` (SITC 27 + 28 + 68), import side only, same denominator and
Taiwan treatment as the trade channel. This is a **proxy**: broader than the
EU Critical Raw Materials Act list (it includes bulk commodities such as iron
ore), blind to criticality, and — as T2 shows (§2, §5.8) — near-collinear with
gross trade shares, so the slider does not yet move the index independently.
It is used because it is the finest open cut available from the same source as
the other channels. No concentration measure is computed anywhere in the
pipeline or the interface.

**Upgrade path:**

```
w^crm_ij = Σ_m  s_m,i  ·  (I_ijm / I_im)
```

where *m* would index materials on the EU Critical Raw Materials Act list,
`I_ijm` *i*'s imports of material *m* from *j*, and `s_m,i` a criticality
weight for material *m*. Supply concentration would be reported alongside as a
Herfindahl–Hirschman index so that concentration and risk could be read
separately rather than conflated. Sources would be the JRC Raw Materials
Information System (RMIS) and Comext at HS-6.

### 3.4 Chokepoint transit

Not a bilateral weight. For each maritime chokepoint *p* (Hormuz, Bab el-Mandeb,
Suez, Malacca, Taiwan Strait, Panama, Danish Straits, Bosphorus):

```
w^choke_ip = (volume of i's seaborne imports transiting p) / (total seaborne imports of i)
G_p,t      = weighted mean GPR of p's littoral states
```

**Implemented (Phase 2, revised in the methods review):** per-importer transit
volumes do not exist as open data, so the transit share is approximated from
the gross bilateral trade weights and a coarse, hand-coded region-level routing
table (in `03_build_intensity.py`, auditable as code):

```
c_choke_i,t   = Σ_p [ Σ_j w^trade_ij · f_p(i,j) ] · G_p,t^(−i)
G_p,t^(−i)    = mean_{j ∈ L_p \ {i}}  G_j,t
```

where `f_p(i,j)` is the fraction of the pair's trade assumed to pass *p* (1.0
wherever a route is assigned, with one exception below), `L_p` is the set of
*p*'s GPR-covered littoral states (`data/reference/chokepoints.csv`), and
intra-regional pairs transit nothing (largely overland or short-sea). Six
chokepoints are tracked — the Red Sea corridor (Suez + Bab el-Mandeb as one),
Hormuz, Malacca, the Taiwan Strait, the Bosphorus and the Danish Straits.
Panama is *excluded*: no littoral or proximate state has a GPR series. The
chokepoint channel always uses the gross trade weights, whichever basis the
trade channel is displayed on.

*Self-exclusion.* The bilateral channels exclude an economy's own GPR by
construction — `w_ii` is not a trade share. Until the methods review the
chokepoint channel did not: Saudi Arabia's Hormuz term was `Σ_j w_SAU,j ×
G_SAU`, China carried its own GPR through the Taiwan Strait, and Egypt its own
through the Red Sea. Taiwan could not: it is not a Comtrade reporter, so it has
no chokepoint channel and enters the strait only as a littoral. Only Saudi
Arabia, China and Egypt carried their own GPR. That leak is why Saudi Arabia
topped the October 2023 Red Sea event study (+151 index points) and why its
own GPR correlated 0.95 with its own chokepoint channel. The littoral mean now
**excludes the exposed economy**: `G_p,t^(−i)` averages over `L_p \ {i}`. Where
nothing remains — the economy was the strait's only covered littoral — that
strait contributes nothing to that economy's chokepoint channel. This is the
case for Saudi Arabia at Hormuz and for Turkey at the Bosphorus; both pairs are
computed by the pipeline, never hard-coded, and shipped in the payload as
`choke_self_excluded` (`{"SAU": ["hormuz"], "TUR": ["bosphorus"]}`) so the
detail panel can say so. After the change Saudi Arabia's own-GPR correlation
with its chokepoint channel falls from 0.95 to 0.50 and China's from 0.70 to
0.62 (Pearson, months from 2020-01, the same panel as §5.8); Saudi Arabia's
rebased chokepoint value at 2023-10 falls from 270 to 158, and the economies
leading the Red Sea event study are Ukraine and Israel, whose traffic the
corridor actually carries.

*Fractional transit for China.* Mainland China straddles the Taiwan Strait, so
only part of its long-haul westbound trade passes it. The fraction is set at
`f = 0.7`, the share of 2024 container throughput at ports north of the strait
in the China Ministry of Transport's 2024 port statistics: north — Dalian,
Yingkou, Tangshan, Huanghua, Qinhuangdao, Tianjin, Qingdao, Rizhao, Yantai,
Shanghai, Lianyungang, Nantong, Ningbo-Zhoushan, Wenzhou, Fuzhou and the
Yangtze-basin river ports, 21,564 万TEU; south — Shenzhen, Guangzhou, Zhuhai,
Shantou, Zhanjiang, Beibu Gulf, Haikou, Yangpu, the Pearl River and Guangxi
river ports and Xiamen (at the strait's southern mouth, counted south), 9,777
万TEU; north share 21,564 / 31,341 = 0.69, carried as 0.7 because the table is
region-coarse and TEU is a container proxy for all goods trade. The full port
table is in the code comment. The fraction applies whether China is the
exposed economy or the partner: it describes where the cargo is loaded, not
who owns it. Every other assigned route carries 1.0.

*Routing table as it now stands.* Europe, Ukraine and Russia ↔ Asia and
Oceania: the Red Sea corridor, plus Malacca for East and South-East Asia;
Russia ↔ East Asia is the exception and transits nothing (overland rail and
the Pacific). The Mediterranean Middle East — Israel, Egypt, Turkey, Tunisia —
↔ East, South-East and South Asia, Oceania and Africa: the Red Sea corridor.
This block did not exist before the review, so Israel ↔ Asia was assigned
Malacca but never Suez; the evidence for it is that roughly 98% of Israel's
trade is seaborne, all of its containers move through Haifa and Ashdod on the
Mediterranean, and about a quarter of its trade is "with the East" via Suez;
Turkey and Tunisia are Mediterranean states; Egypt is the canal state, and its
own GPR is removed from its Red Sea term by the self-exclusion rule. Saudi
Arabia is deliberately outside that block: its Asia trade is Gulf-coast, so it
keeps Hormuz always, the Red Sea for European, Ukrainian and Russian partners
and Malacca for East and South-East Asian ones, and gets no Red Sea for Asia
(nor for the Americas, where the Cape and trans-Atlantic routes are too
ambiguous to assign). East and South-East
Asia ↔ South Asia, the Middle East and Africa: Malacca — westbound traffic
from Port Klang, Laem Chabang and the Vietnamese ports; before the review
South-East Asia ↔ South Asia and ↔ Middle East / Africa were assigned nothing.
Indonesia's Sunda and Lombok alternatives mean this slightly overstates for
IDN. Taiwan Strait: economies whose ports lie north of or at the strait —
China, Korea, Japan, Taiwan — ↔ Europe, the Middle East, South Asia, Africa
and Ukraine (not Russia: Russia ↔ East Asia transits nothing, by the early
return noted above, so no such pair ever reaches the strait rule in
`transit()`). **Hong Kong was removed from that northern set**: it sits
in the Pearl River delta, south of the strait, and its westbound traffic
leaves through the South China Sea without touching it; listing it was an
outright error. South-East Asia ↔ China is explicitly *not* assigned the
strait (South China Sea traffic). Danish Straits: Finland, Sweden, Poland and
Russia ↔ anything outside Europe/Russia. Bosphorus: Ukraine ↔ anything outside
Europe/Russia.

*Known omissions, left as they are because the table is region-level:*
south-China ↔ Americas traffic also uses the Taiwan Strait northbound (Lloyd's
List, 5 August 2022) and is not assigned; Taiwan itself is coded 1.0 although
Kaohsiung sits at the strait's southern end. And the littoral sets remain
thin: several true littorals (Iran, Oman, UAE, Yemen, Singapore) lack GPR
series, so the channel systematically **understates** — most severely for
Hormuz, whose only covered littoral is Saudi Arabia, which now means the Gulf's
own risk complex reaches Hormuz users through Saudi GPR alone and reaches Saudi
Arabia itself not at all. The validation report (T1 per channel, T3 self-
exclusion notes) states which economies are affected at each strait.

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

The Level question is answered less cleanly than the table suggests. A
country's article share scales with how much the ten anglophone newspapers
cover that country at all, so a cross-country comparison of levels is
confounded by press coverage: a state that is written about constantly
carries a high level in calm times, and one that is rarely covered registers a
low level through a crisis. Caldara and Iacoviello note this themselves.
Rebasing removes the confound — each country is compared with its own history,
so its coverage share cancels — and in doing so introduces the opposite
problem below. Both cautions are stated in the interface, in the note beside
the normalisation control.

A further caution applies to **Intensity** (as opposed to source-side GPR): rebased
Intensity is a *weighted sum* of partner-rebased series, so it has no natural
"100 = normal" anchor — an economy trading mostly with chronically elevated
partners sits structurally above 100. The map therefore colours Intensity by
percentile rank across economies, and reserves fixed breaks (anchored at 100)
for source-side GPR only.

Rebasing removes persistent level differences between countries. That is
desirable when detecting deterioration, and misleading when comparing across
countries: a chronically high-risk state rebases to ~100 in normal times and
therefore looks calm. Saadaoui's map uses rebasing (to the 1985–2023 mean;
§7). Defaulting to it without saying so is the single most common error in
this literature's visual output.

---

## 5. Known limitations

These belong in the interface, not buried in a footnote. Each is a real
constraint on interpretation.

**5.1 Media vantage bias.** GPR is constructed from ten anglophone newspapers.
It measures the *salience of geopolitical risk to a Western readership*, not
risk in any objective sense. Events in states with thin Western press coverage
are systematically understated. Intensity inherits this bias fully; weighting by
trade does not correct it.

An earlier draft of this section claimed that the obvious remedy — GPR built
from national-language press — would merely substitute one vantage point for
another, and that archive licensing made it impractical in any case. That was
overstated. A multilingual, national-source GPR now exists: Alonso-Alvarez,
Bukina, Diakonova, Khitarishvili, Pérez and Piqueras (2026), "Geopolitical
Risk: A Database of General and Bilateral Indices", Banco de España Documentos
Ocasionales 2603, doi 10.53479/42445. It covers 34 economies from their own
national press via Factiva in 15 languages, with monthly general indices
(start years vary from 1977 for the United States to 2014–2017 for Egypt, Iran
and Nigeria) and quarterly bilateral indices toward four origins — Russia,
China, the Western bloc and MENA. The series are downloadable
(`GPR_DBGlobal.xlsx`, `GPR_DBGlobal_Bilateral.xlsx`) from
https://www.bde.es/wbe/en/areas-actuacion/analisis-e-investigacion/recursos/indices-de-riesgo-geopolitico-generales-y-bilaterales-para-34-economias-6075d2451c9da91.html.
The vantage-point problem is therefore no longer merely asserted; it is
*measurable*, by comparing the anglophone and national-press indices for the
same country over the same months.

It is not adopted as `G_j,t` here, for four reasons. (i) It measures risk *as
perceived in j's national media* — a perceiving-side object — whereas the
formula in §2 needs risk *emanating from j* as seen by its partners; the two
diverge exactly where the vantage bias is largest. (ii) Coverage only partly
overlaps: 25 of the 44 GPR countries are in both sets (ARG AUS BEL BRA CAN CHL
CHN COL EGY FRA DEU IND ITA JPN MYS MEX PHL POL PRT RUS ESP CHE THA GBR USA),
19 are not (DNK FIN HUN NOR SWE UKR NLD ISR SAU ZAF TUN TUR HKG KOR TWN IDN
VNM PER VEN), and start years vary. (iii) The bilateral indices are quarterly,
and the instrument is monthly. (iv) The licence permits "reproduction for
educational and non-commercial purposes … provided the source is
acknowledged", which is not an open licence; redistributing the series inside
a web payload is not clearly permitted, and this project ships only what it
may redistribute (SOURCES.md).

Upgrade path: a fifth validation test, T5, comparing the Caldara–Iacoviello
and Banco de España general indices for the 25 overlapping countries — a
direct measurement of how much of `G_j,t` is vantage — and the Banco de España
bilateral indices as prior art for incidence measured from the perceiving
side, against which the source-side construction here can be checked.

**5.2 Direct exposure only.** Bilateral trade weights capture first-order
dependency. They miss exposure routed through third countries: a German
manufacturer importing intermediate goods from Poland which embody Russian
inputs registers as exposure to Poland. The correction is to compute weights
from value-added rather than gross flows, using OECD ICIO or WIOD
input–output tables.

**Implemented (Phase 3):** the interface offers a gross / value-added toggle
for the trade channel. Value-added weights are OECD TiVA `FDVA` ("origin of
value added in final demand", 2025 edition, annual, currently to 2022):

```
w^va_ij = FDVA_{j→i} / (FDVA_{W→i} − FDVA_{i→i})
```

The denominator is **foreign-only**: domestic value added — typically 60–80%
of an economy's final demand — is removed before shares are taken. Gross trade
weights have no domestic term (an economy is not its own trading partner), so
leaving `FDVA_{i→i}` in the denominator would make the toggle jump roughly
threefold for denominator reasons alone and the two bases could not be read
against each other. An earlier version of this section printed the formula
with the full denominator; the code has always used the foreign-only one.
Unlike the Comtrade-based weights, TiVA covers Taiwan, Russia and Venezuela as
final-demand economies, so the value-added basis has no carried-forward
weights. Its benchmark years (2019, 2021, 2022) are mapped to month vintages
by the same latest-benchmark-before-*t* rule, 2022 serving the 2023 vintage.

What FDVA measures must be stated precisely, because it is not quite the
quantity the paragraph above motivates. FDVA is the origin of the value added
embodied in *i*'s **final demand** — what *i*'s consumers, investors and
government ultimately absorb, finished goods included. It looks through third
countries, so Russian value added reaching Germany inside Polish intermediates
is attributed to Russia; that is the look-through the toggle is for. But it is
an absorption-side object, not a production-side one: it does not measure what
German *producers* use as inputs. The backward-linkage quantity the German
manufacturer example actually describes is the origin of value added in
*gross imports* — OECD TiVA 2025 dataflow `DSD_TIVA_IMGRVA@DF_IMGRVA`,
indicator `IMGR_BSCI` (value added in gross imports by importing country and
partner, broken down by the country where the value added originated; Guide
to OECD TiVA Indicators 2025, §7.2). That production-side cut is the upgrade
path; the basis note in the interface says which object it currently shows.

Divergence between the two bases is still informative on those terms: where
value-added exposure exceeds gross exposure, the value added *i* absorbs from
*j* is arriving through intermediary economies rather than directly, which is
exactly the exposure gross bilateral weights cannot see.

**5.3 Endogeneity of the weights.** Trade shares respond to risk. An economy
that has successfully de-risked shows *low* exposure precisely because risk was
*high* — the measure inverts where it should be most informative. Mitigation:
lag weights by *k* periods and report results against pre-shock benchmark
shares (e.g. 2019 or 2021 for Russia-related exposure). Do not use contemporaneous
weights.

**5.4 Coverage.** Country-specific GPR exists for 44 countries. Every channel
restricts its numerator to those 44 while keeping the world total as its
denominator (§3.1), so a channel's weights sum to the covered share rather than
to one, and the identity

```
c^ch_i,t  =  Σ_j w^ch_ij · G_j,t  =  covered_share^ch_i  ×  E[ G_j,t | j observed ]
```

holds for trade, value added, energy and raw materials. An economy whose
partners are mostly outside the GPR set — notably in Sub-Saharan Africa and
Central Asia — therefore carries a low value for a coverage reason, not an
exposure one. This is not merely a downward bias: because the map colours
Intensity by **percentile rank**, it is a **ranking confound**. Two economies
with identical partner risk and covered shares of 0.9 and 0.5 differ 1.8× and
sit in different bins. Measured on the shipped payload at its last month
(2026-08) under the default mix, the rank correlation between as-observed
Intensity and Intensity divided by covered share is 0.74; Saudi Arabia moves
from rank 42 to 17, South Africa from 30 to 12, Israel from 31 to 16, while
Mexico falls from 8 to 23 and Canada from 10 to 25 (of 42). (On the payload
the review examined, before the chokepoint channel was rebuilt, the figures
were 0.70 and 42→13, 30→11, 35→17, 7→24, 9→25.)

The interface therefore offers a **coverage toggle**. *As observed* (the
default) shows the identity's left-hand side, which is what the data measure.
*Per observed dependency* divides each channel value by its covered share,
recovering `E[G_j,t | j observed]` — the mean partner risk over the dependency
GPR can see — so that thinly and thickly covered economies rank on comparable
terms. Two caveats travel with it. Dividing by a thin covered share amplifies
noise in proportion: energy coverage falls to 0.09 for the thinnest economy,
where the division multiplies a few observed partners' GPR elevenfold. And the
chokepoint channel has no coverage measure at all (its weight is a routing
indicator, not a share of an observed flow; §6), so it is never divided and
`covered_choke` is blank. The covered share is reported next to every channel
value in the detail panel and in every export, and the export header records
which mode produced the file (`coverage_normalisation`; §6), because a
per-observed-dependency file read as an as-observed one would be wrong by the
covered share on every row.

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
Measured across every economy-month in the shipped payload (42 economies with
a default-mix channel × 500 months), the resulting discrepancy is at most about
2 parts in 10,000 (worst observed: SAU 1998-04, 1.7e-4 relative; median 2e-5).
It is invisible at the one-decimal percentages shown and is a rounding artefact
of the payload, not a coverage gap: no source is dropped, and the per-channel
weight blocks reconstruct their channel value to the same tolerance.

Percentages in the routing tooltips use adaptive precision for this reason. At a
fixed two decimals the smallest of 43 un-pooled sources round to `0.00%`, and the
displayed contributions then visibly failed to sum to the displayed attributed
share — a chart whose subject is an unreconciled residual cannot afford a second,
accidental one.

**5.7 Weight vintages before 2020 are anachronistic.** The lag rule of §3.1
and §5.3 — each month uses the latest benchmark strictly before it — has
nothing to return for months before the first benchmark year, and
`weight_year_for` then falls back to the earliest benchmark. With benchmarks at
2019, 2021 and 2023, every month from 1985-01 to 2019-12 is joined to the 2019
cross-section: **420 of the 500 months on the slider, 84.0%**, are computed
with weights that postdate them, and the twelve months of 2019 use
contemporaneous rather than lagged weights. The lag rule is genuinely in force
only from 2020-01.

Those months are not wrong, but they answer a different question. For
2001-09 or 1990-08 the map shows **who would be exposed to that month's risk
given the 2019 dependency structure**, not who was exposed at the time: the
Soviet Union's trading partners, pre-WTO China, pre-Maastricht Europe are all
rendered with the trade map of 2019. Read as a counterfactual — today's
dependencies under yesterday's risk — the early slider is informative; read as
history it is not. The endogeneity concern of §5.3 also runs the other way
here: 2019 shares already embody every de-risking decision taken in response
to the risks the earlier months display.

The condition is computed, not typed in. The pipeline derives the last
affected month from the vintage map and emits it as
`weights_anachronistic_through` (`"2019-12"` for the current benchmark set);
the validation report recomputes it independently from `trade_weights.csv` and
confirms the payload agrees. Every month at or before that value is flagged in
four places: the legend carries a caption naming the benchmark vintage in force
and, for such months, a warning that it postdates the month; the detail panel
repeats the warning beside the vintage line; every export row carries
`weight_vintage` and `weights_anachronistic`, the header block carries an
`anachronistic_weights` line, and the SVG and PNG captions carry the same
sentence (§6); and the validation report's event studies print a warning under
every event dated in or before the first benchmark year. The remedy is data
entry, not code: earlier benchmark cross-sections (WITS reaches back to the
1980s for most reporters) would extend the properly lagged range backwards one
vintage at a time.

**5.8 Channel discrimination — and whether the ranking moves.** Two of the
validation tests in `04_validate.py` bear on how the instrument may honestly be
described, and their results are stated here rather than left in the report.
Both use months from 2020-01, the first properly lagged vintage (§5.7).

*T2 — are the sliders four channels?* Spearman correlation between channels
over economy-months, rebased values: trade–CRM 0.922, trade–value added 0.937,
CRM–value added 0.900; energy against the three of them 0.746–0.778; chokepoint
against every other channel 0.20–0.29; mean off-diagonal 0.604. At a
collinearity threshold of 0.9 the channels form **three blocs, not four**:
trade / value added / CRM; energy; chokepoint. The CRM proxy is gross import
shares of ores and metals, and those track gross import shares of everything;
the value-added basis is, as intended, a re-measurement of the same trade
channel. Energy and the chokepoint channel are the two the mix can actually
move. The report names the pairs above the threshold each time it runs, so a
future CRM construction that breaks the bloc will show up as a fourth.

*T4 — static structure or time series?* T1 (own-GPR versus Intensity over
the same 80 months, mean cross-sectional Spearman 0.167 on the trade channel;
0.101 value added, 0.276 energy, 0.192 CRM, 0.185 chokepoint; own GPR read from
the same source 03 built Intensity from) shows that the cross-section differs
from source-side GPR. One per-economy figure in the chokepoint line deserves a
sentence, because a reader of T1-per-channel may take it for a leak: Israel's
own-GPR correlation with its chokepoint channel *rose* from 0.46 to 0.82 with
the self-exclusion change, because its new Red Sea route (§3.4) reads Egyptian
and Saudi GPR, which co-moves with Israel's own — regional co-movement among
littorals, not Israel's own series feeding back. T1 does not show that the
cross-section *moves*: if `INT_i,t ≈ α_i + γ_t`, the month slider recolours a
fixed dependency map by world risk and the monthly framing is not earned. T4
fits `y_it = μ + α_i + γ_t + ε_it` by two-way demeaning on the balanced panel
(42 economies, 80 months) and reports variance shares, with thresholds fixed
before the numbers were seen: residual below 0.10 static, 0.10–0.30 partly
dynamic, above 0.30 substantial economy-specific variation; mean 12-month rank
correlation above 0.90 means the ranking barely moves within a year.

For the default-mix Intensity the residual share is **0.138** (economy effects
0.084, month effects 0.779; 0.095 in log10) — partly dynamic — and the mean
Spearman between the cross-sectional ranking at *t* and at *t−12* is
**0.510**: the ranking does move within a year. The small economy-effect share
is expected rather than reassuring: rebasing centres every economy's series at
100 and removes between-economy level differences by construction, so the
month factor absorbs most of the variance and the residual and the mobility
are the informative figures. By channel: value added is the most
global-factor-like (residual 0.051, month share 0.937, mobility 0.318); trade
0.105 and 0.480; CRM 0.173 and 0.399; energy the most economy-specific
(residual 0.261, economy share 0.233, mobility 0.701). The **chokepoint
channel is the static one**: economy effects carry 0.583 of its variance and
its 12-month rank correlation is 0.963 — a fixed routing structure recoloured
by littoral GPR, which is what a hand-coded route table applied to slow-moving
trade weights should produce, and a reason to read the chokepoint layer as a
map of who *would* be hit rather than as a monthly signal. On the full
1985–2026 sample, under the §5.7 caveat, the default-mix residual is 0.109 and
the mobility 0.593; the chokepoint channel's mobility is 0.955.

What this licenses: the monthly framing is earned for the mixed index and for
the bilateral channels, partly — a material share of the month-to-month
variation is economy-specific and the ranking turns over within a year — but
the instrument is closer to "a dependency structure through which world risk is
read" than to a set of independent national time series, and the chokepoint
layer is structural. The interface's language should not outrun that. The
figures the story page (`web/story.html`) quotes from T1, T2 and T4 are not
typed there: `04_validate.py` writes them to `web/data/validation.json`
alongside the report and the page reads that file at load, so they cannot go
stale between monthly refreshes.

---

## 6. Export contract

The interface offers two downloads: a **cross-section** (every exposed economy
at the selected month) and a **time series** (one economy, all months), in CSV
or JSON. Both share one column set, so the two shapes cannot drift apart:

`iso3, name, month, intensity, c_trade, c_va, c_energy, c_crm, c_choke,
covered_trade, covered_va, covered_energy, covered_crm, covered_choke,
weights_stale, weight_vintage, weights_anachronistic`

`intensity` is the mixed index under the channel weights, normalisation and
coverage mode in force when the file was written; `c_*` are the per-channel
components *before* the mix, so a reader can re-derive `intensity` or
re-weight it themselves. The `c_*` columns are emitted **as displayed**: with
the coverage toggle on they are already divided by `covered_*`, so `intensity`
re-derives from them in either mode, and the header says which mode produced
the file. `weight_vintage` is the benchmark year each row's weights are joined
to and `weights_anachronistic` is `true` where that benchmark postdates the
row's month (§5.7).

A downloaded file leaves this interface and loses every caveat the panels
carry, so each one opens with a header block (`#`-prefixed lines in CSV, a
`meta` object in JSON) restating: the normalisation, the trade basis, the
channel mix actually applied, the data vintage and download date, the
lagged-benchmark weight rule and its pre-2020 fallback (`anachronistic_weights`:
which months use the earliest benchmark and what they therefore measure), the
coverage semantics below and the coverage mode in force
(`coverage_normalisation`: `as observed`, or `per observed dependency` with a
statement of which columns were divided), the not-a-forecast caution, and the
Caldara–Iacoviello CC-BY citation. Attribution is a licence obligation, not a
courtesy; `ribat-verify` fails if the header is stripped. The reverse-map
exports carry the same `coverage_normalisation` key.

The two panel charts — the Intensity series and the channel decomposition —
export as standalone SVG. The page styles them with CSS custom properties and
puts their key and caption in sibling elements, none of which survive the file
leaving the page, so the export resolves the variables to literals and redraws
the key, the normalisation, the weight-vintage rule, the stale-weight warning
where it applies, the coverage mode, the anachronistic-weights warning where it
applies, the not-a-forecast caution and the citation as text inside the figure.
A chart that travels without its caveats is the failure mode §5 exists to
prevent, so the figure is self-describing or it is not shipped.

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
break values actually displayed, the unit line, the channel mix, the coverage
mode and anachronism warning where they apply, the not-a-forecast caution and
the citation; the footer sizes itself to the wrapped text so nothing is clipped
at any capture width. Reading pixels back from a WebGL canvas requires
`preserveDrawingBuffer`, which costs memory on every page load whether or not
anyone exports — a standing charge accepted for this convenience, and the
reason the PNG was the last of the export formats to be built rather than the
first.

**Why `covered_choke` is always empty.** For trade, value added, energy and raw
materials, `covered_*` is the share of that channel's *denominator* observed by
the GPR-44 source set — a genuine fraction of a measured flow. The chokepoint
weight has no such denominator: it is a routing indicator derived from a coarse
hand-coded route table (§3.4), not a share of observed trade. Emitting a number
in that column would invite a comparison the construction does not support, so
the column is written blank and the header states the reason; for the same
reason the coverage toggle of §5.4 leaves `c_choke` untouched. The channel
understates by construction, most severely at Hormuz, whose true littorals are
almost entirely outside the GPR set. This is a documented absence, not a gap in
the pipeline.

---

## 7. Attribution

GPR data are open access under Creative Commons BY. Required citation:

> Caldara, Dario and Matteo Iacoviello (2022), "Measuring Geopolitical Risk,"
> *American Economic Review*, 112(4), pp. 1194–1225.

> Caldara, Dario, Sarah Conlisk, Matteo Iacoviello and Maddie Penn (2023),
> "Do Geopolitical Risks Raise or Lower Inflation?" (extends country coverage
> to 44 countries).

Data downloaded from https://www.matteoiacoviello.com/gpr.htm on 31 August 2026.

Note for the record: Iacoviello and Tong (2026) published the **AI-GPR Index**
(https://www.matteoiacoviello.com/research_files/AI_GPR_PAPER.pdf), which
applies GPT-4o mini to about 4.6 million *New York Times*, *Washington Post*
and *Chicago Tribune* articles, 1960–2025, producing graded rather than binary
risk scores. The paper contains country-level and directed country-pair
decompositions; whether the country series are publicly released is
unconfirmed. Should they be, they substitute directly for `G_j,t` in the
formula above with no change to the exposure framework — and the directed
pairs would, for the first time, allow a source-side bilateral `G_j→i,t` in
place of the country-level `G_j,t`.

The map referred to in §1 and §4 is Jamel Saadaoui, "Drawing an Interactive
Map for the Geopolitical Risks with Jupyter", 3 November 2025,
https://www.jamelsaadaoui.com/drawing-an-interactive-map-for-the-geopolitical-risks-with-jupyter/,
which maps the January–September 2025 mean of country GPR rebased to the
1985–2023 mean = 100.
