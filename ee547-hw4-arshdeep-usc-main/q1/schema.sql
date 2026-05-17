-- Metro transit database schema
-- Tables: lines, stops, line_stops, trips, stop_events

-- 1) lines: surrogate primary key, unique natural key (line_name)
CREATE TABLE IF NOT EXISTS lines (
    line_id    SERIAL PRIMARY KEY,
    line_name  VARCHAR(50) NOT NULL UNIQUE,
    vehicle_type VARCHAR(10) NOT NULL CHECK (vehicle_type IN ('rail', 'bus', 'tram', 'ferry', 'other'))
);

-- 2) stops: surrogate primary key, natural unique on stop_name
CREATE TABLE IF NOT EXISTS stops (
    stop_id    SERIAL PRIMARY KEY,
    stop_name  VARCHAR(200) NOT NULL UNIQUE,
    latitude   NUMERIC(9,6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude  NUMERIC(9,6) NOT NULL CHECK (longitude BETWEEN -180 AND 180)
);

-- 3) line_stops: which stops each line serves, in order
CREATE TABLE IF NOT EXISTS line_stops (
    line_stop_id SERIAL PRIMARY KEY,
    line_id      INTEGER NOT NULL REFERENCES lines(line_id) ON DELETE CASCADE,
    stop_id      INTEGER NOT NULL REFERENCES stops(stop_id) ON DELETE CASCADE,
    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
    time_offset_minutes INTEGER NOT NULL CHECK (time_offset_minutes >= 0),
    UNIQUE (line_id, sequence_number),
    UNIQUE (line_id, stop_id)
);

-- 4) trips: scheduled vehicle runs
CREATE TABLE IF NOT EXISTS trips (
    trip_id    VARCHAR(50) PRIMARY KEY,
    line_id    INTEGER NOT NULL REFERENCES lines(line_id) ON DELETE RESTRICT,
    scheduled_departure TIMESTAMP NOT NULL,
    vehicle_id VARCHAR(50)
);

-- 5) stop_events: actual arrivals during trips
CREATE TABLE IF NOT EXISTS stop_events (
    stop_event_id SERIAL PRIMARY KEY,
    trip_id    VARCHAR(50) NOT NULL REFERENCES trips(trip_id) ON DELETE CASCADE,
    stop_id    INTEGER NOT NULL REFERENCES stops(stop_id) ON DELETE RESTRICT,
    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
    scheduled_time TIMESTAMP NOT NULL,
    actual_time    TIMESTAMP,
    passengers_on  INTEGER NOT NULL CHECK (passengers_on >= 0),
    passengers_off INTEGER NOT NULL CHECK (passengers_off >= 0),
    UNIQUE (trip_id, sequence_number),
    UNIQUE (trip_id, stop_id)
);

-- Indexes to support common queries
CREATE INDEX IF NOT EXISTS idx_line_stops_lineid_seq ON line_stops(line_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_trips_line_sched ON trips(line_id, scheduled_departure);
CREATE INDEX IF NOT EXISTS idx_stop_events_trip_seq ON stop_events(trip_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_stop_events_stop ON stop_events(stop_id);
CREATE INDEX IF NOT EXISTS idx_stop_events_sched_actual ON stop_events(scheduled_time, actual_time);