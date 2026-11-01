# Spec Delta

## Purpose

Show how fitness, fatigue and form evolve over time, and how much load was done each week, from the stored activity scores.

## ADDED Requirements

### Requirement: Daily fitness, fatigue and form
The system SHALL compute for each calendar day the daily total TSS, fitness (CTL) as the exponentially weighted average of daily TSS with a 42-day time constant, fatigue (ATL) the same with a 7-day constant, and form (TSB) as CTL − ATL. Days without activities SHALL count as zero TSS, and the series SHALL start at zero on the day before the first activity.

#### Scenario: Single day of load
- **WHEN** the only activity is 100 TSS on day 1
- **THEN** on day 1 CTL is 100/42 and ATL is 100/7 (within 0.01), and TSB is CTL − ATL

#### Scenario: Rest days decay
- **WHEN** no activity occurs for 14 days after a block of training
- **THEN** ATL falls faster than CTL and TSB rises

#### Scenario: Multiple activities on a day
- **WHEN** a day has two activities of 50 and 30 TSS
- **THEN** that day's TSS is 80

### Requirement: Series extends to today
The series SHALL run from the first activity through the current local date, so a recent rest period is visible.

#### Scenario: No recent activity
- **WHEN** the last activity was 10 days ago
- **THEN** the series includes those 10 days with zero daily TSS and decaying CTL/ATL

### Requirement: Sport filter
The system SHALL accept an optional sport filter. With a filter, the series SHALL be computed from only that sport's activities; without it, from all activities combined.

#### Scenario: Filter to running
- **WHEN** the series is requested with sport `running`
- **THEN** cycling activities contribute nothing to daily TSS, CTL or ATL

#### Scenario: Combined view
- **WHEN** the series is requested with no sport
- **THEN** all sports' TSS are summed per day

### Requirement: Date range
The system SHALL accept optional start and end dates and return only that range, while computing CTL and ATL from the full history so values do not depend on the range chosen.

#### Scenario: Windowed request
- **WHEN** the series is requested for the last 90 days
- **THEN** CTL for each returned day equals the value from the full-history series

### Requirement: Weekly load
The system SHALL provide total TSS per ISO week (Monday start), optionally filtered by sport.

#### Scenario: Weekly totals
- **WHEN** a week has activities of 60, 80 and 40 TSS
- **THEN** that week's load is 180

### Requirement: Weekly relative effort
The system SHALL provide the total relative effort per ISO week (Monday start), optionally filtered by sport and date range. Activities without a relative effort count as zero.

#### Scenario: Weekly relative effort totals
- **WHEN** a week has activities with relative effort 120 and 60, and one without heart rate
- **THEN** that week's relative effort is 180

#### Scenario: Sport filter
- **WHEN** the weekly relative effort is requested for `running`
- **THEN** only running activities contribute

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
