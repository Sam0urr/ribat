"""
03_build_intensity.py — join country GPR with channel weights into Intensity.

INT_i,t = sum_c theta_c * sum_j w^c_ij * G_j,t        (METHODOLOGY.md section 2)

Channels shipped:
  trade   02_build_weights.py        (M+X)/(M+X total), GPR-44 partners
  energy  02b (WITS product Fuels)   import shares
  crm     02b (WITS product OresMtls) import shares — CRM *proxy*
  choke   derived: trade weights x hand-coded route transit x littoral GPR

The channel mix theta is NOT applied here: the web payload carries each
channel's contribution separately and the interface mixes them client-side,
so the sliders are a real sensitivity analysis rather than a re-run.

Chokepoint channel construction:
  transit(i,j) = set of chokepoints on the dominant sea route between i and j,
                 from a coarse region-level routing table (below). Intra-region
                 pairs get none (largely overland/short-sea).
  c_choke_i,t  = sum_p [ sum_j w_trade_ij * 1{p in transit(i,j)} ] * G_p,t
  G_p,t        = mean GPR of the chokepoint's GPR-covered littoral states
                 (data/reference/chokepoints.csv; several true littorals lack
                 GPR series, so the channel UNDERSTATES — see the csv notes).

Weight vintage: each month t uses the latest benchmark year strictly before t;
non-reporters carry forward their last benchmark (flagged in stale_weights).

Input:  data/processed/gpr_country_monthly.csv     (01)
        data/processed/trade_weights.csv           (02)
        data/processed/channel_weights.csv         (02b, optional)
        data/reference/chokepoints.csv
Output: data/processed/intensity_monthly.csv
        web/data/intensity.json
"""

from __future__ import annotations

import json
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
TS_NORTH = {"CHN", "KOR", "JPN"}  # routes to these transit the Taiwan Strait
ASIA = {"EASIA", "SEASIA", "SASIA"}


def transit(i: str, j: str) -> set[str]:
    a, b = REGION[i], REGION[j]
    if a == b:
        return set()
    pair, out = {a, b}, set()
    east = {i, j} & (TS_NORTH if True else set())

    # Europe/Med <-> Asia/Oceania: Suez corridor
    if pair & {"EUR", "UKR", "RUS"} and pair & (ASIA | {"OCE"}):
        out.add("red_sea")
        if pair & {"EASIA", "SEASIA"}:
            out.add("malacca")
    # Gulf (SAU) shipping: Hormuz; westbound also Red Sea
    if "SAU" in (i, j):
        out.add("hormuz")
        if pair & {"EUR", "AMER", "UKR", "RUS"}:
            out.add("red_sea")
        if pair & {"EASIA", "SEASIA"}:
            out.add("malacca")
    # East Asia <-> South Asia / Middle East / Africa: Malacca
    if "EASIA" in pair and pair & {"SASIA", "ME", "AFR"}:
        out.add("malacca")
    # Taiwan Strait: partner north of it, counterpart approaching from S/W
    if east and pair & {"EUR", "ME", "SASIA", "SEASIA", "AFR", "UKR"}:
        out.add("taiwan_strait")
    # Baltic exit
    if (i in BALTIC_RIM or j in BALTIC_RIM) and not pair <= {"EUR", "RUS"}:
        out.add("danish_straits")
    # Black Sea exit
    if "UKR" in pair and not pair & {"EUR", "RUS"}:
        out.add("bosphorus")
    return out


def weight_year_for(month: pd.Timestamp, years: list[int]) -> int:
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


def main() -> None:
    gpr = pd.read_csv(PROC / "gpr_country_monthly.csv", parse_dates=["month"])
    gpr = gpr[(gpr["variant"] == "recent") & (gpr["month"].dt.year >= START_YEAR)]
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
    years = sorted(trade["year"].unique())

    vintage = {m: weight_year_for(pd.Timestamp(m), years) for m in months}
    gpr = gpr.assign(wyear=gpr["month"].map(vintage))

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
    littoral = {r.chokepoint: r.gpr_littoral_states.split(";") for r in ck.itertuples()}

    # G_p,t: mean GPR over the chokepoint's covered littoral states
    gp = {}
    for p, states in littoral.items():
        sub = gpr[gpr["iso3"].isin(states)]
        g = sub.groupby("month")[["gpr", "gpr_rebased"]].mean()
        gp[p] = g

    tr = w_all[w_all["channel"] == "trade"]
    ck_rows = []
    for (exp, wyear), grp in tr.groupby(["exposed_iso3", "wyear"]):
        share = {p: 0.0 for p in littoral}
        for r in grp.itertuples():
            for p in transit(exp, r.source_iso3):
                share[p] += r.w
        for m in months:
            if vintage[m] != wyear:
                continue
            lvl = sum(share[p] * gp[p].loc[m, "gpr"] for p in littoral if m in gp[p].index)
            reb = sum(share[p] * gp[p].loc[m, "gpr_rebased"] for p in littoral if m in gp[p].index)
            ck_rows.append({"exposed_iso3": exp, "month": m, "channel": "choke",
                            "level": lvl, "rebased": reb, "covered": None})
    intens = pd.concat([intens, pd.DataFrame(ck_rows)], ignore_index=True)

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
    top_sources: dict[str, list] = {}
    lm = merged[(merged["month"] == last) & (merged["channel"] == "trade")]
    for iso, grp in lm.groupby("exposed_iso3"):
        top = grp.nlargest(5, "c_rebased")
        top_sources[iso] = [
            [r["iso3"], round(r["w"], 4), round(r["c_rebased"], 1)]
            for _, r in top.iterrows()
        ]

    payload = {
        "kind": "intensity_multi",
        "channels": channels,
        "months": month_labels,
        "countries": countries,
        "top_sources": top_sources,
        "weight_years": [int(y) for y in years],
        "stale_weights": stale_all,
        "source": "Intensity = channel-weighted Caldara & Iacoviello country GPR. "
                  "Weights: WITS/UN Comtrade benchmark years; chokepoint routing "
                  "table in data/reference/.",
        "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
    }
    WEB.mkdir(parents=True, exist_ok=True)
    out = WEB / "intensity.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    kb = out.stat().st_size // 1024
    print(f"wrote {out}  ({len(countries)} economies x {len(months)} months x "
          f"{len(channels)} channels, {kb} KB)")

    show = intens[(intens["month"] == last)]
    for ch in channels:
        top5 = show[show["channel"] == ch].nlargest(5, "rebased")
        line = ", ".join(f"{r.exposed_iso3} {r.rebased:.0f}" for r in top5.itertuples())
        print(f"top-5 {ch:<7}: {line}")


if __name__ == "__main__":
    main()
