-- Project 3: KPI layer over the star schema (SQLite). Order-level, excluding canceled shipments from delivery KPIs.
DROP VIEW IF EXISTS v_orders;
CREATE VIEW v_orders AS
SELECT order_id,
       MIN(order_date_key) AS order_date_key, MIN(route_key) AS route_key, MIN(mode_key) AS mode_key,
       MIN(scheduled_days) AS scheduled_days, MIN(actual_days) AS actual_days, MIN(delay_days) AS delay_days,
       MAX(is_late) AS is_late, MAX(is_canceled) AS is_canceled,
       ROUND(SUM(order_item_total), 2) AS order_value
FROM Fact_Shipments GROUP BY order_id;

DROP VIEW IF EXISTS v_delivered;
CREATE VIEW v_delivered AS SELECT * FROM v_orders WHERE is_canceled = 0;

-- KPIs by shipping mode (carrier service level)
DROP VIEW IF EXISTS v_kpi_mode;
CREATE VIEW v_kpi_mode AS
SELECT m.shipping_mode, m.scheduled_days,
       COUNT(*) AS orders,
       ROUND(100.0 * (1 - AVG(o.is_late)), 2) AS otd_pct,
       ROUND(AVG(o.actual_days), 2) AS avg_lead_time,
       ROUND(AVG(o.delay_days), 2) AS avg_delay_days,
       ROUND(SUM(CASE WHEN o.is_late = 1 THEN o.order_value ELSE 0 END), 0) AS delayed_order_value
FROM v_delivered o JOIN Dim_ShippingMode m USING (mode_key) GROUP BY m.shipping_mode, m.scheduled_days;

-- KPIs by region, with window-function share of all late orders
DROP VIEW IF EXISTS v_kpi_region;
CREATE VIEW v_kpi_region AS
WITH r AS (
    SELECT d.region, COUNT(*) AS orders, SUM(o.is_late) AS late_orders,
           ROUND(100.0 * (1 - AVG(o.is_late)), 2) AS otd_pct, ROUND(AVG(o.actual_days), 2) AS avg_lead_time
    FROM v_delivered o JOIN Dim_Route d USING (route_key) GROUP BY d.region
)
SELECT *, ROUND(100.0 * late_orders / SUM(late_orders) OVER (), 2) AS share_of_late FROM r;

-- Monthly OTD trend
DROP VIEW IF EXISTS v_kpi_month;
CREATE VIEW v_kpi_month AS
SELECT t.year_month, COUNT(*) AS orders, ROUND(100.0 * (1 - AVG(o.is_late)), 2) AS otd_pct
FROM v_delivered o JOIN Dim_Date t ON t.date_key = o.order_date_key GROUP BY t.year_month;

-- Pareto by destination country: cumulative share of late orders
DROP VIEW IF EXISTS v_pareto_country;
CREATE VIEW v_pareto_country AS
WITH c AS (
    SELECT d.country, d.region, COUNT(*) AS orders, SUM(o.is_late) AS late_orders
    FROM v_delivered o JOIN Dim_Route d USING (route_key) GROUP BY d.country, d.region
)
SELECT country, region, orders, late_orders, ROUND(1.0 * late_orders / orders, 4) AS late_rate,
       ROUND(1.0 * SUM(late_orders) OVER (ORDER BY late_orders DESC, country) / SUM(late_orders) OVER (), 4) AS cum_share_late,
       ROW_NUMBER() OVER (ORDER BY late_orders DESC, country) AS rnk
FROM c;
