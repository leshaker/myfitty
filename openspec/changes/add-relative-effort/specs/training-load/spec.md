# Spec Delta

## REMOVED Requirements

### Requirement: Relative effort (TRIMP)
**Reason**: The Edwards TRIMP weights (1 to 5 on fixed percentages of max HR) score easy long efforts about 4 to 5 times higher than Strava's Relative Effort and vary 5-fold in ratio between activities. It is replaced by a zone-weighted relative effort calibrated to Strava's numbers.
**Migration**: Use the "Relative effort" requirement below. Stored TRIMP values are kept under the new column name when a database is upgraded and are recomputed by the rescore command.

## ADDED Requirements

### Requirement: Relative effort
For an activity with heart rate data and heart rate zones, the system SHALL compute relative effort as the sum over five zones of minutes in the zone times a per-minute weight that never decreases from zone 1 to zone 5. The weights SHALL be calibrated so the score is comparable in size to Strava's Relative Effort.

#### Scenario: Higher zones count more per minute
- **WHEN** one activity has 10 minutes in zone 1, another 10 minutes in zone 3, and a third 10 minutes in zone 5
- **THEN** their scores increase from the first to the third, and zone 1 never scores more per minute than zone 2

#### Scenario: Time raises the score
- **WHEN** two activities have the same heart rate but one lasts twice as long
- **THEN** the longer one scores exactly twice as much

#### Scenario: No heart rate or no zones
- **WHEN** an activity has no heart rate data, or no zones can be determined for it
- **THEN** relative effort is null

#### Scenario: Close to Strava for rides and runs
- **WHEN** the score is compared with Strava's Relative Effort over the owner's rides and runs
- **THEN** the median ratio is within 10% of 1 and the correlation is at least 0.9

### Requirement: Heart rate zone edges
The system SHALL define the five zones by four ascending bpm edges. A heart rate equal to an edge belongs to the higher zone. The edges SHALL come from configuration when set, otherwise from fixed fractions of the max HR in effect on the activity's date.

#### Scenario: Configured edges
- **WHEN** edges of 114, 146, 153 and 163 bpm are configured
- **THEN** time at 150 bpm is in zone 3, whatever the max HR

#### Scenario: Heart rate on an edge
- **WHEN** an activity has time at exactly 146 bpm with those edges
- **THEN** that time is in zone 3, and time at 145 bpm is in zone 2

#### Scenario: Edges derived from max HR
- **WHEN** no edges are configured and a max HR is in effect
- **THEN** the edges are fixed fractions of that max HR, and the max HR used is recorded with the score

#### Scenario: Neither edges nor max HR
- **WHEN** no edges are configured and no max HR is available
- **THEN** relative effort is null

### Requirement: Zone edge configuration is validated
The system SHALL reject configured zone edges that are not exactly four positive numbers in strictly ascending order, report the problem at startup, and leave stored data unchanged.

#### Scenario: Valid edges
- **WHEN** the configuration lists edges 114, 146, 153 and 163
- **THEN** they are accepted

#### Scenario: Wrong number of edges
- **WHEN** the configuration lists three edges
- **THEN** startup reports that four ascending edges are required

#### Scenario: Not ascending or not positive
- **WHEN** the configuration lists edges 114, 146, 153 and 150, or an edge of 0
- **THEN** startup reports the invalid edges and stored data is unchanged

### Requirement: Relative effort storage and upgrade
The system SHALL store each activity's relative effort with its other scores. A database created before relative effort replaced TRIMP SHALL be upgraded on opening, keeping its rows, and its values SHALL be recomputed by the rescore command without reading FIT files.

#### Scenario: Database from an earlier version
- **WHEN** the application opens a database that stores the earlier TRIMP value
- **THEN** the data is kept under the relative effort name and no activity is lost

#### Scenario: Rescore after changing zones
- **WHEN** the configured zone edges change and the rescore command runs
- **THEN** every activity's relative effort is recomputed from its stored heart rate summary
