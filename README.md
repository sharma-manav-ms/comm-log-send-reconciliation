# Comm-Log Send Reconciliation

## Project Overview

This project solves the **Comm-Log Send Reconciliation** data analyst
take-home assignment.

The objective is to reproduce Finance's reported `target_base` for:

-   **Merchant:** `501`
-   **Period:** October 2026
-   **Communication type:** Campaign (`'2'`)
-   **Expected Finance target_base:** `22`

The project investigates why a straightforward count of
communication-log rows does not match the Finance number and builds a
SQL-based reconciliation that correctly produces `22`.

------------------------------------------------------------------------

## Assignment Objective

Finance defines `target_base` as the number of qualifying customers
reached for an **underlying communication**.

An underlying communication consists of:

-   A standalone campaign, or
-   A campaign together with all retry campaigns chained through
    `parent_id`.

For a retry chain, the same customer is counted once across the complete
chain.

For a standalone campaign, every send event is counted separately, even
when the same customer appears more than once.

The assignment also requires campaigns to satisfy the reporting
eligibility rules before their sends are included.

------------------------------------------------------------------------

## Project Files

``` text
Comm_Log_Assignment/
│
├── README.md
├── exploration.py
├── campaign.csv
├── communication_log.csv
├── generate_dataset.py
│
└── data/
    └── comm_log.db
```

### File descriptions

  -----------------------------------------------------------------------
  File                                Purpose
  ----------------------------------- -----------------------------------
  `README.md`                         Project documentation and
                                      methodology

  `comm_log.db`                       SQLite database containing the two
                                      source tables

  `campaign.csv`                      CSV representation of the
                                      `campaign` table

  `communication_log.csv`             CSV representation of the
                                      `communication_log` table

  `generate_dataset.py`               Script that generates the synthetic
                                      source data

  `submissions/exploration.py`        Python script used for SQL
                                      investigation and validation
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## Data Model

The SQLite database contains two tables.

### 1. `campaign`

Important columns:

  Column                Meaning
  --------------------- ----------------------------------------------
  `id`                  Campaign ID
  `merchant_id`         Owning merchant
  `parent_id`           Parent campaign when the campaign is a retry
  `name`                Campaign name
  `creation_status`     Campaign creation/approval state
  `processing_status`   Send-processing state

A campaign is eligible for official reporting only when:

``` text
creation_status IN ('approved', 'aborted', 'resumed', 'stopped')
AND
processing_status = 'processed'
```

`approval_awaiting` campaigns are not eligible.

### 2. `communication_log`

Important columns:

  Column                 Meaning
  ---------------------- ------------------------------------
  `id`                   Individual send-attempt ID
  `merchant_id`          Owning merchant
  `communication_id`     Campaign ID
  `customer_id`          Targeted customer
  `communication_type`   `'2'` represents Campaign
  `delivery_status`      `900` = delivered, `1100` = failed
  `sent_time`            Time of the send
  `scheduled_time`       Scheduled send time
  `credit_used`          Credits consumed
  `channel`              Send channel

------------------------------------------------------------------------

## Business Rules Used

### 1. Merchant filter

Only data for:

``` sql
merchant_id = 501
```

is included.

### 2. Date filter

Only October 2026 sends are included:

``` sql
sent_time >= '2026-10-01'
AND sent_time < '2026-11-01'
```

Using an exclusive upper bound avoids including any records from
November 1 onward.

### 3. Communication type

Only campaign communications are included:

``` sql
communication_type = '2'
```

### 4. Campaign eligibility

A campaign must have:

``` sql
creation_status IN ('approved', 'aborted', 'resumed', 'stopped')
AND processing_status = 'processed'
```

### 5. Retry chains

If:

``` text
B.parent_id = A
```

then B is a retry of A.

A chain can contain multiple levels:

``` text
A → B → C
```

All campaigns in the chain represent one underlying communication.

### 6. Counting retry families

For a retry family:

``` sql
COUNT(DISTINCT customer_id)
```

is used.

A customer who appears in multiple retry attempts is counted once.

### 7. Counting standalone campaigns

For a standalone campaign with no retry chain:

``` sql
COUNT(*)
```

is used.

Repeated sends to the same customer are treated as separate events.

------------------------------------------------------------------------

# Investigation and Reconciliation

## Step 1 --- Naive Count

The first query counts every communication-log row:

``` sql
SELECT COUNT(*) AS total_send_attempts
FROM communication_log
WHERE merchant_id = 501
  AND communication_type = '2'
  AND sent_time >= '2026-10-01'
  AND sent_time < '2026-11-01';
```

Result:

``` text
30
```

This is the naive starting point.

------------------------------------------------------------------------

## Step 2 --- Inspect Send Attempts by Campaign

``` sql
SELECT
    communication_id,
    COUNT(*) AS send_attempts
FROM communication_log
WHERE merchant_id = 501
  AND communication_type = '2'
  AND sent_time >= '2026-10-01'
  AND sent_time < '2026-11-01'
GROUP BY communication_id
ORDER BY communication_id;
```

The campaign-level distribution is:

     Campaign   Send attempts
  ----------- ---------------
         9001              10
         9002               2
         9003               1
         9004               4
         9101               7
         9201               5
         9202               1
    **Total**          **30**

------------------------------------------------------------------------

## Step 3 --- Apply Campaign Eligibility

Campaign `9004` has:

``` text
creation_status = approval_awaiting
processing_status = processed
```

It therefore fails the creation-status eligibility requirement.

It has 4 communication-log rows.

The reconciliation becomes:

``` text
30 - 4 = 26
```

------------------------------------------------------------------------

## Step 4 --- Reconcile Retry Family 9001 → 9002 → 9003

The first retry family is:

``` text
9001 → 9002 → 9003
```

It contains:

``` text
13 send attempts
10 distinct customers
```

Therefore the retry family contributes:

``` text
10
```

rather than 13.

The reduction is:

``` text
13 - 10 = 3
```

------------------------------------------------------------------------

## Step 5 --- Check Standalone Campaign 9101

Campaign `9101` has no retry chain.

It contains:

``` text
7 send events
6 distinct customers
```

Customer `C20` appears twice.

Because `9101` is standalone, both C20 send events are legitimate
separate events.

Therefore:

``` text
9101 contribution = 7
```

not 6.

------------------------------------------------------------------------

## Step 6 --- Reconcile Retry Family 9201 → 9202

The second retry family is:

``` text
9201 → 9202
```

It contains:

``` text
6 send attempts
5 distinct customers
```

Therefore the family contributes:

``` text
5
```

rather than 6.

The reduction is:

``` text
6 - 5 = 1
```

------------------------------------------------------------------------

# Reconciliation Bridge

  --------------------------------------------------------------------------------
                  Step Description                          Result Reason
  -------------------- ---------------------- -------------------- ---------------
                     0 Naive count of                       **30** Starting point;
                       communication-log rows                      each row is a
                                                                   send attempt

                     1 Apply campaign                       **26** Exclude 4 sends
                       eligibility rules                           from ineligible
                                                                   campaign `9004`

                     2 Reconcile retry family               **23** 13 attempts
                       `9001 → 9002 → 9003`                        represent 10
                                                                   customers

                     3 Reconcile retry family               **22** 6 attempts
                       `9201 → 9202`                               represent 5
                                                                   customers

                 Final `target_base`                        **22** Final
                                                                   reconciled
                                                                   value
  --------------------------------------------------------------------------------

The final calculation can also be expressed as:

``` text
9001 → 9002 → 9003 = 10
9101               = 7
9201 → 9202       = 5
                       ──
                       22
```

------------------------------------------------------------------------

# Final SQL

The following query automatically discovers retry chains using a
recursive CTE. It starts only with campaigns where `parent_id IS NULL`,
ensuring that retry campaigns are assigned to their actual root
campaign.

``` sql
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
```

Expected result:

``` text
target_base
-----------
22
```

------------------------------------------------------------------------

# Validation

## Validate retry families

The following query can be used to inspect the intermediate family-level
results:

``` sql
WITH RECURSIVE campaign_chain AS (

    SELECT
        id AS campaign_id,
        id AS root_id
    FROM campaign
    WHERE merchant_id = 501
      AND parent_id IS NULL

    UNION ALL

    SELECT
        c.id,
        cc.root_id
    FROM campaign c
    JOIN campaign_chain cc
        ON c.parent_id = cc.campaign_id
    WHERE c.merchant_id = 501
)

SELECT
    cc.root_id,
    COUNT(cl.id) AS send_attempts,
    COUNT(DISTINCT cl.customer_id) AS distinct_customers
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
GROUP BY cc.root_id
ORDER BY cc.root_id;
```

Expected intermediate result:

    Root campaign   Send attempts   Distinct customers
  --------------- --------------- --------------------
             9001              13                   10
             9101               7                    6
             9201               6                    5

Interpretation:

``` text
9001 retry family → 10
9101 standalone   → 7
9201 retry family → 5

Total             → 22
```

------------------------------------------------------------------------

## Validate Ineligible Campaigns

``` sql
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
```

Expected finding:

``` text
Campaign 9004
4 send attempts
creation_status = approval_awaiting
```

------------------------------------------------------------------------

## Validate Repeated Customers

``` sql
SELECT
    communication_id,
    customer_id,
    COUNT(*) AS occurrences
FROM communication_log
WHERE merchant_id = 501
  AND communication_type = '2'
GROUP BY
    communication_id,
    customer_id
HAVING COUNT(*) > 1
ORDER BY communication_id, customer_id;
```

Expected finding:

``` text
communication_id = 9101
customer_id = C20
occurrences = 2
```

This validates why a global `COUNT(DISTINCT customer_id)` would be
incorrect.

------------------------------------------------------------------------

# Key Observations

1.  Campaign `9004` contains communication-log rows even though its
    creation status is `approval_awaiting`. Those rows exist in the raw
    data but do not qualify for official reporting.

2.  Retry chains can contain multiple levels. The chain
    `9001 → 9002 → 9003` demonstrates why the reconciliation must follow
    the full parent-child hierarchy instead of only looking at direct
    parent relationships.

3.  Campaign `9101` contains two sends to customer `C20`. This is not
    treated as a duplicate to remove because `9101` is a standalone
    campaign. Each send is a separate event.

4.  A naive row count gives `30`, while the reconciled `target_base` is
    `22`.

------------------------------------------------------------------------

# Final Result

``` text
Finance target_base = 22
Reconciled target_base = 22
```

The reconciliation is:

``` text
30  naive send-attempt count
 ↓
26  after excluding ineligible campaign 9004
 ↓
23  after reconciling 9001 → 9002 → 9003
 ↓
22  after reconciling 9201 → 9202
```

------------------------------------------------------------------------

# How to Run

## Using Python

From the `submissions` directory:

``` bash
python exploration.py
```

The Python script uses SQLite through Python's built-in `sqlite3` module
and pandas for displaying query results.

## Using SQLite directly

Open the database:

``` bash
sqlite3 comm_log.db
```

Then run SQL queries directly.

You can inspect the database with:

``` sql
.tables
```

and:

``` sql
.schema campaign
.schema communication_log
```

------------------------------------------------------------------------

# Technologies Used

-   Python 3
-   SQLite
-   SQL
-   pandas
-   Recursive Common Table Expressions (CTEs)

------------------------------------------------------------------------

# Source Documents

This project is based on the provided:

-   Data Analyst Take-Home Assignment
-   Comm-Log Reconciliation Data Dictionary
-   Synthetic dataset generation script

The assignment requires the final reconciliation bridge, executable SQL,
and a short discussion of surprising data observations.
