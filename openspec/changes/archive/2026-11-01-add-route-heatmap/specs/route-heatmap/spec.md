# Spec Delta

## Purpose

Show where the owner's outdoor activities have actually happened on a map, grouped by sport and limited by date, in the style of Strava's personal heatmaps.

## ADDED Requirements

### Requirement: Heatmap view
The system SHALL provide a Heatmap view on the page that shows the routes of outdoor activities on a map for the selected sport and date range.

#### Scenario: Open the heatmap
- **WHEN** the user opens the Heatmap view with outdoor activities in the selected range
- **THEN** a map is shown with the routes of those activities

#### Scenario: Change sport
- **WHEN** the user selects `running`
- **THEN** only running routes are shown

#### Scenario: Change date range
- **WHEN** the user narrows the date range to one month
- **THEN** only routes of activities starting in that month are shown

### Requirement: Routes view
In the Routes view the system SHALL draw each route as a thin translucent line, so that stretches covered by several activities appear stronger, and SHALL colour routes by sport when all sports are shown.

#### Scenario: Overlapping routes appear stronger
- **WHEN** two activities follow the same road for a stretch
- **THEN** that stretch is drawn more strongly than a stretch covered once

#### Scenario: All sports
- **WHEN** the sport selector is on all sports
- **THEN** cycling, running, hiking and walking routes use different colours and a legend names them

#### Scenario: One sport
- **WHEN** a single sport is selected
- **THEN** all routes use that sport's colour

### Requirement: Density view
In the Density view the system SHALL show a smoothed heat layer in which each activity contributes in proportion to distance covered, not to time spent or points recorded.

#### Scenario: Slow and fast stretches weigh the same
- **WHEN** one activity climbs a road slowly and another descends it fast
- **THEN** that road contributes equally to the heat layer from each

#### Scenario: Switching views keeps the selection
- **WHEN** the user switches between Routes and Density
- **THEN** the sport, date range and map position stay the same

### Requirement: Activities without real GPS are left off the map
The system SHALL show only activities with real position data and SHALL leave off indoor and treadmill activities, activities without positions, and virtual rides, whose coordinates describe a game world.

#### Scenario: Virtual ride
- **WHEN** an activity is a virtual ride whose positions are in a game world
- **THEN** it does not appear on the map, and it still counts in the training load charts

#### Scenario: Indoor activity
- **WHEN** an activity has no position data
- **THEN** it does not appear on the map, and it still counts in the training load charts

### Requirement: No line across a GPS gap
The system SHALL NOT draw a line across a stretch with no GPS fix: a route is split where there is no fix for more than 30 seconds or where the position jumps by more than 300 metres.

#### Scenario: Signal lost in a tunnel
- **WHEN** an activity has no fix for 90 seconds in the middle of a ride
- **THEN** the route is drawn as two separate lines with nothing between them

#### Scenario: Recording paused
- **WHEN** recording is paused for several minutes at one place
- **THEN** no line connects the points before and after the pause

### Requirement: Map fits the routes
The system SHALL centre and zoom the map to contain all routes in the selection when the view opens and whenever the sport or date range changes.

#### Scenario: Routes in one region
- **WHEN** all routes in the selection lie around one city
- **THEN** the map is zoomed to that city

#### Scenario: Selection changes region
- **WHEN** the date range changes from a period of local rides to a week abroad
- **THEN** the map moves to show the routes abroad

### Requirement: Basemap can be hidden
The system SHALL let the user switch the basemap off, in which case routes are drawn on a plain background and no map tiles are requested.

#### Scenario: Basemap off
- **WHEN** the user switches the basemap off
- **THEN** routes are shown on a plain background without map tiles

### Requirement: Empty selection
When no activity in the selection has a route, the system SHALL say so and explain that only outdoor activities with GPS are shown and that the filters can be widened.

#### Scenario: Indoor-only period
- **WHEN** the selected range contains only indoor and virtual activities
- **THEN** the Heatmap view shows a message that no routes were found, and the map is not drawn

#### Scenario: Empty database
- **WHEN** no activities have been imported
- **THEN** the Heatmap view shows the same empty-state guidance as the rest of the page

### Requirement: Responsive on the full history
The system SHALL show the heatmap for the owner's full history, about 600 activities, within 3 seconds of changing a filter, once the routes are stored.

#### Scenario: Full history
- **WHEN** the filters cover all activities
- **THEN** the map is ready within 3 seconds and the data sent to the browser is under 5 MB
