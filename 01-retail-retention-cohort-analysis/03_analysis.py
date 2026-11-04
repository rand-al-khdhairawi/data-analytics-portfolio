"""RFM segmentation, retention heatmap and region/category analysis. Run from this folder after 02_build_views.py.
Reads data/retail.db, writes charts and CSV/JSON files to outputs/."""
import json
import sqlite3
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import os
OUT = "outputs"
os.makedirs(OUT, exist_ok=True)
con = sqlite3.connect("data/retail.db")
q = lambda s: pd.read_sql(s, con)

# ---------- Retention heatmap ----------
ret = q("select * from v_cohort_retention")
mat = ret.pivot(index="cohort_month", columns="month_n", values="retention")
sizes = ret.groupby("cohort_month").cohort_size.first()
# keep only cells observable (cohort + n within data window)
last_month = pd.Timestamp("2011-11-01")
for cm in mat.index:
    max_n = (last_month.year - pd.Timestamp(cm).year) * 12 + last_month.month - pd.Timestamp(cm).month
    mat.loc[cm, mat.columns > max_n] = np.nan
mat = mat.iloc[:, :13]
mat.index = [c[:7] for c in mat.index]
plt.figure(figsize=(11, 8))
sns.heatmap(mat.drop(columns=[0]), annot=True, fmt=".0%", cmap="Blues", cbar_kws={"label": "Retention"}, annot_kws={"size": 7})
plt.title("Monthly cohort retention (month 1-12 after first order, Jan 2010 onward)")
plt.xlabel("Months since acquisition"); plt.ylabel("Acquisition cohort")
plt.tight_layout(); plt.savefig("images/retention_heatmap.png", dpi=150); plt.close()

# ---------- RFM ----------
rfm = q("select * from v_rfm").set_index("customer_id")
rfm["R"] = pd.qcut(rfm.recency_days.rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
rfm["F"] = pd.cut(rfm.frequency, [0, 1, 2, 3, 4, 1e9], labels=[1, 2, 3, 4, 5]).astype(int)
rfm["M"] = pd.qcut(rfm.monetary.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)

def seg(r):
    if r.R >= 4 and r.F >= 4: return "Champions"
    if r.F >= 3 and r.R >= 3: return "Loyal"
    if r.R >= 4 and r.F == 1: return "New customers"
    if r.R >= 3 and r.F == 2: return "Promising"
    if r.R <= 2 and r.F >= 3: return "At risk"
    if r.R <= 2 and r.F == 2: return "Needs attention"
    return "Hibernating"
rfm["segment"] = rfm.apply(seg, axis=1)

cust = q("select * from customers").set_index("customer_id")
rfm = rfm.join(cust[["channel"]])
# retention proxy: share with 2+ orders
seg_tbl = rfm.groupby("segment").agg(
    customers=("frequency", "size"), avg_orders=("frequency", "mean"),
    avg_ltv=("monetary", "mean"), revenue=("monetary", "sum"), avg_recency=("recency_days", "mean")
).round(2).sort_values("revenue", ascending=False)
seg_tbl["revenue_share"] = (seg_tbl.revenue / seg_tbl.revenue.sum()).round(4)
seg_tbl.to_csv(f"{OUT}/rfm_segments.csv")

plt.figure(figsize=(8, 4.5))
order = seg_tbl.sort_values("avg_ltv").index
sns.barplot(data=rfm.reset_index(), y="segment", x="monetary", order=order, estimator=np.mean, color="#2a6fb0", errorbar=None)
plt.title("Average customer value by RFM segment"); plt.xlabel("Avg revenue per customer"); plt.ylabel("")
plt.tight_layout(); plt.savefig("images/rfm_segments.png", dpi=150); plt.close()

# ---------- Channel & category ----------
ch = rfm.groupby("channel").agg(
    customers=("frequency", "size"), avg_ltv=("monetary", "mean"), avg_orders=("frequency", "mean")).round(4)
# 90-day repeat rate on acquired customers with a full 90-day window
mat90 = q("""select k.customer_id, k.channel,
   (select days_since_prev from v_orders_clean o where o.customer_id=k.customer_id and o.order_seq=2) as d2
   from v_customer_cohort k
   where k.first_order_date <= (select date(max(order_date),'-90 days') from v_orders_clean)""")
mat90["rep90"] = (mat90.d2 <= 90).astype(int)
ch["customers_90d_base"] = mat90.groupby("channel").size()
ch["repeat_rate"] = mat90.groupby("channel").rep90.mean().round(4)
orders = q("select o.*, c.channel from v_orders_clean o join customers c using(customer_id)")
ch["aov"] = orders.groupby("channel").order_total.mean().round(2)
ch.to_csv(f"{OUT}/channel_summary.csv")
cat = q("select * from v_first_order_category_repeat").sort_values("repeat_rate", ascending=False)
cat.to_csv(f"{OUT}/category_repeat.csv", index=False)

# funnel: where customers drop off
orders_per = rfm.frequency
funnel = {f"{k}+ orders": float((orders_per >= k).mean()) for k in [1, 2, 3, 4, 5]}
gap = orders[orders.order_seq == 2].days_since_prev
funnel_gap = {"median_days_to_2nd": float(gap.median()), "p75_days_to_2nd": float(gap.quantile(.75)),
              "share_of_2nd_orders_within_90d": float((gap <= 90).mean())}

# ---------- Export for dashboard ----------
mr = q("select * from v_monthly_revenue order by order_month")
aov = q("select channel, order_month, aov from v_aov_channel order by order_month")
curves = ret[ret.month_n <= 12].copy()
curves["h"] = curves.apply(lambda r: r.month_n <= (2011 - int(r.cohort_month[:4])) * 12 + 11 - int(r.cohort_month[5:7]), axis=1)
curves = curves[curves.h]
# retention curve by channel (weighted)
cc = q("select * from v_customer_cohort")
act = q("""select distinct o.customer_id, o.order_month, k.cohort_month, k.channel from v_orders_clean o
           join v_customer_cohort k using(customer_id)""")
act["n"] = (pd.to_datetime(act.order_month).dt.year - pd.to_datetime(act.cohort_month).dt.year) * 12 + \
           (pd.to_datetime(act.order_month).dt.month - pd.to_datetime(act.cohort_month).dt.month)
cc["max_n"] = (2011 - pd.to_datetime(cc.cohort_month).dt.year) * 12 + 11 - pd.to_datetime(cc.cohort_month).dt.month
chan_curve = {}
for chn, g in cc.groupby("channel"):
    pts = []
    for n in range(1, 13):
        elig = g[g.max_n >= n].customer_id
        a = act[(act.n == n) & act.customer_id.isin(elig)].customer_id.nunique()
        pts.append(round(a / len(elig), 4) if len(elig) else None)
    chan_curve[chn] = pts

payload = {
    "monthly": mr.to_dict("records"),
    "aov": {c: g.set_index("order_month").aov.round(2).to_dict() for c, g in aov.groupby("channel")},
    "channel_summary": ch.reset_index().to_dict("records"),
    "segments": seg_tbl.reset_index().to_dict("records"),
    "category": cat.to_dict("records"),
    "channel_curve": chan_curve,
    "heatmap": {"rows": list(mat.index), "cols": [int(c) for c in mat.columns],
                "vals": [[None if pd.isna(v) else round(float(v), 4) for v in row] for row in mat.values],
                "sizes": [int(sizes[r + "-01"]) for r in mat.index]},
    "funnel": funnel, "funnel_gap": funnel_gap,
    "kpis": {"customers": int(len(rfm)), "orders": int(len(orders)),
             "revenue": float(orders.order_total.sum()), "aov": float(orders.order_total.mean()),
             "repeat_rate": float((rfm.frequency > 1).mean()), "avg_ltv": float(rfm.monetary.mean())},
}
json.dump(payload, open(f"{OUT}/dashboard_data.json", "w"), default=float)

print(seg_tbl.to_string()); print(); print(ch.to_string()); print(); print(cat.to_string(index=False))
print(); print(funnel); print(funnel_gap); print(payload["kpis"])
