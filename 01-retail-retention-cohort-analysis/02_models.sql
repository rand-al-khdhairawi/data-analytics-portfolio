-- Project 1 (UCI Online Retail II): SQL modeling layer (SQLite dialect; notes for PostgreSQL/BigQuery at the bottom)

-- 1) Clean orders: dedupe, drop non-positive totals, sequence each customer's orders,
--    and compute days since previous order with LAG().
DROP VIEW IF EXISTS v_orders_clean;
CREATE VIEW v_orders_clean AS
WITH dedup AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_date) AS rn
    FROM orders
    WHERE order_total > 0
),
base AS (
    SELECT order_id, customer_id, order_date, order_total
    FROM dedup WHERE rn = 1
)
SELECT b.*,
       ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS order_seq,
       julianday(order_date) - julianday(
           LAG(order_date) OVER (PARTITION BY customer_id ORDER BY order_date, order_id)
       ) AS days_since_prev,
       strftime('%Y-%m-01', order_date) AS order_month
FROM base b;

-- 2) Monthly acquisition cohort = month of first order.
DROP VIEW IF EXISTS v_customer_cohort;
CREATE VIEW v_customer_cohort AS
SELECT o.customer_id,
       c.channel,
       strftime('%Y-%m-01', MIN(o.order_date)) AS cohort_month,
       MIN(o.order_date) AS first_order_date
FROM v_orders_clean o
JOIN customers c USING (customer_id)
GROUP BY o.customer_id, c.channel
-- Data starts 2009-12-01, so customers first seen that month are an existing base, not new acquisitions.
HAVING strftime('%Y-%m-01', MIN(o.order_date)) > '2009-12-01';

-- 3) Cohort retention: share of each cohort ordering in month N after acquisition.
DROP VIEW IF EXISTS v_cohort_retention;
CREATE VIEW v_cohort_retention AS
WITH activity AS (
    SELECT DISTINCT o.customer_id, k.cohort_month, o.order_month,
           (CAST(strftime('%Y', o.order_month) AS INT) - CAST(strftime('%Y', k.cohort_month) AS INT)) * 12
         + (CAST(strftime('%m', o.order_month) AS INT) - CAST(strftime('%m', k.cohort_month) AS INT)) AS month_n
    FROM v_orders_clean o
    JOIN v_customer_cohort k USING (customer_id)
),
sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size FROM v_customer_cohort GROUP BY cohort_month
)
SELECT a.cohort_month, a.month_n, s.cohort_size,
       COUNT(DISTINCT a.customer_id) AS active_customers,
       ROUND(1.0 * COUNT(DISTINCT a.customer_id) / s.cohort_size, 4) AS retention
FROM activity a JOIN sizes s USING (cohort_month)
GROUP BY a.cohort_month, a.month_n, s.cohort_size;

-- 4) Monthly revenue (recurring = revenue from customers' 2nd+ orders) and AOV by channel.
DROP VIEW IF EXISTS v_monthly_revenue;
CREATE VIEW v_monthly_revenue AS
SELECT order_month,
       ROUND(SUM(order_total), 2) AS revenue,
       ROUND(SUM(CASE WHEN order_seq > 1 THEN order_total ELSE 0 END), 2) AS repeat_revenue,
       COUNT(*) AS orders
FROM v_orders_clean WHERE order_month <= '2011-11-01'  -- Dec 2011 is a partial month
GROUP BY order_month;

DROP VIEW IF EXISTS v_aov_channel;
CREATE VIEW v_aov_channel AS
SELECT c.channel,
       strftime('%Y-%m-01', o.order_date) AS order_month,
       COUNT(*) AS orders,
       ROUND(AVG(o.order_total), 2) AS aov
FROM v_orders_clean o JOIN customers c USING (customer_id)
GROUP BY c.channel, order_month;

-- 5) RFM base table, snapshot = day after last order.
DROP VIEW IF EXISTS v_rfm;
CREATE VIEW v_rfm AS
WITH snap AS (SELECT date(MAX(order_date), '+1 day') AS d FROM v_orders_clean)
SELECT customer_id,
       CAST(julianday((SELECT d FROM snap)) - julianday(MAX(order_date)) AS INT) AS recency_days,
       COUNT(*) AS frequency,
       ROUND(SUM(order_total), 2) AS monetary
FROM v_orders_clean GROUP BY customer_id;

-- 6) 90-day repeat rate by first-order category.
--    Only customers who first ordered at least 90 days before the end of the data are included,
--    so every customer has had the same window to come back (avoids right-censoring bias).
DROP VIEW IF EXISTS v_first_order_category_repeat;
CREATE VIEW v_first_order_category_repeat AS
WITH first_cat AS (
    SELECT o.customer_id, i.category,
           ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY i.unit_price * i.quantity DESC) AS rk
    FROM v_orders_clean o
    JOIN order_items i USING (order_id)
    JOIN v_customer_cohort k USING (customer_id)   -- excludes the pre-existing Dec-2009 base
    WHERE o.order_seq = 1
),
second AS (
    SELECT customer_id, days_since_prev FROM v_orders_clean WHERE order_seq = 2
),
mature AS (
    SELECT customer_id FROM v_customer_cohort
    WHERE first_order_date <= (SELECT date(MAX(order_date), '-90 days') FROM v_orders_clean)
)
SELECT f.category,
       COUNT(*) AS customers,
       SUM(CASE WHEN s.days_since_prev <= 90 THEN 1 ELSE 0 END) AS repeaters,
       ROUND(1.0 * SUM(CASE WHEN s.days_since_prev <= 90 THEN 1 ELSE 0 END) / COUNT(*), 4) AS repeat_rate,
       ROUND(AVG(CASE WHEN s.days_since_prev <= 90 THEN s.days_since_prev END), 1) AS avg_days_to_second
FROM first_cat f
JOIN mature m USING (customer_id)
LEFT JOIN second s USING (customer_id)
WHERE f.rk = 1
GROUP BY f.category;

-- Porting: PostgreSQL -> DATE_TRUNC('month', d), d2 - d1 for day diffs;
-- BigQuery -> DATE_TRUNC(d, MONTH), DATE_DIFF(d2, d1, DAY).
