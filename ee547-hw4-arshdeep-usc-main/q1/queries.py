import argparse
import json
import os
import time
import csv
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

DEFAULTS = {
    'host': os.environ.get('DB_HOST', 'db'),
    'port': int(os.environ.get('DB_PORT', 5432)),
    'dbname': os.environ.get('DB_NAME', 'transit'),
    'user': os.environ.get('DB_USER', 'transit'),
    'password': os.environ.get('DB_PASSWORD', 'transit123')
}

QUERIES = {
    "Q1": {
        "description": "Route 20 stops in order",
        "sql": """
SELECT s.stop_name, ls.sequence_number AS sequence, ls.time_offset_minutes AS time_offset
FROM line_stops ls
JOIN lines l ON ls.line_id = l.line_id
JOIN stops s ON ls.stop_id = s.stop_id
WHERE l.line_name = %s
ORDER BY ls.sequence_number;
""",
        "params": ("Route 20",)
    },

    "Q2": {
        "description": "Trips during morning rush (07:00-09:00)",
        "sql": """
SELECT t.trip_id, l.line_name, t.scheduled_departure
FROM trips t
JOIN lines l ON t.line_id = l.line_id
WHERE date_part('hour', t.scheduled_departure) BETWEEN 7 AND 8
ORDER BY t.scheduled_departure;
""",
        "params": ()
    },

    "Q3": {
        "description": "Transfer stops (on 2+ routes)",
        "sql": """
SELECT s.stop_name, COUNT(DISTINCT ls.line_id) AS line_count
FROM line_stops ls
JOIN stops s ON ls.stop_id = s.stop_id
GROUP BY s.stop_name
HAVING COUNT(DISTINCT ls.line_id) >= 2
ORDER BY line_count DESC, s.stop_name;
""",
        "params": ()
    },

    "Q4": {
        "description": "Complete route for trip T0001 (all stops for trip in order)",
        "sql": """
SELECT se.sequence_number, s.stop_name, se.scheduled_time, se.actual_time
FROM stop_events se
JOIN stops s ON se.stop_id = s.stop_id
WHERE se.trip_id = %s
ORDER BY se.sequence_number;
""",
        "params": ("T0001",)
    },

    "Q5": {
        "description": "Routes serving both Wilshire / Veteran and Le Conte / Broxton",
        "sql": """
SELECT l.line_name
FROM lines l
WHERE EXISTS (
    SELECT 1 FROM line_stops ls JOIN stops s ON ls.stop_id = s.stop_id
    WHERE ls.line_id = l.line_id AND s.stop_name = %s
)
AND EXISTS (
    SELECT 1 FROM line_stops ls JOIN stops s ON ls.stop_id = s.stop_id
    WHERE ls.line_id = l.line_id AND s.stop_name = %s
);
""",
        "params": ("Wilshire / Veteran", "Le Conte / Broxton")
    },

    "Q6": {
        "description": "Average ridership by line (avg passengers_on per trip aggregated)",
        "sql": """
SELECT l.line_name,
       AVG(per_trip_boardings) AS avg_passengers
FROM (
    SELECT t.trip_id, t.line_id, SUM(se.passengers_on) AS per_trip_boardings
    FROM stop_events se
    JOIN trips t ON se.trip_id = t.trip_id
    GROUP BY t.trip_id, t.line_id
) x
JOIN lines l ON x.line_id = l.line_id
GROUP BY l.line_name
ORDER BY avg_passengers DESC;
""",
        "params": ()
    },

    "Q7": {
        "description": "Top 10 busiest stops by total activity (on+off)",
        "sql": """
SELECT s.stop_name, SUM(se.passengers_on + se.passengers_off) AS total_activity
FROM stop_events se
JOIN stops s ON se.stop_id = s.stop_id
GROUP BY s.stop_name
ORDER BY total_activity DESC
LIMIT 10;
""",
        "params": ()
    },

    "Q8": {
        "description": "Count delays by line (>2 minutes late)",
        "sql": """
SELECT l.line_name, COUNT(*) AS delay_count
FROM stop_events se
JOIN trips t ON se.trip_id = t.trip_id
JOIN lines l ON t.line_id = l.line_id
WHERE se.actual_time IS NOT NULL
  AND se.actual_time > se.scheduled_time + INTERVAL '2 minutes'
GROUP BY l.line_name
ORDER BY delay_count DESC;
""",
        "params": ()
    },

    "Q9": {
        "description": "Trips with 3+ delayed stops (>2min)",
        "sql": """
SELECT se.trip_id, COUNT(*) AS delayed_stop_count
FROM stop_events se
WHERE se.actual_time IS NOT NULL
  AND se.actual_time > se.scheduled_time + INTERVAL '2 minutes'
GROUP BY se.trip_id
HAVING COUNT(*) >= 3
ORDER BY delayed_stop_count DESC;
""",
        "params": ()
    },

    "Q10": {
        "description": "Stops with above-average ridership (total boardings > avg)",
        "sql": """
WITH totals AS (
  SELECT s.stop_id, s.stop_name, SUM(se.passengers_on) AS total_boardings
  FROM stop_events se
  JOIN stops s ON se.stop_id = s.stop_id
  GROUP BY s.stop_id, s.stop_name
), avgv AS (
  SELECT AVG(total_boardings) AS avg_boardings FROM totals
)
SELECT t.stop_name, t.total_boardings
FROM totals t, avgv
WHERE t.total_boardings > avgv.avg_boardings
ORDER BY t.total_boardings DESC;
""",
        "params": ()
    }
}

def run_query(conn, qname):
    """
    Executes the named query and returns a dict with:
      - query: qname
      - description: text
      - columns: list of column names (in order)
      - results: list of dict rows (RealDictRow -> dict)
      - count: number of rows
      - execution_time_ms: integer ms
    """
    q = QUERIES[qname]
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        start = time.time()
        cur.execute(q['sql'], q['params'])
        rows = cur.fetchall()
        # column names from cursor.description (preserves order)
        colnames = [desc[0] for desc in cur.description] if cur.description else []
        elapsed = (time.time() - start) * 1000.0
        return {
            "query": qname,
            "description": q['description'],
            "columns": colnames,
            "results": [dict(r) for r in rows],
            "count": len(rows),
            "execution_time_ms": int(elapsed)
        }

def _value_to_cell(v):
    """
    Convert DB value to a CSV-safe cell string.
    - None -> empty string
    - basic scalars -> str()
    - complex types (list/dict) -> json.dumps
    - datetimes/decimals etc -> str()
    """
    if v is None:
        return ''
    # JSON-serializable complex types should be dumped
    if isinstance(v, (list, dict)):
        return json.dumps(v, default=str, ensure_ascii=False)
    # Fallback to str for everything else (includes datetimes)
    return str(v)

def write_csv_for_result(res, out_file):
    """
    Write a single query result (res dict returned from run_query) as CSV to out_file.
    out_file should be a file-like object opened for text (e.g. sys.stdout).
    """
    writer = csv.writer(out_file)
    cols = res.get('columns', []) or []
    # If columns are empty but there are rows, infer from first row keys (shouldn't happen often)
    if not cols and res.get('results'):
        cols = list(res['results'][0].keys())

    # Write header row
    writer.writerow(cols)

    # Write data rows
    for row in res.get('results', []):
        row_cells = [_value_to_cell(row.get(c)) for c in cols]
        writer.writerow(row_cells)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('which', choices=list(QUERIES.keys()) + ['all'])
    parser.add_argument('--format', choices=['json', 'text', 'csv'], default='json')
    parser.add_argument('--host', default=DEFAULTS['host'])
    parser.add_argument('--port', type=int, default=DEFAULTS['port'])
    parser.add_argument('--dbname', default=DEFAULTS['dbname'])
    parser.add_argument('--user', default=DEFAULTS['user'])
    parser.add_argument('--password', default=DEFAULTS['password'])
    args = parser.parse_args()

    conn = psycopg2.connect(host=args.host, port=args.port, dbname=args.dbname, user=args.user, password=args.password)
    try:
        if args.which == 'all':
            out = []
            for k in sorted(QUERIES.keys()):
                out.append(run_query(conn, k))

            if args.format == 'json':
                print(json.dumps(out, default=str, indent=2))
            elif args.format == 'text':
                for r in out:
                    print(r)
            elif args.format == 'csv':
                # For 'all' + csv: emit a comment header per query, then the CSV table.
                # Use '#' prefixed line so tools can split; CSV itself doesn't have a native multi-table format.
                for idx, r in enumerate(out):
                    # Comment header with query name and description
                    sys.stdout.write(f"# Query: {r['query']} - {r['description']}\n")
                    write_csv_for_result(r, sys.stdout)
                    # Separate tables with a blank line except after last
                    if idx != len(out) - 1:
                        sys.stdout.write("\n")
        else:
            res = run_query(conn, args.which)
            if args.format == 'json':
                print(json.dumps(res, default=str, indent=2))
            elif args.format == 'text':
                print(res)
            elif args.format == 'csv':
                # Single query CSV: just the CSV table
                write_csv_for_result(res, sys.stdout)
    finally:
        conn.close()

if __name__ == '__main__':
    main()