"""Build a star schema in SQLite from the DataCo supply chain file. PII columns (names, email, password, street, zip) are dropped."""
import sqlite3, sys
import numpy as np, pandas as pd

SRC, DB = sys.argv[1], sys.argv[2]
d = pd.read_csv(SRC, encoding="latin-1")
d.columns = [c.strip() for c in d.columns]
d["order_date"] = pd.to_datetime(d["order date (DateOrders)"], format="%m/%d/%Y %H:%M")
d["ship_date"] = pd.to_datetime(d["shipping date (DateOrders)"], format="%m/%d/%Y %H:%M")

# order-level attributes must be constant within an order, otherwise order-level KPIs would be ambiguous
for c in ["Days for shipping (real)", "Days for shipment (scheduled)", "Shipping Mode", "Order City", "Delivery Status", "order_date"]:
    assert d.groupby("Order Id")[c].nunique().max() == 1, c

def dkey(s): return s.dt.strftime("%Y%m%d").astype(int)
dates = pd.date_range("2015-01-01", "2018-03-31")
dim_date = pd.DataFrame({"date_key": dates.strftime("%Y%m%d").astype(int), "date": dates.strftime("%Y-%m-%d"), "year": dates.year,
                         "quarter": dates.quarter, "month": dates.month, "month_name": dates.strftime("%b"),
                         "year_month": dates.strftime("%Y-%m"), "day_of_week": dates.strftime("%a"), "is_weekend": (dates.dayofweek >= 5).astype(int)})

dim_mode = (d.groupby("Shipping Mode")["Days for shipment (scheduled)"].first().reset_index()
            .rename(columns={"Shipping Mode": "shipping_mode", "Days for shipment (scheduled)": "scheduled_days"}))
dim_mode.insert(0, "mode_key", range(1, len(dim_mode) + 1))

routes = d[["Market", "Order Region", "Order Country", "Order State", "Order City"]].drop_duplicates().reset_index(drop=True)
routes.columns = ["market", "region", "country", "state", "city"]
routes.insert(0, "route_key", range(1, len(routes) + 1))

dim_product = (d.groupby("Product Card Id").agg(product_name=("Product Name", "first"), category_id=("Category Id", "first"),
               category_name=("Category Name", "first"), department_name=("Department Name", "first")).reset_index()
               .rename(columns={"Product Card Id": "product_key"}))
dim_customer = (d.groupby("Customer Id").agg(segment=("Customer Segment", "first"), customer_country=("Customer Country", "first")).reset_index()
                .rename(columns={"Customer Id": "customer_key"}))

f = d.merge(routes.rename(columns={"market": "Market", "region": "Order Region", "country": "Order Country", "state": "Order State", "city": "Order City"}),
            on=["Market", "Order Region", "Order Country", "Order State", "Order City"], how="left")
f = f.merge(dim_mode[["mode_key", "shipping_mode"]], left_on="Shipping Mode", right_on="shipping_mode", how="left")
fact = pd.DataFrame({
    "shipment_key": f["Order Item Id"], "order_id": f["Order Id"],
    "order_date_key": dkey(f.order_date), "ship_date_key": dkey(f.ship_date),
    "route_key": f.route_key, "mode_key": f.mode_key, "product_key": f["Product Card Id"], "customer_key": f["Customer Id"],
    "scheduled_days": f["Days for shipment (scheduled)"], "actual_days": f["Days for shipping (real)"],
    "delay_days": f["Days for shipping (real)"] - f["Days for shipment (scheduled)"],
    "is_canceled": (f["Delivery Status"] == "Shipping canceled").astype(int),
    "delivery_status": f["Delivery Status"], "order_status": f["Order Status"],
    "quantity": f["Order Item Quantity"], "order_item_total": f["Order Item Total"].round(2),
})
# canceled shipments carry meaningless day counts, so they are never counted as late (or on time)
fact["is_late"] = ((fact.delay_days > 0) & (fact.is_canceled == 0)).astype(int)
ok = fact.is_canceled == 0
assert (fact.is_late[ok] == f["Late_delivery_risk"][ok]).all(), "late flag disagrees with source on non-canceled rows"
assert fact.route_key.notna().all() and fact.mode_key.notna().all()

con = sqlite3.connect(DB)
for name, df in [("Dim_Date", dim_date), ("Dim_ShippingMode", dim_mode), ("Dim_Route", routes), ("Dim_Product", dim_product),
                 ("Dim_Customer", dim_customer), ("Fact_Shipments", fact)]:
    df.to_sql(name, con, if_exists="replace", index=False)
con.executescript("""
CREATE INDEX IF NOT EXISTS ix_f_route ON Fact_Shipments(route_key);
CREATE INDEX IF NOT EXISTS ix_f_mode ON Fact_Shipments(mode_key);
CREATE INDEX IF NOT EXISTS ix_f_date ON Fact_Shipments(order_date_key);
""")
con.commit()
print({n: len(x) for n, x in [("Fact_Shipments", fact), ("Dim_Route", routes), ("Dim_Product", dim_product), ("Dim_Customer", dim_customer), ("Dim_ShippingMode", dim_mode), ("Dim_Date", dim_date)]})
