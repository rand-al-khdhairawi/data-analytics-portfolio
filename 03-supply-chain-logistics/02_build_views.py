"""Create the KPI views in data/supply.db from 02_kpis.sql. Run from this folder: python 02_build_views.py"""
import sqlite3
con = sqlite3.connect("data/supply.db")
con.executescript(open("02_kpis.sql", encoding="utf-8").read())
for v in ["v_orders", "v_kpi_mode", "v_kpi_region", "v_kpi_month", "v_pareto_country"]:
    print(v, con.execute(f"select count(*) from {v}").fetchone()[0], "rows")
