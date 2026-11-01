# Spec Delta

## ADDED Requirements

### Requirement: Simplified route per activity
The system SHALL store, for each activity with real GPS positions, a simplified route made of continuous stretches in which no point lies more than 10 metres from the recorded path. It SHALL NOT store a route for virtual rides.

#### Scenario: Route stored at import
- **WHEN** an outdoor activity with GPS is imported
- **THEN** its simplified route is stored with the activity, with far fewer points than the recorded samples

#### Scenario: Gaps split the route
- **WHEN** an activity has no fix for more than 30 seconds, or its position jumps by more than 300 metres
- **THEN** the route is stored as separate stretches, with nothing joining them

#### Scenario: Virtual ride
- **WHEN** a virtual ride whose positions describe a game world is imported
- **THEN** no route is stored for it

#### Scenario: Activity without positions
- **WHEN** an indoor activity with no position data is imported
- **THEN** no route is stored and the import is not reported as a failure

### Requirement: Routes for earlier activities
The system SHALL create the route of an activity imported before routes existed from its stored samples on the next import run, without reading FIT files, and SHALL NOT repeat that work for activities already handled.

#### Scenario: Backfill
- **WHEN** an import run starts and stored activities have samples but no route
- **THEN** their routes are created from the samples and the activities are marked as handled

#### Scenario: Not repeated
- **WHEN** a later import run starts
- **THEN** activities already handled, including those with no usable GPS, are not processed again

#### Scenario: Missing samples
- **WHEN** an activity's samples file cannot be read during the backfill
- **THEN** that activity is skipped without failing the import run
