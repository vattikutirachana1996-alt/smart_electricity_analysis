-- Smart Electricity Analytics: MySQL 8.0+ schema (window functions require 8.0+)
CREATE DATABASE IF NOT EXISTS electricity_analytics
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE electricity_analytics;

-- One row per imported file / official publication
CREATE TABLE IF NOT EXISTS data_sources (
  source_id        INT AUTO_INCREMENT PRIMARY KEY,
  dataset_name     VARCHAR(255) NOT NULL,
  source_url       VARCHAR(500) NOT NULL,
  publisher        VARCHAR(255) NOT NULL DEFAULT 'Central Electricity Authority (CEA), Ministry of Power, Govt. of India',
  period_start     DATE NULL,
  period_end       DATE NULL,
  download_date    DATE NULL,
  energy_unit      VARCHAR(10) NOT NULL DEFAULT 'MU',
  power_unit       VARCHAR(10) NOT NULL DEFAULT 'MW',
  frequency        VARCHAR(30) NOT NULL DEFAULT 'Monthly',
  coverage         VARCHAR(255) NULL,
  limitations      TEXT NULL,
  file_name        VARCHAR(255) NULL,
  imported_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS regions (
  region_id    INT AUTO_INCREMENT PRIMARY KEY,
  region_name  VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS states (
  state_id    INT AUTO_INCREMENT PRIMARY KEY,
  state_name  VARCHAR(100) NOT NULL UNIQUE,
  region_id   INT NULL,
  CONSTRAINT fk_states_region FOREIGN KEY (region_id) REFERENCES regions(region_id)
) ENGINE=InnoDB;

-- Monthly state-level power supply position (energy in MU, power in MW).
-- Energy and power columns stay separate: they are different physical quantities.
CREATE TABLE IF NOT EXISTS power_supply_monthly (
  record_id               BIGINT AUTO_INCREMENT PRIMARY KEY,
  state_id                INT NOT NULL,
  period_month            DATE NOT NULL COMMENT 'first day of the month',
  energy_requirement_mu   DECIMAL(14,4) NULL,
  energy_availability_mu  DECIMAL(14,4) NULL,
  peak_demand_mw          DECIMAL(12,2) NULL,
  peak_met_mw             DECIMAL(12,2) NULL,
  source_id               INT NOT NULL,
  CONSTRAINT fk_ps_state  FOREIGN KEY (state_id)  REFERENCES states(state_id),
  CONSTRAINT fk_ps_source FOREIGN KEY (source_id) REFERENCES data_sources(source_id),
  CONSTRAINT uq_state_month UNIQUE (state_id, period_month),
  CONSTRAINT ck_nonneg CHECK (
    (energy_requirement_mu  IS NULL OR energy_requirement_mu  >= 0) AND
    (energy_availability_mu IS NULL OR energy_availability_mu >= 0) AND
    (peak_demand_mw IS NULL OR peak_demand_mw >= 0) AND
    (peak_met_mw    IS NULL OR peak_met_mw    >= 0)),
  CONSTRAINT ck_first_of_month CHECK (DAY(period_month) = 1),
  INDEX idx_period (period_month),
  INDEX idx_source (source_id)
) ENGINE=InnoDB;
