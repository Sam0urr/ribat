"""
04_validate.py — empirical validation of the Intensity index.

Three tests, each capable of failing and reported whether or not it flatters
the index:

  T1 DISCRIMINANT VALIDITY. If Intensity_i correlates ~1 with economy i's own
     source-side GPR, the exposure weighting adds nothing and the map is a
     re-plot of Caldara-Iacoviello. Reports pooled and cross-sectional rank
     correlation.

  T2 CHANNEL DISCRIMINATION. If the four channels move together, the sliders
     are decorative. Reports the cross-channel correlation matrix.

  T3 EVENT STUDIES. Pre-registered expectations for known episodes: which
     economies should move, on which channel. Reports the actual top movers
     so the expectation can be scored honestly.

Weight-vintage caveat: months before the first benchmark year (2019) are
computed with 2019 weights. Pre-2019 episodes are therefore ANACHRONISTIC —
they answer "who would have been exposed, given today's structure", not "who
was exposed then". Flagged in the output and in the methods note.

Input:  data/processed/intensity_monthly.csv, gpr_country_monthly.csv
Output: data/processed/validation_report.txt
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = PROC / "validation_report.txt"

FIRST_BENCHMARK = 2019

# Pre-registered expectations. Written from the mechanism, not from the data.
EVENTS = [
    ("2019-09", "Abqaiq strike on Saudi oil processing", "energy",
     "Gulf-dependent oil importers: JPN, KOR, IND, CHN, TWN"),
    ("2022-02", "Russian invasion of Ukraine", "energy",
     "European importers of Russian supply: POL, HUN, DEU, ITA, FIN, TUR"),
    ("2022-08", "Taiwan Strait crisis (Pelosi visit)", "choke",
     "Economies routing through the Taiwan Strait: JPN, KOR, PHL, EU-Asia traders"),
    ("2023-10", "Israel-Gaza war onset", "choke",
     "Red Sea corridor users: EU-Asia traders (DEU, NLD, ITA, POL) via EGY littoral"),
    ("2024-01", "Red Sea shipping attacks", "choke",
     "Same Red Sea corridor, sustained: EU-Asia traders"),
    ("2001-09", "9/11 [ANACHRONISTIC WEIGHTS]", "trade",
     "US-dependent economies: CAN, MEX"),
    ("1990-08", "Iraq invades Kuwait [ANACHRONISTIC WEIGHTS]", "energy",
     "Oil importers exposed to Saudi GPR"),
]

BASELINE_MONTHS = 12
TOP_N = 6


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    it = pd.read_csv(PROC / "intensity_monthly.csv", parse_dates=["month"])
    gpr = pd.read_csv(PROC / "gpr_country_monthly.csv", parse_dates=["month"])
    gpr = gpr[gpr["variant"] == "recent"]
    return it, gpr


def t1_discriminant(it: pd.DataFrame, gpr: pd.DataFrame, out: list[str]) -> None:
    out += ["", "=" * 72,
            "T1  DISCRIMINANT VALIDITY - is Intensity just re-plotting GPR?",
            "=" * 72]
    trade = it[it["channel"] == "trade"][["exposed_iso3", "month", "rebased"]]
    m = trade.merge(
        gpr[["iso3", "month", "gpr_rebased"]],
        left_on=["exposed_iso3", "month"], right_on=["iso3", "month"], how="inner",
    )
    m = m[m["month"].dt.year >= FIRST_BENCHMARK]
    if m.empty:
        out.append("  no overlap")
        return
    out += [f"  Pooled Pearson  own-GPR vs Intensity : "
            f"{m['rebased'].corr(m['gpr_rebased']): .3f}",
            f"  Pooled Spearman own-GPR vs Intensity : "
            f"{m['rebased'].corr(m['gpr_rebased'], method='spearman'): .3f}"]

    xs = []
    for _, g in m.groupby("month"):
        if len(g) > 3:
            xs.append(g["rebased"].corr(g["gpr_rebased"], method="spearman"))
    xs = pd.Series(xs).dropna()
    out += [f"  Cross-sectional Spearman, mean       : {xs.mean(): .3f}"
            f"   (min {xs.min(): .2f}, max {xs.max(): .2f}, n={len(xs)} months)",
            "",
            "  Interpretation: values near +1 would mean the exposure weighting is",
            "  redundant. Values near 0 mean Intensity ranks economies differently",
            "  from source-side GPR - i.e. it carries information GPR does not."]


def t2_channels(it: pd.DataFrame, out: list[str]) -> None:
    out += ["", "=" * 72,
            "T2  CHANNEL DISCRIMINATION - are the sliders decorative?",
            "=" * 72]
    w = (
        it[it["month"].dt.year >= FIRST_BENCHMARK]
        .pivot_table(index=["exposed_iso3", "month"], columns="channel", values="rebased")
        .dropna(how="all")
    )
    corr = w.corr(method="spearman").round(3)
    out.append(corr.to_string())
    vals = [corr.iloc[i, j] for i in range(len(corr)) for j in range(len(corr)) if i < j]
    out += ["",
            f"  Mean off-diagonal Spearman: {np.mean(vals): .3f}",
            "  Interpretation: near +1 across the board would mean the channels are",
            "  the same signal and the mix is cosmetic."]


def t3_events(it: pd.DataFrame, out: list[str]) -> None:
    out += ["", "=" * 72,
            "T3  EVENT STUDIES - pre-registered expectations vs actual top movers",
            "=" * 72]
    for month_s, label, channel, expectation in EVENTS:
        t = pd.Timestamp(month_s + "-01")
        sub = it[it["channel"] == channel]
        cur = sub[sub["month"] == t].set_index("exposed_iso3")["rebased"]
        base_win = sub[(sub["month"] < t) &
                       (sub["month"] >= t - pd.DateOffset(months=BASELINE_MONTHS))]
        base = base_win.groupby("exposed_iso3")["rebased"].mean()
        if cur.empty or base.empty:
            out += ["", f"  {month_s}  {label}: no data"]
            continue
        delta = ((cur - base) / base * 100).replace([np.inf, -np.inf], np.nan).dropna()
        delta = delta.sort_values(ascending=False)
        top = ", ".join(f"{i} {v:+.0f}%" for i, v in delta.head(TOP_N).items())
        out += ["",
                f"  {month_s}  {label}   [channel: {channel}]",
                f"    expected : {expectation}",
                f"    observed : {top}",
                f"    median move across economies: {delta.median():+.0f}%"]
        if t.year < FIRST_BENCHMARK:
            out.append("    WARNING pre-2019 - weights are anachronistic (2019 vintage)")


def main() -> None:
    it, gpr = load()
    out = ["Intensity index - validation report",
           f"generated {pd.Timestamp.today():%Y-%m-%d}",
           f"months {it['month'].min():%Y-%m} to {it['month'].max():%Y-%m}, "
           f"{it['exposed_iso3'].nunique()} economies, "
           f"channels: {', '.join(sorted(it['channel'].unique()))}"]
    t1_discriminant(it, gpr, out)
    t2_channels(it, out)
    t3_events(it, out)
    text = "\n".join(out)
    OUT.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
