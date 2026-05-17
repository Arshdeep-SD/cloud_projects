# Transit Database — Design Notes

## Schema Decisions 

The schema uses **surrogate primary keys** for core tables while preserving **natural unique keys** where appropriate.

### Surrogate Keys

* `lines.line_id` (SERIAL PRIMARY KEY)
* `stops.stop_id` (SERIAL PRIMARY KEY)
* `line_stops.line_stop_id` (SERIAL PRIMARY KEY)
* `stop_events.stop_event_id` (SERIAL PRIMARY KEY)

These provide:

* Stable identifiers independent of business name changes
* Smaller, more efficient foreign keys
* Simpler joins and indexing
* Protection from cascading updates if natural names change

### Natural Keys (Enforced as UNIQUE)

* `lines.line_name` (UNIQUE)
* `stops.stop_name` (UNIQUE)
* `trips.trip_id` (natural primary key)

These ensure human-meaningful uniqueness while still allowing the system to map names to surrogate IDs during ingestion.

This hybrid approach combines performance and stability (surrogate keys) with real-world identity enforcement (natural keys).

---

## Constraints

### UNIQUE Constraints

* `lines.line_name`
* `stops.stop_name`
* `line_stops (line_id, sequence_number)`
* `line_stops (line_id, stop_id)`
* `stop_events (trip_id, sequence_number)`
* `stop_events (trip_id, stop_id)`

These prevent:

* Duplicate routes
* Duplicate stops
* Duplicate stop order positions within a line
* Duplicate stop events within a trip

### CHECK Constraints

* `vehicle_type` restricted to: `rail`, `bus`, `tram`, `ferry`, `other`
* `latitude BETWEEN -90 AND 90`
* `longitude BETWEEN -180 AND 180`
* `sequence_number > 0`
* `time_offset_minutes >= 0`
* `passengers_on >= 0`
* `passengers_off >= 0`

These ensure domain correctness (e.g., no impossible coordinates, no negative passengers).

### Foreign Keys

* `line_stops.line_id → lines.line_id`
* `line_stops.stop_id → stops.stop_id`
* `trips.line_id → lines.line_id`
* `stop_events.trip_id → trips.trip_id`
* `stop_events.stop_id → stops.stop_id`

These enforce referential integrity across the schema.

---

## Complex Query

The most complex query is **Q6: Average ridership by line**.

* It requires **two levels of aggregation**.
* First, total boardings must be computed per trip.
* Then, the average of those trip totals must be computed per line.

This prevents incorrectly averaging stop-level boardings directly.

The query structure:

1. Aggregate passengers per trip.
2. Join aggregated results to lines.
3. Compute average per line.

This layered aggregation makes it more complex than simple GROUP BY or filtering queries.

---

## Foreign Keys — Examples of Invalid Data They Prevent

1. **Trip referencing non-existent line**

   * Example: inserting a trip with `line_id = 9999` when no such line exists.
   * Prevented by FK constraint on `trips.line_id`.

2. **Stop event referencing non-existent trip**

   * Example: inserting stop events for `trip_id = 'X404'` when that trip does not exist.
   * Prevented by FK on `stop_events.trip_id`.

3. **Line-stop mapping referencing non-existent stop**

   * Example: `stop_id = 8888` not present in `stops`.
   * Prevented by FK on `line_stops.stop_id`.

---

## Why Relational (SQL) is a Good Fit for This Domain

Transit systems are highly structured and relational:

* Lines serve many stops.
* Trips belong to lines.
* Stop events belong to trips.
* Stops are shared across lines.

This creates a classic many-to-many relational model.

1. **Strong Integrity Enforcement**
   CHECK, UNIQUE, and FOREIGN KEY constraints ensure clean, reliable data.

2. **Efficient Joins & Aggregations**
   Queries like busiest stops, delay counts, and ridership averages rely on JOIN + GROUP BY — SQL excels at this.

3. **Transactional ETL Support**
   Staging tables and conflict handling (`ON CONFLICT DO NOTHING`) allow safe, idempotent data loading.

4. **Index Support for Performance**
   Indexes on sequence numbers, departure times, and stop IDs support common reporting queries.

5. **Clear Data Modeling**
   The schema mirrors the real-world structure of transit operations in a precise, enforceable way.
