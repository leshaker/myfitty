# training-load Specification

## Purpose
Quantify each activity's training stress (TSS) and relative effort (a zone-weighted heart-rate score comparable to Strava's) from power or heart rate, using the thresholds in effect on the activity's date.

## Requirements

### Requirement: Power-based TSS
For an activity with power data and an applicable FTP, the system SHALL compute intensity factor IF = NP / FTP and TSS = (duration in hours) × IF² × 100, using moving duration and normalized power.

#### Scenario: One hour at FTP
- **WHEN** an activity lasts 1 hour with NP equal to FTP
- **THEN** TSS is 100 and the method is recorded as `power`

#### Scenario: Two hours at 75% of FTP
- **WHEN** an activity lasts 2 hours with NP = 0.75 × FTP
- **THEN** TSS is 112.5 (within 0.1)

### Requirement: Heart-rate-based TSS fallback
For an activity with heart rate data and an applicable threshold HR but no usable power or FTP, the system SHALL compute hrTSS from time spent in heart rate zones defined as percentages of threshold HR, where each zone contributes a fixed TSS per hour, and SHALL record the method as `hr`.

#### Scenario: Running with HR only
- **WHEN** an activity has heart rate but no power, and threshold HR is configured
- **THEN** TSS is computed from time in zones and the method is `hr`

#### Scenario: One hour at threshold HR
- **WHEN** an activity has one hour steady at threshold HR
- **THEN** hrTSS is within 10% of 100

### Requirement: Method precedence and unscored activities
The system SHALL use power-based TSS when both power and FTP are available, otherwise hrTSS, and otherwise leave the activity unscored with TSS null and a stated reason, except that running activities are always scored by heart rate. Unscored activities SHALL still be listed.

#### Scenario: Power and HR both available
- **WHEN** a non-running activity has power, HR, FTP and threshold HR
- **THEN** the power-based TSS is stored

#### Scenario: Nothing to score with
- **WHEN** an activity has no power, and no heart rate or no threshold HR
- **THEN** TSS is null with reason `no_data` or `no_threshold`, and the activity contributes zero to load charts

### Requirement: Running is scored by heart rate
The system SHALL ignore power data when scoring running activities and SHALL score them from heart rate, because running power is not comparable with a cycling FTP. A running activity with no heart rate or no threshold HR SHALL be unscored.

#### Scenario: Run with power and heart rate
- **WHEN** a running activity has power data and heart rate, and both FTP and threshold HR are configured
- **THEN** its TSS is hrTSS, its method is `hr`, and no FTP is recorded as used

#### Scenario: Run with power only
- **WHEN** a running activity has power but no heart rate
- **THEN** it is unscored with reason `no_data`

#### Scenario: Cycling unaffected
- **WHEN** a cycling activity has power, heart rate and an FTP
- **THEN** its TSS is still power-based

### Requirement: Rescoring on demand
The system SHALL provide a command that recomputes the scores of every stored activity from its stored summary and the thresholds in effect on its date, so that stored scores can be brought in line after the scoring rules change.

#### Scenario: Old scores corrected
- **WHEN** a stored running activity carries a power-based score from before running was scored by heart rate and the rescore command runs
- **THEN** its score becomes the heart-rate-based score and its method becomes `hr`

#### Scenario: Nothing to change
- **WHEN** the rescore command runs and every stored score already matches current rules
- **THEN** no activity is modified

### Requirement: Scores are stored with their inputs
The system SHALL store, with each score, the method and the threshold values used, so any score can be explained.

#### Scenario: Inspect a score
- **WHEN** an activity's details are requested
- **THEN** the response includes TSS, method, and the FTP or threshold HR used

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
