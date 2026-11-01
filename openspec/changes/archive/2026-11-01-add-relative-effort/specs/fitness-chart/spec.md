# Spec Delta

## MODIFIED Requirements

### Requirement: Training status page
The system SHALL provide a single page that shows CTL, ATL and TSB over time, a weekly load bar chart, a weekly relative effort bar chart, a sport selector (all plus each stored sport) and a date range selector, using the computed series.

#### Scenario: Open the page
- **WHEN** the user opens the app URL with activities imported
- **THEN** the PMC chart and both weekly bar charts are displayed for the combined view

#### Scenario: Change sport
- **WHEN** the user selects `running`
- **THEN** all charts update to the running-only series

#### Scenario: Empty database
- **WHEN** no activities have been imported
- **THEN** the page shows an empty state explaining how to set the FIT folder and run an import

## ADDED Requirements

### Requirement: Weekly relative effort
The system SHALL provide the total relative effort per ISO week (Monday start), optionally filtered by sport and date range. Activities without a relative effort SHALL count as zero.

#### Scenario: Weekly relative effort totals
- **WHEN** a week has activities with relative effort 120 and 60, and one without heart rate
- **THEN** that week's relative effort is 180

#### Scenario: Sport filter
- **WHEN** the weekly relative effort is requested for `running`
- **THEN** only running activities contribute

#### Scenario: Weeks without activity
- **WHEN** a week between two active weeks has no activities
- **THEN** it is listed with a relative effort of zero

#### Scenario: Empty database
- **WHEN** no activities have been imported
- **THEN** no weeks are returned
