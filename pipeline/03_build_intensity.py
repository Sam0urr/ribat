"""
03_build_intensity.py — join country GPR with channel weights into Intensity.

INT_i,t = sum_c theta_c * sum_j w^c_ij * G_j,t        (METHODOLOGY.md section 2)

Channels shipped:
  trade   02_build_weights.py        (M+X)/(M+X total), GPR-44 partners
  energy  02b (WITS product Fuels)   import shares
  crm     02b (WITS product OresMtls) import shares — CRM *proxy*
  va      02c (OECD TiVA FDVA)       alternative BASIS for the trade channel
  choke   derived: trade weights x hand-coded route transit x littoral GPR

The channel mix theta is NOT applied here: the web payload carries each
channel's contribution separately and the interface mixes them client-side,
so the sliders are a real sensitivity analysis rather than a re-run.

Chokepoint channel construction (METHODOLOGY.md section 3.4):
  transit(i,j) = {chokepoint: fraction} on the dominant sea route between i
                 and j, from a coarse region-level routing table (below).
                 Intra-region pairs get none (largely overland/short-sea). The
                 fraction is the share of the pair's trade assumed to pass the
                 strait: 1.0 everywhere except the Taiwan Strait for mainland
                 China (CHN_TS_FRACTION, derived from port throughput below).
  c_choke_i,t  = sum_p [ sum_j w_trade_ij * f_p(i,j) ] * G_p,t^(-i)
  G_p,t^(-i)   = mean GPR of the chokepoint's GPR-covered littoral states
                 EXCLUDING the exposed economy i itself. The bilateral channels
                 exclude i's own GPR by construction (w_ii is not a trade
                 share); until the methods review the chokepoint channel did
                 not: SAU's Hormuz term was w x G_SAU, CHN carried its own GPR
                 through the Taiwan Strait and EGY through the Red Sea, which
                 is why SAU topped the 2023-10 Red Sea event study. Where the
                 exclusion leaves no littoral (SAU at Hormuz, TUR at the
                 Bosphorus) the strait contributes nothing to that economy's
                 channel and the pair is listed in the payload field
                 choke_self_excluded so the interface can say so.
                 Several true littorals lack GPR series, so the channel
                 UNDERSTATES — see the notes in data/reference/chokepoints.csv.

Weight vintage: each month t uses the latest benchmark year strictly before t
(weight_year_for). Months before the first benchmark year have no such year
and FALL BACK to the earliest benchmark, which postdates them: with benchmarks
2019/2021/2023 every month through 2019-12 is computed with 2019 weights, and
2019 itself is contemporaneous rather than lagged. Those months answer "who
would be exposed given the 2019 structure", not "who was exposed". The payload
records the last such month in weights_anachronistic_through — derived from
the vintage map, never typed in — so the interface, the exports and
04_validate.py can flag it (METHODOLOGY.md section 5.7). Non-reporters carry
forward their last benchmark (flagged in stale_weights).

Input:  data/processed/gpr_country_monthly.csv     (01) or web/data/gpr.json
        data/processed/trade_weights.csv           (02)
        data/processed/channel_weights.csv         (02b, optional)
        data/processed/va_weights.csv              (02c, optional)
        data/reference/chokepoints.csv
Output: data/processed/intensity_monthly.csv
        web/data/intensity.json
        web/data/weights.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
REF = ROOT / "data" / "reference"
WEB = ROOT / "web" / "data"

START_YEAR = 1985

# ---------------------------------------------------------------------------
# Region-level sea-route table for the chokepoint channel. Deliberately coarse
# and fully auditable here; refining it is data entry, not code.
# ---------------------------------------------------------------------------
REGION = {}
for r, isos in {
    "AMER": ["USA","CAN","MEX","ARG","BRA","CHL","COL","PER","VEN"],
    "EUR":  ["BEL","CHE","DEU","DNK","ESP","FIN","FRA","GBR","HUN","ITA",
             "NLD","NOR","POL","PRT","SWE"],
    "RUS":  ["RUS"], "UKR": ["UKR"],
    "ME":   ["SAU","ISR","EGY","TUN","TUR"],
    "AFR":  ["ZAF"], "SASIA": ["IND"],
    "SEASIA": ["IDN","MYS","THA","VNM","PHL"],
    "EASIA": ["CHN","JPN","KOR","TWN","HKG"],
    "OCE":  ["AUS"],
}.items():
    for iso in isos:
        REGION[iso] = r

BALTIC_RIM = {"FIN", "SWE", "POL", "RUS"}

# North-east Asian economies whose ports lie north of, or at, the Taiwan Strait,
# so their traffic to Europe, the Middle East, South Asia and Africa passes it.
# HKG was in this set until the methods review: Hong Kong sits in the Pearl
# River delta, SOUTH of the strait, and its westbound traffic leaves via the
# South China Sea without touching it. Listing it was an outright error.
TS_NORTH = {"CHN", "KOR", "JPN", "TWN"}

# Mainland China straddles the strait, so only part of its long-haul westbound
# trade passes it. Fraction = share of 2024 container throughput at ports north
# of the strait (China Ministry of Transport, 2024 port statistics, 万TEU):
#   north: Dalian 540, Yingkou 556, Tangshan 272, Huanghua 85, Qinhuangdao 54,
#          Tianjin 2329, Qingdao 3087, Rizhao 671, Yantai 509, Shanghai 5151,
#          Lianyungang 669, Nantong 15, Ningbo-Zhoushan 3930, Wenzhou 145,
#          Fuzhou 381, Yangtze-basin river ports 3170                = 21,564
#   south: Shenzhen 3340, Guangzhou 2607, Zhuhai 128, Shantou 178,
#          Zhanjiang 165, Beibu Gulf 902, Haikou 166, Yangpu 200,
#          Pearl-River river ports 687, Guangxi river ports 179,
#          Xiamen 1225 (at the strait's southern mouth, counted south) =  9,777
#   north share = 21,564 / 31,341 = 0.69, carried as 0.7 because the routing
#   table is region-coarse and TEU is a container proxy for all goods trade.
# Applied whether CHN is the exposed economy or the partner: the fraction
# describes where China's cargo is loaded, not who owns it.
CHN_TS_FRACTION = 0.7

ASIA = {"EASIA", "SEASIA", "SASIA"}

# Mediterranean-coast Middle East. SAU is deliberately absent: its Asia trade
# is Gulf-coast (Hormuz), handled by its own rule below.
MED_ME = {"ISR", "EGY", "TUR", "TUN"}


def transit(i: str, j: str) -> dict[str, float]:
    """Chokepoints on the dominant sea route between i and j, each with the
    fraction of the pair's trade assumed to pass it (1.0 unless stated)."""
    a, b = REGION[i], REGION[j]
    if a == b:
        return {}
    pair: set[str] = {a, b}
    out: dict[str, float] = {}

    # Russia <-> East Asia moves overland (rail) and across the Pacific, not
    # through Suez. Treating it as a Europe-Asia sea route put Russia atop the
    # Red Sea event studies, which is not credible.
    if pair == {"RUS", "EASIA"}:
        return out

    # Europe/Med <-> Asia/Oceania: Suez corridor
    if pair & {"EUR", "UKR", "RUS"} and pair & (ASIA | {"OCE"}):
        out["red_sea"] = 1.0
        if pair & {"EASIA", "SEASIA"}:
            out["malacca"] = 1.0
    # Mediterranean Middle East <-> Asia/Oceania/Africa: also the Suez corridor.
    # Israel's trade is ~98% seaborne and its containers all move through
    # Haifa/Ashdod on the Mediterranean, with roughly a quarter of its trade
    # "with the East" via Suez; Turkey and Tunisia are Mediterranean states;
    # Egypt is the canal state (its own GPR is removed from its Red Sea term by
    # the self-exclusion rule in main()). Before the methods review this block
    # did not exist, so ISR <-> Asia got Malacca but never the Red Sea. SAU is
    # NOT in MED_ME and keeps its Hormuz(+Malacca) rule; no Red Sea for
    # SAU <-> Asia.
    if ({i, j} & MED_ME) and pair & (ASIA | {"OCE", "AFR"}):
        out["red_sea"] = 1.0
    # Gulf (SAU) shipping: Hormuz always; Suez only for European destinations.
    # Gulf <-> Americas is routed via the Cape or trans-Atlantic depending on
    # coast and is too ambiguous to assign, so it gets no Red Sea transit.
    if "SAU" in (i, j):
        out["hormuz"] = 1.0
        if pair & {"EUR", "UKR", "RUS"}:
            out["red_sea"] = 1.0
        if pair & {"EASIA", "SEASIA"}:
            out["malacca"] = 1.0
    # East / South-East Asia <-> South Asia / Middle East / Africa: Malacca.
    # For the South-East Asian reporters this is westbound traffic from Port
    # Klang, Laem Chabang and the Vietnamese ports. Indonesia's Sunda and
    # Lombok alternatives mean the rule slightly OVERSTATES for IDN. Until the
    # methods review SEASIA <-> SASIA and SEASIA <-> ME/AFR were assigned
    # nothing at all.
    if pair & {"EASIA", "SEASIA"} and pair & {"SASIA", "ME", "AFR"}:
        out["malacca"] = 1.0
    # Taiwan Strait: north-east Asian ports routing south or west. Explicitly
    # NOT assigned to South-East Asia <-> China flows: those run through the
    # South China Sea and bypass the strait entirely. Assigning them was a bug
    # that put Vietnam and Indonesia atop the 2022-08 Taiwan crisis event study
    # (see 04_validate.py T3). Mainland China gets the port-throughput fraction.
    # Known omissions, left as they are because the table is region-level:
    #   - south-China <-> Americas traffic also uses the strait NORTHBOUND
    #     (Lloyd's List, 5 Aug 2022) and is not assigned here;
    #   - TWN is coded 1.0 although Kaohsiung sits at the strait's southern end.
    # No "RUS" in this set: every TS_NORTH economy is EASIA, and RUS <-> EASIA
    # returned early above, so a Russian counterpart never reaches this rule.
    if ({i, j} & TS_NORTH) and pair & {"EUR", "ME", "SASIA", "AFR", "UKR"}:
        out["taiwan_strait"] = CHN_TS_FRACTION if "CHN" in (i, j) else 1.0
    # Baltic exit
    if (i in BALTIC_RIM or j in BALTIC_RIM) and not pair <= {"EUR", "RUS"}:
        out["danish_straits"] = 1.0
    # Black Sea exit
    if "UKR" in pair and not pair & {"EUR", "RUS"}:
        out["bosphorus"] = 1.0
    return out


def weight_year_for(month: pd.Timestamp, years: list[int]) -> int:
    """Latest benchmark year strictly before the month's year; if none exists
    the earliest benchmark, which then POSTDATES the month (see module doc)."""
    prior = [y for y in years if y < month.year]
    return max(prior) if prior else min(years)


def carry_forward(w: pd.DataFrame, years: list[int]) -> tuple[pd.DataFrame, dict]:
    """Map each benchmark year to each economy's last reported vintage."""
    avail = w.groupby("exposed_iso3")["year"].unique().to_dict()
    blocks = []
    for target in years:
        for exp, ys in avail.items():
            prior = [y for y in ys if y <= target]
            use = max(prior) if prior else min(ys)
            blk = w[(w["exposed_iso3"] == exp) & (w["year"] == use)].copy()
            blk["wyear"] = target
            blocks.append(blk)
    stale = {e: int(max(ys)) for e, ys in avail.items() if max(ys) < max(years)}
    return pd.concat(blocks, ignore_index=True), stale


def load_gpr() -> tuple[pd.DataFrame, str]:
    """Load the monthly country GPR panel from the freshest pinned source.

    data/raw and data/processed are both gitignored and the refresh runs in CI,
    so a clone has neither the workbook nor the processed CSV. web/data/gpr.json
    is tracked, carries the same `recent` variant this script consumes, and is
    versioned alongside the payload it produced - so it pins the GPR vintage that
    built any given commit. Reading it makes

        git checkout <sha> && python3 pipeline/03_build_intensity.py

    reproduce that commit's payload from a clean clone, with nothing extra
    committed. It also sidesteps upstream revision: the workbook is republished
    in place each month with recent months revised, so re-downloading reproduces
    today's numbers, not a past commit's.

    The processed CSV wins when it is at least as current; otherwise gpr.json
    does, and says so. gpr.json is rounded at write time, though, so the fallback
    reproduces a commit's payload only to the published precision; the second
    return value names the source so guard_no_regression can refuse to publish a
    rounded rebuild over a full-precision one.
    """
    csv_path, json_path = PROC / "gpr_country_monthly.csv", WEB / "gpr.json"

    csv_df = None
    if csv_path.exists():
        df = pd.read_csv(csv_path, parse_dates=["month"])
        csv_df = df[(df["variant"] == "recent") & (df["month"].dt.year >= START_YEAR)]

    json_df = None
    if json_path.exists():
        d = json.loads(json_path.read_text())
        months = pd.to_datetime(d.get("months") or [])
        rows = []
        for iso, rec in (d.get("countries") or {}).items():
            lvl, reb = rec.get("level") or [], rec.get("rebased") or []
            for i, m in enumerate(months):
                a = lvl[i] if i < len(lvl) else None
                b = reb[i] if i < len(reb) else None
                if a is None and b is None:
                    continue
                rows.append((m, a, iso, "recent", b))
        if rows:
            json_df = pd.DataFrame(
                rows, columns=["month", "gpr", "iso3", "variant", "gpr_rebased"])
            json_df = json_df[json_df["month"].dt.year >= START_YEAR]

    def last(df):
        return None if df is None or df.empty else df["month"].max()

    lc, lj = last(csv_df), last(json_df)
    if csv_df is not None and (lj is None or lc >= lj):
        print(f"GPR source: {csv_path.name} (through {str(lc)[:7]})")
        return csv_df, "processed_csv"
    if json_df is not None:
        why = "no processed CSV" if csv_df is None else f"CSV only reaches {str(lc)[:7]}"
        print(f"GPR source: web/data/gpr.json (through {str(lj)[:7]}) — {why}")
        return json_df, "tracked_gpr_json"
    raise SystemExit(
        "No GPR panel found. Expected data/processed/gpr_country_monthly.csv "
        "(run 01_load_gpr.py against the workbook) or the tracked web/data/gpr.json."
    )


def guard_no_regression(payload: dict, out: Path) -> list[str]:
    """Report ways `payload` is poorer than the payload already at `out`.

    data/processed/ is gitignored and the monthly refresh runs in CI, so a
    working tree can easily hold GPR inputs older than the committed payload.
    Rebuilding from those inputs silently drops months: the run looks clean, the
    file shrinks, and nothing says so. This makes that loud.

    Pass --allow-regression when a shorter grid is the intended result, e.g. an
    upstream revision genuinely withdrew months.
    """
    if not out.exists():
        return []
    try:
        old = json.loads(out.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    bad = []
    om, nm = old.get("months") or [], payload.get("months") or []
    if om and nm:
        if nm[-1] < om[-1]:
            bad.append(f"last month goes backwards: {om[-1]} -> {nm[-1]}")
        if len(nm) < len(om):
            bad.append(f"month count shrinks: {len(om)} -> {len(nm)}")
    oc, nc = len(old.get("countries") or {}), len(payload.get("countries") or {})
    if nc < oc:
        bad.append(f"exposed economies shrink: {oc} -> {nc}")
    ochs, nchs = set(old.get("channels") or []), set(payload.get("channels") or [])
    missing = ochs - nchs
    if missing:
        bad.append("channels disappear: " + ", ".join(sorted(missing)))
    # Precision regression. web/data/gpr.json is rounded when written (4dp on
    # level, 2dp on rebased), so rebuilding the payload from it rather than from
    # the full-precision CSV moves every value by up to one unit in the last
    # published place. Nothing else catches this: the refresh job's change
    # detector hashes gpr.json, which is identical either way.
    osrc, nsrc = old.get("gpr_source"), payload.get("gpr_source")
    if osrc == "processed_csv" and nsrc == "tracked_gpr_json":
        bad.append("GPR precision degrades: rebuilt from the rounded "
                   "web/data/gpr.json rather than data/processed/"
                   "gpr_country_monthly.csv (run 01_load_gpr.py first)")
    return bad


def main() -> None:
    gpr, gpr_source = load_gpr()
    months = sorted(gpr["month"].unique())

    # ---- assemble long weight table: one row per (i, j, year, channel) -----
    trade = pd.read_csv(PROC / "trade_weights.csv").assign(channel="trade")
    trade = trade.rename(columns={"w_trade": "w"})
    frames = [trade]
    ch_path = PROC / "channel_weights.csv"
    if ch_path.exists():
        frames.append(pd.read_csv(ch_path))
    else:
        print("NOTE channel_weights.csv missing — energy/crm channels skipped")
    # Phase 3: value-added weights (OECD TiVA FDVA). Not a separate exposure
    # channel — an alternative measurement basis for the trade channel; the
    # interface offers it as a gross/value-added toggle. TiVA benchmark years
    # (2019, 2021, 2022) differ from Comtrade's; carry_forward handles the
    # mapping (2022 serves the 2023 target vintage).
    va_path = PROC / "va_weights.csv"
    if va_path.exists():
        frames.append(pd.read_csv(va_path))
    else:
        print("NOTE va_weights.csv missing — value-added basis skipped")
    w_all = pd.concat(frames, ignore_index=True)
    years = sorted(int(y) for y in trade["year"].unique())

    vintage = {m: weight_year_for(pd.Timestamp(m), years) for m in months}
    gpr = gpr.assign(wyear=gpr["month"].map(vintage))

    # Months whose vintage does not precede them. weight_year_for returns a year
    # >= the month's own year only when it fell back to the earliest benchmark,
    # so this is read off the vintage map rather than typed in; the payload
    # field and every warning downstream derive from it.
    anachronistic = [m for m in months if vintage[m] >= pd.Timestamp(m).year]
    weights_anachronistic_through = (
        pd.Timestamp(max(anachronistic)).strftime("%Y-%m") if anachronistic else None)
    print(f"weights anachronistic or contemporaneous through "
          f"{weights_anachronistic_through}: {len(anachronistic)} of {len(months)} months "
          f"({len(anachronistic) / len(months):.1%}) use the {min(years)} benchmark")

    stale_all: dict[str, int] = {}
    parts = []
    for ch, grp in w_all.groupby("channel"):
        cf, stale = carry_forward(grp, years)
        parts.append(cf)
        if ch == "trade":
            stale_all = stale
    w_all = pd.concat(parts, ignore_index=True)

    merged = gpr.merge(
        w_all.rename(columns={"source_iso3": "iso3"}),
        on=["iso3", "wyear"], how="inner",
    )
    merged["c_level"] = merged["w"] * merged["gpr"]
    merged["c_rebased"] = merged["w"] * merged["gpr_rebased"]

    intens = (
        merged.groupby(["exposed_iso3", "month", "channel"])
        .agg(level=("c_level", "sum"), rebased=("c_rebased", "sum"),
             covered=("covered_share", "first"))
        .reset_index()
    )

    # ---- chokepoint channel ------------------------------------------------
    ck = pd.read_csv(REF / "chokepoints.csv")
    present = set(gpr["iso3"].unique())
    # Only littorals with a GPR series in this panel are "covered"; the csv
    # already lists only those, the filter guards against a shorter panel.
    littoral: dict[str, list[str]] = {
        r.chokepoint: [s for s in str(r.gpr_littoral_states).split(";") if s in present]
        for r in ck.itertuples()
    }

    # G_p,t^(-i): mean littoral GPR excluding the exposed economy. The exclusion
    # set depends on (p, i) and not on the month, so it is built once per pair
    # and cached; recomputing it inside the month loop would be wasted work.
    # None means nothing remains once i is removed — i is p's only covered
    # littoral — and p must contribute nothing to i.
    gp_cache: dict[tuple[str, str | None], pd.DataFrame | None] = {}

    def littoral_gpr(p: str, exposed: str) -> pd.DataFrame | None:
        excl = exposed if exposed in littoral[p] else None
        key = (p, excl)
        if key not in gp_cache:
            states = [s for s in littoral[p] if s != excl]
            if not states:
                gp_cache[key] = None
            else:
                sub = gpr[gpr["iso3"].isin(states)]
                gp_cache[key] = sub.groupby("month")[["gpr", "gpr_rebased"]].mean()
        return gp_cache[key]

    tr = w_all[w_all["channel"] == "trade"]
    choke_self_excluded: dict[str, list[str]] = {}
    ck_rows = []
    for (exp, wyear), grp in tr.groupby(["exposed_iso3", "wyear"]):
        share = {p: 0.0 for p in littoral}
        for r in grp.itertuples():
            for p, frac in transit(exp, r.source_iso3).items():
                share[p] += r.w * frac
        m_in = pd.DatetimeIndex([m for m in months if vintage[m] == wyear])
        if m_in.empty:
            continue
        lvl = pd.Series(0.0, index=m_in)
        reb = pd.Series(0.0, index=m_in)
        for p in littoral:
            g = littoral_gpr(p, exp)
            if g is None:
                # exp is p's only covered littoral: recorded whether or not the
                # routing table sends exp's trade through p, because the rule
                # is structural and the interface explains it as such.
                lst = choke_self_excluded.setdefault(exp, [])
                if p not in lst:
                    lst.append(p)
                continue
            if share[p] == 0.0:
                continue
            # Months without a littoral mean contribute nothing for p, as before.
            g = g.reindex(m_in).fillna(0.0)
            lvl += share[p] * g["gpr"]
            reb += share[p] * g["gpr_rebased"]
        for m in m_in:
            ck_rows.append({"exposed_iso3": exp, "month": m, "channel": "choke",
                            "level": float(lvl[m]), "rebased": float(reb[m]),
                            "covered": None})
    choke_self_excluded = {k: sorted(v) for k, v in sorted(choke_self_excluded.items())}
    print("choke_self_excluded (sole covered littoral, strait dropped from own channel): "
          + json.dumps(choke_self_excluded))
    # covered is None on every chokepoint row (no coverage measure exists for a
    # strait); cast it so concat does not have to infer a dtype from all-NA.
    ck_df = pd.DataFrame(ck_rows).astype({"covered": "float64"})
    intens = pd.concat([intens, ck_df], ignore_index=True)

    intens.to_csv(PROC / "intensity_monthly.csv", index=False)
    print(f"wrote {PROC / 'intensity_monthly.csv'}  ({len(intens):,} rows)")

    # ---- web payload -------------------------------------------------------
    month_labels = [pd.Timestamp(m).strftime("%Y-%m") for m in months]
    idx = {pd.Timestamp(m): i for i, m in enumerate(months)}
    channels = sorted(intens["channel"].unique())

    countries: dict[str, dict] = {}
    for (iso), grp in intens.groupby("exposed_iso3"):
        rec = {"level": {}, "rebased": {}, "covered": {}}
        for ch, g in grp.groupby("channel"):
            lvl = [None] * len(months)
            reb = [None] * len(months)
            for m, l, r in zip(g["month"], g["level"], g["rebased"]):
                lvl[idx[m]] = round(float(l), 4)
                reb[idx[m]] = round(float(r), 2)
            rec["level"][ch] = lvl
            rec["rebased"][ch] = reb
            cov = g["covered"].iloc[-1]
            if pd.notna(cov):
                rec["covered"][ch] = round(float(cov), 3)
        countries[iso] = rec

    last = max(months)

    # top_sources (trade-only, last-month-only top-5 partners) was removed in the
    # methods review: it duplicated what the reverse map derives from
    # weights.json for any month, channel and mix.
    payload = {
        "kind": "intensity_multi",
        "channels": channels,
        "months": month_labels,
        "countries": countries,
        "weight_years": years,
        "stale_weights": stale_all,
        # Last month whose weights are the earliest benchmark applied to a month
        # it does not precede; every month <= this is anachronistic (or, in the
        # benchmark year itself, contemporaneous). METHODOLOGY.md section 5.7.
        "weights_anachronistic_through": weights_anachronistic_through,
        # GPR-covered littoral table behind the chokepoint channel, and the
        # (economy, strait) pairs dropped because the economy was the strait's
        # only covered littoral (its own GPR would otherwise feed back).
        "choke_littorals": littoral,
        "choke_self_excluded": choke_self_excluded,
        "source": "Intensity = channel-weighted Caldara & Iacoviello country GPR. "
                  "Weights: WITS/UN Comtrade benchmark years (value-added basis: "
                  "OECD TiVA); chokepoint routing table in data/reference/. The "
                  "chokepoint term uses the mean GPR of each strait's GPR-covered "
                  "littoral states excluding the exposed economy's own GPR; where "
                  "none remains the strait is dropped (choke_self_excluded).",
        "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
        # Which GPR panel built this payload; guard_no_regression uses it to
        # refuse a rounded rebuild over a full-precision one.
        "gpr_source": gpr_source,
    }
    WEB.mkdir(parents=True, exist_ok=True)
    out = WEB / "intensity.json"
    regressions = guard_no_regression(payload, out)
    if regressions and "--allow-regression" not in sys.argv:
        print("\nREFUSING TO WRITE — the rebuild is poorer than the payload on disk:")
        for r in regressions:
            print(f"  - {r}")
        print("\nThe usual cause is stale inputs: data/processed/ is gitignored and the\n"
              "monthly refresh runs in CI, so this tree may hold an older GPR download\n"
              "than the committed payload. Re-run 01_load_gpr.py against a current\n"
              "workbook, or pass --allow-regression if the shorter grid is intended.")
        sys.exit(1)
    if regressions:
        print("WARNING overriding regression checks: " + "; ".join(regressions))
    out.write_text(json.dumps(payload, separators=(",", ":")))
    kb = out.stat().st_size // 1024
    print(f"wrote {out}  ({len(countries)} economies x {len(months)} months x "
          f"{len(channels)} channels, {kb} KB)")

    # ---- bilateral weight payload (reverse map) ----------------------------
    # To attribute a country's Intensity back to the sources producing it, the
    # interface needs w^c_ij itself. Shipping weights rather than precomputed
    # contributions keeps the channel mix client-side, exactly as the main
    # payload does:
    #     contribution of j to i at t = sum_c theta_c w^c_ij G_j,t / sum_c theta_c
    # Summing over j recovers the ATTRIBUTABLE part of Intensity_i,t, not all of
    # it: chokepoint carries no bilateral source, so the attribution falls short
    # by theta_choke * c_choke_i,t / sum_c theta_c whenever that slider is above
    # zero. The interface must show that residual. Loaded lazily, so the initial
    # page weight is unchanged.
    #
    # The chokepoint channel is absent by construction: its weight attaches to a
    # strait, not to a source country, so it cannot be attributed here and the
    # interface must disclose the share it leaves unexplained.
    src_list = sorted(w_all["source_iso3"].unique())
    src_idx = {s: i for i, s in enumerate(src_list)}
    wmap: dict[str, dict] = {}
    blocks = 0
    # Key by wyear, the TARGET vintage, not the raw benchmark year. w_all has
    # been through carry_forward by this point, so wyear is the year a consumer
    # actually resolves via weight_year_for. The two coincide for trade, energy
    # and crm and diverge exactly where it matters: TiVA publishes 2022, which
    # serves the 2023 vintage, and an economy that stopped reporting has its
    # last year carried forward. Keying by "year" shipped 2022 for va and no
    # 2023 at all, so a client following weight_year_for found nothing for every
    # month from 2024 on, and nothing for a stale economy's latest vintage.
    for (exp, ch, yr), grp in w_all.groupby(["exposed_iso3", "channel", "wyear"]):
        pairs = [[src_idx[r.source_iso3], round(float(r.w), 6)]
                 for r in grp.itertuples() if pd.notna(r.w) and r.w > 0]
        if not pairs:
            continue
        wmap.setdefault(exp, {}).setdefault(ch, {})[str(int(yr))] = pairs
        blocks += 1
    wpay = {
        "kind": "bilateral_weights",
        "channels": sorted(w_all["channel"].unique()),
        "years": [int(y) for y in years],
        "sources": src_list,
        "w": wmap,
        "note": "w[exposed][channel][weight_year] = [[source index, weight], ...]; source index refers to the 'sources' array. weight_year is the TARGET vintage a month resolves to - the latest year in 'years' strictly before the month's year, or the earliest for months before all of them - not the benchmark year the underlying source published. Every exposed x channel carries all of 'years'. Contribution of source j to exposed country i at month t = theta_c * w^c_ij * G_j,t summed over the channels present here, divided by the sum of theta over ALL channels including chokepoint. Summing over j therefore recovers only the attributable part of Intensity_i,t: it falls short by theta_choke * c_choke_i,t / sum_c theta_c, because the chokepoint weight attaches to a strait, not to a source country. Any interface using this must disclose that residual rather than presenting the attribution as complete.",
        "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
    }
    wout = WEB / "weights.json"
    wout.write_text(json.dumps(wpay, separators=(",", ":")))
    print(f"wrote {wout}  ({len(wmap)} exposed x {len(src_list)} sources, "
          f"{blocks} vintage blocks, {wout.stat().st_size // 1024} KB)")

    show = intens[(intens["month"] == last)]
    for ch in channels:
        top5 = show[show["channel"] == ch].nlargest(5, "rebased")
        line = ", ".join(f"{r.exposed_iso3} {r.rebased:.0f}" for r in top5.itertuples())
        print(f"top-5 {ch:<7}: {line}")


if __name__ == "__main__":
    main()
