-- TTC Delay Analytics Framework — MySQL schema
-- BSMM-8730, Data Acquisition and Management

CREATE DATABASE IF NOT EXISTS ttc_delays;
USE ttc_delays;

-- ---------------------------------------------------------------------
-- date_dim: one row per calendar date, holds date-level temporal flags.
-- Everything else joins to this on date, so "is it a holiday" logic
-- lives in exactly one place instead of being recomputed per table.
-- ---------------------------------------------------------------------
CREATE TABLE date_dim (
    date            DATE PRIMARY KEY,
    day_of_week     VARCHAR(9)  NOT NULL,          -- e.g. 'Monday'
    is_weekend      BOOLEAN     NOT NULL DEFAULT FALSE,
    is_holiday      BOOLEAN     NOT NULL DEFAULT FALSE,
    season          VARCHAR(6)  NOT NULL            -- 'Winter','Spring','Summer','Fall'
);

-- ---------------------------------------------------------------------
-- weather: one row per date (ECCC daily climate data)
-- ---------------------------------------------------------------------
CREATE TABLE weather (
    date              DATE PRIMARY KEY,
    mean_temp_c       DECIMAL(4,1),
    min_temp_c        DECIMAL(4,1),
    max_temp_c        DECIMAL(4,1),
    total_precip_mm   DECIMAL(5,1),
    total_rain_mm     DECIMAL(5,1),
    total_snow_cm     DECIMAL(5,1),
    snow_on_grnd_cm   DECIMAL(5,1),
    FOREIGN KEY (date) REFERENCES date_dim(date)
);

-- ---------------------------------------------------------------------
-- sports_events: one row per home game (Leafs, Raptors, Blue Jays).
-- Toronto FC / MLS was dropped: ESPN's API returned 0 events for it
-- across 2023-2025 (see etl/extract_sports_events.py for details).
-- Multiple games can fall on the same date (different leagues), so this
-- is NOT one-to-one with date_dim — many events can point at one date.
-- ---------------------------------------------------------------------
CREATE TABLE sports_events (
    event_id        INT AUTO_INCREMENT PRIMARY KEY,
    event_date      DATE NOT NULL,
    team            VARCHAR(50) NOT NULL,
    league          VARCHAR(10) NOT NULL,           -- 'NHL','NBA','MLB'
    venue           VARCHAR(50),
    is_home_game    BOOLEAN NOT NULL DEFAULT TRUE,
    FOREIGN KEY (event_date) REFERENCES date_dim(date),
    INDEX idx_event_date (event_date)
);

-- ---------------------------------------------------------------------
-- delays: one row per delay incident, across all three TTC networks.
-- Subway/streetcar/bus source files have slightly different column
-- names (e.g. "Station" vs "Location", "Code" vs "Incident") — this
-- table unifies them so cross-network comparison doesn't need a join.
--
-- Column widths below (incident_code, route_or_line, direction,
-- vehicle_number) and delay_category were widened/added after real
-- TTC data was loaded and didn't fit the original narrower design
-- (e.g. incident codes like "COLLISION - TTC INVOLVED" run 25+ chars).
-- ---------------------------------------------------------------------
CREATE TABLE delays (
    delay_id               INT AUTO_INCREMENT PRIMARY KEY,
    delay_date             DATE NOT NULL,
    delay_time             TIME NOT NULL,
    network                ENUM('subway','streetcar','bus') NOT NULL,
    route_or_line           VARCHAR(50),               -- e.g. 'Line 1', '504'
    location                VARCHAR(100),               -- station or intersection
    incident_code           VARCHAR(100),
    incident_description   VARCHAR(150),
    delay_category           VARCHAR(20),               -- mechanical/weather/operational/crowding
    min_delay               INT,                        -- minutes
    min_gap                 INT,                        -- minutes
    direction                VARCHAR(50),
    vehicle_number           VARCHAR(20),
    is_rush_hour             BOOLEAN NOT NULL DEFAULT FALSE,  -- derived from delay_time
    FOREIGN KEY (delay_date) REFERENCES date_dim(date),
    INDEX idx_delay_date (delay_date),
    INDEX idx_network (network),
    INDEX idx_delay_category (delay_category)
);