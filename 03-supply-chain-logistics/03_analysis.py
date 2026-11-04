"""Pareto, lead-time variance and mode-adjusted lateness; exports aggregates for the dashboard."""
import json, sqlite3, sys
import numpy as np, pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB, OUT = sys.argv[1], sys.argv[2]
con = sqlite3.connect(DB)
o = pd.read_sql("""select o.order_id, o.is_late, o.actual_days, o.scheduled_days, o.delay_days, o.order_value, m.shipping_mode,
                   r.region, r.country, r.city, t.year_month
                   from v_delivered o join Dim_Route r using(route_key) join Dim_ShippingMode m using(mode_key)
                   join Dim_Date t on t.date_key = o.order_date_key""", con)
R = {"orders": len(o), "otd_pct": 100 * (1 - o.is_late.mean()), "avg_lead_time": o.actual_days.mean(),
     "delayed_value": float(o.loc[o.is_late == 1, "order_value"].sum()), "total_value": float(o.order_value.sum())}

# ---- lead time variance by mode
v = o.groupby("shipping_mode").agg(orders=("is_late", "size"), sched=("scheduled_days", "first"), mean_actual=("actual_days", "mean"),
                                   sd_actual=("actual_days", "std"), mean_delay=("delay_days", "mean"), sd_delay=("delay_days", "std"),
                                   otd=("is_late", lambda s: 1 - s.mean())).round(3)
R["mode"] = v.reset_index().to_dict("records")
print(v)

# ---- Pareto on country and city
def pareto(level):
    g = o.groupby(level).agg(orders=("is_late", "size"), late=("is_late", "sum")).sort_values("late", ascending=False)
    g["cum_late"] = g.late.cumsum() / g.late.sum(); g["cum_orders"] = g.orders.cumsum() / g.orders.sum()
    n80 = int((g.cum_late < 0.8).sum() + 1); share_units = n80 / len(g)
    vol_share = g.orders.iloc[:n80].sum() / g.orders.sum()
    return g, {"units": len(g), "units_for_80pct_late": n80, "share_of_units": share_units, "their_share_of_all_orders": float(vol_share)}
gc, R["pareto_country"] = pareto("country"); gci, R["pareto_city"] = pareto("city")
print(R["pareto_country"], R["pareto_city"])
fig, ax = plt.subplots(figsize=(10, 4.2)); top = gc.head(30)
ax.bar(range(len(top)), top.late, color="#0f6b7a"); ax.set_ylabel("Late orders")
ax.set_xticks(range(len(top))); ax.set_xticklabels(top.index, rotation=70, ha="right", fontsize=8)
ax2 = ax.twinx(); ax2.plot(range(len(top)), top.cum_late * 100, color="#c2571a", marker="o", ms=3); ax2.set_ylabel("Cumulative % of late orders"); ax2.axhline(80, ls="--", color="grey", lw=1)
ax.set_title("Pareto of late orders by destination country (top 30)"); plt.tight_layout(); plt.savefig(f"{OUT}/pareto_country.png", dpi=150); plt.close()

# ---- is lateness geographic? expected late count from shipping-mode mix alone
mode_rate = o.groupby("shipping_mode").is_late.mean()
o["exp"] = o.shipping_mode.map(mode_rate)
def excess(level, min_orders):
    g = o.groupby(level).agg(orders=("is_late", "size"), late=("is_late", "sum"), exp=("exp", "sum"), var=("exp", lambda s: (s * (1 - s)).sum()))
    g = g[g.orders >= min_orders].copy()
    g["z"] = (g.late - g.exp) / np.sqrt(g["var"]); g["p"] = 2 * stats.norm.sf(g.z.abs())
    g["p_bonf"] = (g.p * len(g)).clip(upper=1)
    return g
ec = excess("country", 300)
R["excess_country"] = {"countries_tested": len(ec), "significant_bonferroni_05": int((ec.p_bonf < 0.05).sum()),
                       "max_abs_excess_rate_pp": float(((ec.late - ec.exp) / ec.orders).abs().max() * 100),
                       "late_rate_min_pct": float(100 * (ec.late / ec.orders).min()), "late_rate_max_pct": float(100 * (ec.late / ec.orders).max())}
er = excess("region", 100)
R["excess_region"] = {"regions_tested": len(er), "significant_bonferroni_05": int((er.p_bonf < 0.05).sum())}
print(R["excess_country"], R["excess_region"])
print(er.assign(excess_pp=(er.late - er.exp) / er.orders * 100)[["orders", "excess_pp", "p_bonf"]].round(3).sort_values("p_bonf").head(5))
# share of variation in lateness explained by mode vs region (simple eta-squared style via R^2 of group means)
def r2(col):
    gm = o.groupby(col).is_late.transform("mean"); return float(1 - ((o.is_late - gm) ** 2).sum() / ((o.is_late - o.is_late.mean()) ** 2).sum())
R["r2"] = {"mode": r2("shipping_mode"), "region": r2("region"), "country": r2("country")}
print(R["r2"])

# ---- what if the promised days matched typical performance? (First Class 1->2 days, Second Class 2->4 days)
new_sched = o.shipping_mode.map({"First Class": 2, "Second Class": 4}).fillna(o.scheduled_days)
new_late = (o.actual_days > new_sched).astype(int)
R["rebaseline"] = {"otd_before_pct": float(100 * (1 - o.is_late.mean())), "otd_after_pct": float(100 * (1 - new_late.mean())),
                   "first_class_otd_after_pct": float(100 * (1 - new_late[o.shipping_mode == "First Class"].mean())),
                   "second_class_otd_after_pct": float(100 * (1 - new_late[o.shipping_mode == "Second Class"].mean())),
                   "late_orders_removed": int(o.is_late.sum() - new_late.sum())}
print(R["rebaseline"])

# ---- aggregates for the dashboard (month x region x country x mode)
o["delayed_value"] = np.where(o.is_late == 1, o.order_value, 0.0)
agg = (o.groupby(["year_month", "region", "country", "shipping_mode"])
        .agg(n=("is_late", "size"), late=("is_late", "sum"), act=("actual_days", "sum"), sch=("scheduled_days", "sum"), dv=("delayed_value", "sum"), val=("order_value", "sum"))
        .reset_index())
agg[["act", "sch", "dv", "val"]] = agg[["act", "sch", "dv", "val"]].round(1)
json.dump({"agg": agg.values.tolist(), "cols": list(agg.columns)}, open(f"{OUT}/dashboard_agg.json", "w"))
json.dump(R, open(f"{OUT}/results.json", "w"), indent=1, default=float)
print(len(agg), "agg rows; summary", {k: R[k] for k in ["orders", "otd_pct", "avg_lead_time", "delayed_value", "total_value"]})
