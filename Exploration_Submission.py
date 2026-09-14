from pathlib import Path


# Imports and Database Connection
import sqlite3
import pandas as pd
DB_PATH = Path(__file__).resolve().parent / "data" / "comm_log.db"
conn = sqlite3.connect(DB_PATH)


# Load the Source Tables
campaign = pd.read_sql_query(
    "SELECT * FROM campaign",
    conn
)
comm_log = pd.read_sql_query(
    "SELECT * FROM communication_log",
    conn
)


# Initial Data Inspection
print("CAMPAIGN")
print(campaign)
print("\nCOMMUNICATION LOG")
print(comm_log)


# Query 1: Naive Row Count
query1 = """
SELECT COUNT(*) AS total_rows
FROM communication_log;
"""
result1 = pd.read_sql_query(query1, conn)
print(result1)


# Query 2: Attempts by Campaign
query2 = """
SELECT
    communication_id,
    COUNT(*) AS send_attempts
FROM communication_log
GROUP BY communication_id
ORDER BY communication_id;
"""
result2 = pd.read_sql_query(query2, conn)
print(result2)


# Query 3: Campaign-Level Summary
query3 = """
SELECT
    c.id,
    c.parent_id,
    c.name,
    c.creation_status,
    c.processing_status,
    COUNT(cl.id) AS send_attempts
FROM campaign c
LEFT JOIN communication_log cl
    ON c.id = cl.communication_id
GROUP BY
    c.id,
    c.parent_id,
    c.name,
    c.creation_status,
    c.processing_status
ORDER BY c.id;
"""
result3 = pd.read_sql_query(query3, conn)
print(result3)


# Query 4: Family A Retry Chain
query = """
SELECT
    communication_id,
    customer_id,
    delivery_status,
    sent_time
FROM communication_log
WHERE communication_id IN (9001, 9002, 9003)
ORDER BY customer_id, sent_time;
"""
result4 = pd.read_sql_query(query, conn)
print(result4.to_string(index=False))


# Query 5: Family B Retry Chain
query5 = """
SELECT
    cl.communication_id,
    cl.customer_id,
    cl.delivery_status,
    cl.sent_time
FROM communication_log cl
WHERE cl.communication_id IN (9201, 9202)
ORDER BY
    cl.customer_id,
    cl.sent_time;
    """
result5 = pd.read_sql_query(query5, conn)
print(result5.to_string(index=False))


# Query 6: Standalone Campaign
query6 = """
SELECT
    communication_id,
    customer_id,
    delivery_status,
    sent_time
FROM communication_log
WHERE communication_id = 9101
ORDER BY sent_time;
"""
result6 = pd.read_sql_query(query6, conn)
print(result6.to_string(index=False))


# Query 7: Reconciliation Bridge
query7 = """
WITH RECURSIVE campaign_chain AS (
    SELECT
        id AS campaign_id,
        id AS root_id
    FROM campaign
    WHERE merchant_id = 501
      AND parent_id IS NULL
    UNION ALL
    SELECT
        c.id AS campaign_id,
        cc.root_id
    FROM campaign c
    JOIN campaign_chain cc
        ON c.parent_id = cc.campaign_id
    WHERE c.merchant_id = 501
),
base_logs AS (
    SELECT
        cl.*
    FROM communication_log cl
    WHERE cl.merchant_id = 501
      AND cl.communication_type = '2'
      AND cl.sent_time >= '2026-10-01'
      AND cl.sent_time < '2026-11-01'
),
eligible_logs AS (
    SELECT
        bl.*,
        cc.root_id
    FROM base_logs bl
    JOIN campaign c
        ON c.id = bl.communication_id
    JOIN campaign_chain cc
        ON cc.campaign_id = bl.communication_id
    WHERE c.creation_status IN
        ('approved', 'aborted', 'resumed', 'stopped')
      AND c.processing_status = 'processed'
),
family_summary AS (
    SELECT
        root_id,
        COUNT(*) AS send_attempts,
        COUNT(DISTINCT customer_id) AS distinct_customers
    FROM eligible_logs
    GROUP BY root_id
),
root_campaigns AS (
    SELECT
        c.id AS root_id,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM campaign child
                WHERE child.parent_id = c.id
                  AND child.merchant_id = c.merchant_id
            )
            THEN 1
            ELSE 0
        END AS has_retry
    FROM campaign c
    WHERE c.merchant_id = 501
      AND c.parent_id IS NULL
),
final_calculation AS (
    SELECT
        fs.root_id,
        fs.send_attempts,
        fs.distinct_customers,
        rc.has_retry,
        CASE
            WHEN rc.has_retry = 1
                THEN fs.distinct_customers
            ELSE fs.send_attempts
        END AS qualifying_sends
    FROM family_summary fs
    JOIN root_campaigns rc
        ON rc.root_id = fs.root_id
)
SELECT
    0 AS step,
    'Naive count of communication-log rows' AS description,
    (SELECT COUNT(*)
     FROM base_logs) AS result,
    'Starting point: every send attempt is counted.' AS reason
UNION ALL
SELECT
    1 AS step,
    'Apply campaign eligibility rules' AS description,
    (SELECT COUNT(*)
     FROM eligible_logs) AS result,
    'Exclude campaigns that have not cleared approval or processing.' AS reason
UNION ALL
SELECT
    2 AS step,
    'Collapse eligible retry chains' AS description,
    (SELECT SUM(qualifying_sends)
     FROM final_calculation) AS result,
    'Customers are counted once within a retry chain; standalone campaigns retain every send event.' AS reason
ORDER BY step;
"""
result7 = pd.read_sql_query(query, conn)
print("\nRECONCILIATION BRIDGE")
print(result7.to_string(index=False))


# Query 8: Campaign Validation
query8 = """
SELECT
    c.id,
    c.parent_id,
    c.name,
    c.creation_status,
    c.processing_status,
    COUNT(cl.id) AS send_attempts
FROM campaign c
LEFT JOIN communication_log cl
    ON c.id = cl.communication_id
WHERE c.merchant_id = 501
GROUP BY
    c.id,
    c.parent_id,
    c.name,
    c.creation_status,
    c.processing_status
ORDER BY c.id;
"""
result8 = pd.read_sql_query(query8, conn)
print(result8.to_string(index=False))


# Query 9: Final Target Base
query9 = """
WITH RECURSIVE campaign_chain AS (
    SELECT
        id AS campaign_id,
        id AS root_id
    FROM campaign
    WHERE merchant_id = 501
      AND parent_id IS NULL
    UNION ALL
    SELECT
        c.id AS campaign_id,
        cc.root_id
    FROM campaign c
    JOIN campaign_chain cc
        ON c.parent_id = cc.campaign_id
    WHERE c.merchant_id = 501
),
eligible_logs AS (
    SELECT
        cl.*,
        cc.root_id
    FROM communication_log cl
    JOIN campaign c
        ON c.id = cl.communication_id
    JOIN campaign_chain cc
        ON cc.campaign_id = cl.communication_id
    WHERE cl.merchant_id = 501
      AND cl.communication_type = '2'
      AND cl.sent_time >= '2026-10-01'
      AND cl.sent_time < '2026-11-01'
      AND c.creation_status IN
          ('approved', 'aborted', 'resumed', 'stopped')
      AND c.processing_status = 'processed'
),
family_summary AS (
    SELECT
        root_id,
        COUNT(*) AS send_attempts,
        COUNT(DISTINCT customer_id) AS distinct_customers
    FROM eligible_logs
    GROUP BY root_id
),
root_campaigns AS (
    SELECT
        c.id AS root_id,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM campaign child
                WHERE child.parent_id = c.id
                  AND child.merchant_id = c.merchant_id
            )
            THEN 1
            ELSE 0
        END AS has_retry
    FROM campaign c
    WHERE c.merchant_id = 501
      AND c.parent_id IS NULL
),
final_calculation AS (
    SELECT
        fs.root_id,
        fs.send_attempts,
        fs.distinct_customers,
        rc.has_retry,
        CASE
            WHEN rc.has_retry = 1
                THEN fs.distinct_customers
            ELSE fs.send_attempts
        END AS qualifying_sends
    FROM family_summary fs
    JOIN root_campaigns rc
        ON rc.root_id = fs.root_id
)
SELECT
    SUM(qualifying_sends) AS target_base
FROM final_calculation;
"""
result9 = pd.read_sql_query(query9, conn)
print("\nFINAL TARGET BASE")
print(result9.to_string(index=False))


# Validation 1: Naive Count
query_validation1 = """
SELECT COUNT(*) AS total_send_attempts
FROM communication_log
WHERE merchant_id = 501
  AND communication_type = '2'
  AND sent_time >= '2026-10-01'
  AND sent_time < '2026-11-01';
  """
result_validation1 = pd.read_sql_query(query_validation1, conn)
print("\nVALIDATION 1 - Naive Count of Communication Log Rows")
print(result_validation1.to_string(index=False))


# Validation 2: Ineligible Campaigns
query_validation2 = """
SELECT
    c.id,
    c.name,
    c.creation_status,
    c.processing_status,
    COUNT(cl.id) AS send_attempts
FROM campaign c
LEFT JOIN communication_log cl
    ON c.id = cl.communication_id
WHERE c.merchant_id = 501
GROUP BY
    c.id,
    c.name,
    c.creation_status,
    c.processing_status
HAVING c.creation_status = 'approval_awaiting';
"""
result_validation2 = pd.read_sql_query(query_validation2, conn)
print("\nVALIDATION 2 - Ineligible Campaigns")
print(result_validation2.to_string(index=False))


# Validation 3: Retry Chains
query_validation3 = """
SELECT
    id AS campaign_id,
    parent_id,
    name
FROM campaign
WHERE merchant_id = 501
  AND parent_id IS NOT NULL
ORDER BY id;
"""
result_validation3 = pd.read_sql_query(query_validation3, conn)
print("\nVALIDATION 3 - Retry Chains")
print(result_validation3.to_string(index=False))


# Validation 4: Retry-Family Counts
query_validation4 = """
WITH RECURSIVE campaign_chain AS (
    SELECT
        id AS campaign_id,
        id AS root_id
    FROM campaign
    WHERE merchant_id = 501
      AND parent_id IS NULL
    UNION ALL
    SELECT
        c.id AS campaign_id,
        cc.root_id
    FROM campaign c
    JOIN campaign_chain cc
        ON c.parent_id = cc.campaign_id
    WHERE c.merchant_id = 501
),
eligible_logs AS (
    SELECT
        cl.*,
        cc.root_id
    FROM communication_log cl
    JOIN campaign_chain cc
        ON cc.campaign_id = cl.communication_id
    JOIN campaign c
        ON c.id = cl.communication_id
    WHERE cl.merchant_id = 501
      AND cl.communication_type = '2'
      AND cl.sent_time >= '2026-10-01'
      AND cl.sent_time < '2026-11-01'
      AND c.creation_status IN
          ('approved', 'aborted', 'resumed', 'stopped')
      AND c.processing_status = 'processed'
)
SELECT
    root_id,
    COUNT(*) AS send_attempts,
    COUNT(DISTINCT customer_id) AS distinct_customers
FROM eligible_logs
GROUP BY root_id
ORDER BY root_id;
"""
result_validation4 = pd.read_sql_query(query_validation4, conn)
print("\nVALIDATION 4 - Retry-Family Counts")
print(result_validation4.to_string(index=False))


# Close Database Connection
conn.close()