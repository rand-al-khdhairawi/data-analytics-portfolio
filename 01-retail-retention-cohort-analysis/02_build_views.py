"""Create the SQL views in data/retail.db from 02_models.sql. Run from this folder: python 02_build_views.py"""
import sqlite3
con = sqlite3.connect("data/retail.db")
con.executescript(open("02_models.sql", encoding="utf-8").read())
for v in ["v_cohort_retention", "v_monthly_revenue", "v_aov_channel", "v_rfm", "v_first_order_category_repeat"]:
    print(v, con.execute(f"select count(*) from {v}").fetchone()[0], "rows")
