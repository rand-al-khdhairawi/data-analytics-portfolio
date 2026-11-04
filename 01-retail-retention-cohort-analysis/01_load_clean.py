"""Load UCI Online Retail II, clean it, and build customers/orders/order_items tables in SQLite."""
import sqlite3, sys, re
import pandas as pd
src, out = sys.argv[1], sys.argv[2]
raw = pd.read_csv(src, encoding="latin-1", parse_dates=["InvoiceDate"])
raw.columns = ["invoice","stockcode","description","quantity","invoice_date","price","customer_id","country"]
log = {"raw_rows": len(raw)}
log["cancellation_rows"] = int(raw.invoice.astype(str).str.startswith("C").sum())
d = raw[~raw.invoice.astype(str).str.startswith("C")]
d = d[(d.quantity > 0) & (d.price > 0)]
log["no_customer_id_rows"] = int(d.customer_id.isna().sum())
d = d.dropna(subset=["customer_id"])
d = d[d.stockcode.astype(str).str.match(r"^\d{5}")]  # real products only (drops POST, M, BANK CHARGES, ...)
d = d.drop_duplicates()
d["customer_id"] = d.customer_id.astype(int)
d["line_total"] = d.quantity * d.price
log["clean_rows"] = len(d)

def family(desc):
    s = str(desc).upper()
    rules = [("Christmas", r"CHRISTMAS|XMAS|ADVENT|SANTA|REINDEER|SNOW"),
             ("Bags & Storage", r"\bBAG\b|BASKET|BOX|TIN\b|JAR\b|CASE|HOLDER|ORGANI"),
             ("Kitchen & Dining", r"MUG|CUP|TEA|PLATE|BOWL|CAKE|SPOON|JUG|KITCHEN|TEAPOT|COASTER|BAKING|APRON"),
             ("Lights & Candles", r"LIGHT|CANDLE|LANTERN|T-LIGHT|TEALIGHT|LAMP"),
             ("Cards, Paper & Wrap", r"CARD|WRAP|PAPER|RIBBON|STICKER|NOTEBOOK|GIFT TAG|STATIONERY|PENCIL"),
             ("Decor & Frames", r"FRAME|CLOCK|SIGN|MIRROR|HEART|BIRD|DOOR|WALL|HANGING|CUSHION|GARLAND"),
             ("Toys & Party", r"TOY|PARTY|BALLOON|GAME|DOLL|CHILDREN|KIDS|BUNTING")]
    for name, pat in rules:
        if re.search(pat, s): return name
    return "Other Home & Gift"
prod = d.drop_duplicates("stockcode")[["stockcode","description"]]
fam = prod.assign(family=prod.description.map(family)).set_index("stockcode").family
d["category"] = d.stockcode.map(fam)

orders = (d.groupby("invoice").agg(customer_id=("customer_id","first"), order_ts=("invoice_date","min"),
          order_total=("line_total","sum")).reset_index().rename(columns={"invoice":"order_id"}))
orders["order_date"] = orders.order_ts.dt.strftime("%Y-%m-%d"); orders = orders.drop(columns="order_ts")
orders["order_id"] = orders.order_id.astype(str)
cust = (d.sort_values("invoice_date").groupby("customer_id").agg(country=("country","first"),
        acquisition_date=("invoice_date","min")).reset_index())
cust["acquisition_date"] = cust.acquisition_date.dt.strftime("%Y-%m-%d")
cust["channel"] = cust.country.map(lambda c: "United Kingdom" if c=="United Kingdom" else ("Europe (ex-UK)" if c in {
 "Germany","France","EIRE","Spain","Netherlands","Belgium","Switzerland","Portugal","Italy","Austria","Sweden","Denmark","Finland","Norway","Poland","Greece","Cyprus","Malta","Iceland","Lithuania","Channel Islands","Czech Republic","Lebanon"} else "Rest of world"))
items = d[["invoice","stockcode","description","category","quantity","price"]].rename(
    columns={"invoice":"order_id","price":"unit_price"}); items["order_id"] = items.order_id.astype(str)
items["category"] = items.category
con = sqlite3.connect(out)
cust.to_sql("customers", con, if_exists="replace", index=False)
orders.to_sql("orders", con, if_exists="replace", index=False)
items.to_sql("order_items", con, if_exists="replace", index=False)
log.update(customers=len(cust), orders=len(orders), items=len(items),
           date_min=orders.order_date.min(), date_max=orders.order_date.max())
print(log)
print(cust.channel.value_counts().to_dict()); print(items.category.value_counts().to_dict())
