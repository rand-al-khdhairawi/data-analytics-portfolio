"""Full A/B analysis of the Marketing A/B dataset. Usage: python3 run_analysis.py marketing_AB.csv outdir"""
import json, sys
import numpy as np, pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import ab_lib as L

SRC, OUT = sys.argv[1], sys.argv[2]
df = pd.read_csv(SRC).iloc[:, 1:]
df.columns = ["user_id", "group", "converted", "total_ads", "day", "hour"]
df["converted"] = df.converted.astype(int)
df["treat"] = (df.group == "ad").astype(int)
R = {}

# ---- 1. Data quality and assignment checks
R["quality"] = {"rows": len(df), "duplicate_users": int(df.user_id.duplicated().sum()), "missing_values": int(df.isna().sum().sum()),
                "total_ads_min": int(df.total_ads.min()), "hour_range": [int(df.hour.min()), int(df.hour.max())]}
n_ad, n_psa = int((df.treat == 1).sum()), int((df.treat == 0).sum())
R["srm"] = {"ad": n_ad, "psa": n_psa, "share_ad": n_ad / len(df),
            "vs_96_4": L.srm_test([n_ad, n_psa], [0.96, 0.04]), "vs_50_50": L.srm_test([n_ad, n_psa], [0.5, 0.5])}
df["hour_block"] = pd.cut(df.hour, [-1, 5, 11, 17, 23], labels=["00-05", "06-11", "12-17", "18-23"])
bal = {}
for col in ["day", "hour_block"]:
    ct = pd.crosstab(df[col], df.group); c2, p, _, _ = stats.chi2_contingency(ct)
    bal[col] = {"chi2": float(c2), "p": float(p), "cramers_v": float(np.sqrt(c2 / (ct.values.sum() * (min(ct.shape) - 1))))}
mw = stats.mannwhitneyu(df.total_ads[df.treat == 1], df.total_ads[df.treat == 0], alternative="two-sided")
bal["total_ads_mannwhitney"] = {"U": float(mw.statistic), "p": float(mw.pvalue),
                                "median_ad": float(df.total_ads[df.treat == 1].median()), "median_psa": float(df.total_ads[df.treat == 0].median())}
tt = stats.ttest_ind(df.total_ads[df.treat == 1], df.total_ads[df.treat == 0], equal_var=False)
bal["total_ads_welch"] = {"t": float(tt.statistic), "p": float(tt.pvalue), "mean_ad": float(df.total_ads[df.treat == 1].mean()), "mean_psa": float(df.total_ads[df.treat == 0].mean())}
R["balance"] = bal

# outliers / possible bots (extreme impression counts)
q999 = float(df.total_ads.quantile(0.999)); q99 = float(df.total_ads.quantile(0.99))
R["outliers"] = {"p99": q99, "p999": q999, "n_above_p999": int((df.total_ads > q999).sum()),
                 "conv_above_p999": float(df.converted[df.total_ads > q999].mean()), "conv_below": float(df.converted[df.total_ads <= q999].mean()),
                 "max": int(df.total_ads.max())}

# ---- 2. Primary result: conversion
def primary(d):
    x1, n1 = int(d.converted[d.treat == 1].sum()), int((d.treat == 1).sum())
    x2, n2 = int(d.converted[d.treat == 0].sum()), int((d.treat == 0).sum())
    r = L.two_prop(x1, n1, x2, n2); r.update({"x_treat": x1, "n_treat": n1, "x_ctrl": x2, "n_ctrl": n2})
    return r
R["primary"] = primary(df)
p = R["primary"]
R["power"] = {"observed_power": L.power_two_prop(p["p_ctrl"], p["p_treat"], p["n_ctrl"], p["n_treat"]),
              "mde_abs_80": L.mde_two_prop(p["p_ctrl"], p["n_ctrl"], p["n_treat"]),
              "n_per_group_for_observed_effect": L.n_per_group(p["p_ctrl"], p["diff"]),
              "n_per_group_for_10pct_rel_lift": L.n_per_group(p["p_ctrl"], 0.10 * p["p_ctrl"])}
lo, hi = L.wilson(p["x_ctrl"], p["n_ctrl"]); lo2, hi2 = L.wilson(p["x_treat"], p["n_treat"])
R["wilson"] = {"ctrl": (lo, hi), "treat": (lo2, hi2)}
# t-test on the 0/1 outcome (for comparison with the z-test)
t = stats.ttest_ind(df.converted[df.treat == 1], df.converted[df.treat == 0], equal_var=False)
R["welch_on_conversion"] = {"t": float(t.statistic), "p": float(t.pvalue)}

# sensitivity: drop extreme-exposure users
R["sensitivity"] = {}
for name, cut in [("exclude_above_p999", q999), ("exclude_above_p99", q99)]:
    r = primary(df[df.total_ads <= cut]); R["sensitivity"][name] = {k: r[k] for k in ["p_treat", "p_ctrl", "diff", "diff_ci", "rel_lift", "p_z"]}

# ---- 3. Exposure strata: where does the effect come from?
bins = [0, 1, 5, 10, 25, 50, 100, 1e9]; labels = ["1", "2-5", "6-10", "11-25", "26-50", "51-100", "100+"]
df["bucket"] = pd.cut(df.total_ads, bins, labels=labels)
strata, rows = [], []
for b, g in df.groupby("bucket", observed=True):
    a = g[g.treat == 1]; c = g[g.treat == 0]
    r = L.two_prop(int(a.converted.sum()), len(a), int(c.converted.sum()), len(c))
    rows.append({"bucket": str(b), "n_ad": len(a), "n_psa": len(c), "conv_ad": r["p_treat"], "conv_psa": r["p_ctrl"], "diff": r["diff"],
                 "diff_ci": r["diff_ci"], "p": r["p_z"]})
    strata.append((int(a.converted.sum()), len(a) - int(a.converted.sum()), int(c.converted.sum()), len(c) - int(c.converted.sum())))
adj = L.holm([r["p"] for r in rows])
for r, a in zip(rows, adj): r["p_holm"] = float(a)
R["by_exposure"] = rows
R["cmh"] = L.cmh(strata)

# logistic models: main effect + exposure, then interaction (LR test for heterogeneity)
df["log_ads"] = np.log1p(df.total_ads)
X0 = np.column_stack([np.ones(len(df)), df.treat, df.log_ads])
X1 = np.column_stack([X0, df.treat * df.log_ads])
m0 = L.logit_fit(X0, df.converted, ["intercept", "ad", "log1p(total_ads)"])
m1 = L.logit_fit(X1, df.converted, ["intercept", "ad", "log1p(total_ads)", "ad x log1p(total_ads)"])
m_naive = L.logit_fit(np.column_stack([np.ones(len(df)), df.treat]), df.converted, ["intercept", "ad"])
pack = lambda m: [{"term": n, "coef": float(c), "se": float(s), "odds_ratio": float(o), "or_ci": [float(a), float(b)], "p": float(pp)}
                  for n, c, s, o, a, b, pp in zip(m["names"], m["coef"], m["se"], m["or"], m["or_ci"][0], m["or_ci"][1], m["p"])]
R["logit_naive"] = pack(m_naive); R["logit_adjusted"] = pack(m0); R["logit_interaction"] = pack(m1)
R["interaction_lr"] = L.lr_test(m1["ll"], m0["ll"], 1)

# ---- 4. Day and hour-of-day segments (Holm-corrected)
seg_rows = []
for col in ["day", "hour_block"]:
    for v, g in df.groupby(col, observed=True):
        a = g[g.treat == 1]; c = g[g.treat == 0]
        r = L.two_prop(int(a.converted.sum()), len(a), int(c.converted.sum()), len(c))
        seg_rows.append({"dimension": col, "value": str(v), "conv_ad": r["p_treat"], "conv_psa": r["p_ctrl"], "diff": r["diff"],
                         "diff_ci": r["diff_ci"], "p": r["p_z"], "n_psa": len(c)})
adj = L.holm([r["p"] for r in seg_rows])
for r, a in zip(seg_rows, adj): r["p_holm"] = float(a)
R["segments"] = seg_rows

json.dump(R, open(f"{OUT}/results.json", "w"), indent=1, default=float)

# ---- charts
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
ax[0].bar(["PSA (control)", "Ad (treatment)"], [p["p_ctrl"] * 100, p["p_treat"] * 100], color=["#8a96a3", "#0f6b7a"],
          yerr=[[(p["p_ctrl"] - lo) * 100, (p["p_treat"] - lo2) * 100], [(hi - p["p_ctrl"]) * 100, (hi2 - p["p_treat"]) * 100]], capsize=6)
ax[0].set_ylabel("Conversion rate (%)"); ax[0].set_title("Overall conversion with 95% Wilson CI")
x = np.arange(len(rows)); w = 0.38
ax[1].bar(x - w / 2, [r["conv_psa"] * 100 for r in rows], w, label="PSA", color="#8a96a3")
ax[1].bar(x + w / 2, [r["conv_ad"] * 100 for r in rows], w, label="Ad", color="#0f6b7a")
ax[1].set_xticks(x); ax[1].set_xticklabels([r["bucket"] for r in rows]); ax[1].set_xlabel("Ads seen by user"); ax[1].set_ylabel("Conversion rate (%)")
ax[1].set_title("Conversion by ad exposure"); ax[1].legend()
plt.tight_layout(); plt.savefig(f"{OUT}/ab_overview.png", dpi=150); plt.close()

print(json.dumps({k: R[k] for k in ["quality", "srm", "balance", "outliers", "primary", "power", "wilson", "welch_on_conversion", "sensitivity", "cmh", "interaction_lr"]}, indent=1, default=float))
for r in rows: print(r)
for k in ["logit_naive", "logit_adjusted", "logit_interaction"]: print(k, [(t["term"], round(t["coef"], 3), round(t["odds_ratio"], 2), t["p"]) for t in R[k]])
for r in seg_rows: print(r["dimension"], r["value"], round(r["conv_ad"]*100,2), round(r["conv_psa"]*100,2), round(r["diff"]*100,2), round(r["p_holm"],4))
