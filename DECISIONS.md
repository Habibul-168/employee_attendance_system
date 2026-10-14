# DECISIONS.md

1. **Indexes.**
   - On `employees`: unique `emp_code` ensures employee uniqueness; compound `(department, joined_on)` and `(joined_on)` serve headcount filtering and avoid collection scans during department summaries.
   - On `attendance_logs`: unique compound `(emp_code, date)` guarantees at most one record per employee per day; `(date, emp_code)` serves paginated attendance listing; `(emp_code, punch_in)` provides instant punch-out lookups; `(date, late_minutes, emp_code)` accelerates late leaderboard queries.
   - Rejected: a standalone index on `date` alone, because the compound `(date, emp_code)` index already satisfies date prefix filters and sorting.

2. **Punch-in race.**
   Both requests calculate the attendance date and attempt `insert_one()`. The database's unique compound index on `(emp_code, date)` guarantees atomicity: the first insert succeeds (201 Created), while the second fails with `DuplicateKeyError`. Our code catches this error and immediately returns HTTP 409 Conflict.

3. **Ties.**
   The aggregation uses MongoDB's `$rank` window function to assign standard competition ranks (e.g., 1, 2, 2, 4). The `limit` filter (`rank <= limit`) runs after ranking. If two employees tie at the cutoff rank, both are returned (exceeding `limit` rows if needed), sorted by `emp_code` ascending.

4. **Headcount.**
   The department summary aggregation starts from the `employees` collection, filtering `joined_on <= month_end`. Each matching employee contributes to headcount (`$sum: 1`), and logs are pulled in via `$lookup`. Employees with zero logs still increment headcount.

5. **One thing you would change for 100x the data.**
   Pre-aggregate daily and monthly statistics into dedicated summary collections during punch-out and regularization events, avoiding cross-collection aggregations over millions of raw log documents at read time.
