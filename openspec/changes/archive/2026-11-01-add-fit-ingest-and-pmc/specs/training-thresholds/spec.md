# Spec Delta

## Purpose

Keep FTP, threshold heart rate and max heart rate as a dated history, so each activity is scored with the thresholds that applied when it happened.

## ADDED Requirements

### Requirement: Effective-dated thresholds
The system SHALL store FTP (watts), threshold heart rate (bpm) and max heart rate (bpm) as entries that each have an effective-from date. Each metric SHALL have its own history.

#### Scenario: Add a new FTP
- **WHEN** the user adds FTP 260 W effective 2026-06-01 and an earlier entry of 240 W effective 2026-01-01 exists
- **THEN** both entries are kept and listed in date order

#### Scenario: Replace an entry on the same date
- **WHEN** the user adds a value for a metric on a date that already has an entry
- **THEN** the existing entry for that date is replaced

### Requirement: Threshold lookup by activity date
The system SHALL select, for an activity, the most recent entry of each metric whose effective-from date is on or before the activity's local start date. If none exists, the earliest entry SHALL be used, and if there are no entries the metric is unavailable.

#### Scenario: Activity between two entries
- **WHEN** FTP entries are 240 W from 2026-01-01 and 260 W from 2026-06-01, and an activity occurred on 2026-03-15
- **THEN** 240 W is used

#### Scenario: Activity before the first entry
- **WHEN** the earliest FTP entry is effective 2026-01-01 and an activity occurred on 2025-11-01
- **THEN** that earliest entry is used

#### Scenario: No threshold configured
- **WHEN** no FTP entry exists
- **THEN** power-based TSS is unavailable for every activity

### Requirement: Past scores are stable across new entries
Adding a threshold entry SHALL NOT change the stored scores of activities dated before its effective-from date.

#### Scenario: New FTP does not rescore history
- **WHEN** FTP 260 W is added effective 2026-06-01
- **THEN** TSS of activities before 2026-06-01 is unchanged

### Requirement: Rescoring after edits to history
When a threshold entry is edited or deleted, the system SHALL recompute scores for the activities whose applicable thresholds changed, and only those.

#### Scenario: Correcting an old entry
- **WHEN** the user changes the 240 W entry effective 2026-01-01 to 250 W
- **THEN** activities from 2026-01-01 up to the next FTP entry are rescored, and later ones are not

### Requirement: Threshold validation
The system SHALL reject threshold values that are not positive numbers, and a threshold HR greater than the max HR effective on the same date.

#### Scenario: Invalid value
- **WHEN** the user submits an FTP of 0 or a negative number
- **THEN** the request is rejected with a validation error and nothing is stored

### Requirement: Thresholds from a config file
The system SHALL read an optional config file at startup and add the threshold entries it lists that are not already stored for the same metric and date. It SHALL NOT overwrite or remove stored entries, and SHALL rescore the activities those new entries affect.

#### Scenario: Seeding an empty database
- **WHEN** the config lists four FTP entries and none are stored
- **THEN** all four are stored and existing activities are rescored with them

#### Scenario: UI edits win
- **WHEN** a stored FTP entry for a date differs from the config's value for that date
- **THEN** the stored value is kept

#### Scenario: Startup is idempotent
- **WHEN** the application starts twice with the same config
- **THEN** the second start adds nothing and rescored values are unchanged

#### Scenario: Invalid config
- **WHEN** the config has an unknown metric, a non-positive value, or an unparseable date
- **THEN** startup reports which entry is invalid and does not change stored thresholds

