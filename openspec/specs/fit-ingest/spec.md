# fit-ingest Specification

## Purpose
Import activities from FIT files in a local folder into the app's database, regardless of which device or service produced the file, without creating duplicates.

## Requirements

### Requirement: Import FIT files from a configured folder
The system SHALL scan a configured folder, including subfolders, for `.fit` files and import each one as an activity. The folder SHALL be treated as read-only.

#### Scenario: Initial scan
- **WHEN** the importer runs against a folder containing three valid FIT files
- **THEN** three activities are stored and the run reports three imported

#### Scenario: New file picked up on demand
- **WHEN** a new FIT file has been added to the folder and the user opens the app or triggers an import
- **THEN** the file is imported without a restart

#### Scenario: Unchanged files are skipped
- **WHEN** a scan runs and a file's size and modification time are unchanged since its last import
- **THEN** it is not parsed again

#### Scenario: File still being written
- **WHEN** a file was modified within the last 2 seconds
- **THEN** it is left for the next scan

#### Scenario: Source files untouched
- **WHEN** any import completes
- **THEN** no file in the source folder has been modified, moved or deleted

### Requirement: Deduplicate activities
The system SHALL treat two files as the same activity when they have the same start time and device serial number, and SHALL store only one. When a file has no device serial, the system SHALL fall back to the start time plus a hash of the file contents.

#### Scenario: Same file imported twice
- **WHEN** a file already imported is scanned again
- **THEN** no new activity is created and it is reported as a duplicate

#### Scenario: Same activity under a different filename
- **WHEN** a second file has the same start time and device serial as a stored activity
- **THEN** it is skipped as a duplicate

### Requirement: Record sport from the FIT session
The system SHALL store each activity's sport and sub-sport from the FIT session message, and SHALL store `unknown` when absent.

#### Scenario: Cycling activity
- **WHEN** a file's session has sport `cycling` and sub-sport `road`
- **THEN** the stored activity has sport `cycling` and sub-sport `road`

#### Scenario: Missing sport
- **WHEN** a file has no session sport
- **THEN** the activity is stored with sport `unknown`

### Requirement: Store activity summary metrics
The system SHALL store for each activity: start time, elapsed and moving duration, distance when present, average and maximum heart rate and power when present, normalized power when power is present, and seconds spent at each heart rate when heart rate is present.

#### Scenario: Power and heart rate present
- **WHEN** an activity has both power and heart rate records
- **THEN** normalized power, average and maximum power, maximum heart rate and the per-bpm time histogram are stored

#### Scenario: Database from an earlier version
- **WHEN** the application opens a database whose activities lack a stored maximum power and their samples are available
- **THEN** the maximum power is added and filled in from the samples on the next scan, without re-importing

#### Scenario: No sensors
- **WHEN** an activity has neither power nor heart rate
- **THEN** it is stored with duration only and those metrics are null

### Requirement: Store per-second samples
The system SHALL store each activity's samples, resampled to one per second, in columnar files outside the main database, containing time, heart rate, power, speed, altitude and position when present. Indoor activities SHALL have no position values.

#### Scenario: Samples available after import
- **WHEN** an activity is imported
- **THEN** its samples can be queried by activity, with one row per second of recorded time

#### Scenario: Re-import does not duplicate samples
- **WHEN** the same file is scanned again
- **THEN** no additional sample data is stored

#### Scenario: Interrupted import
- **WHEN** an import is interrupted after samples are written but before the activity is recorded
- **THEN** the next scan imports the file normally and leaves exactly one set of samples

### Requirement: Concurrent imports
The system SHALL run overlapping import requests one after another, so that an activity imported by one request is never recorded as failed by another, and no request ends in an error.

#### Scenario: Two sessions import at the same time
- **WHEN** two sessions start an import of the same new files at the same moment
- **THEN** every file is imported exactly once, no failure is recorded, and neither session reports an error

#### Scenario: Same activity committed by another importer first
- **WHEN** another importer stores the same activity between this importer's duplicate check and its insert
- **THEN** the file is reported as a duplicate, not as a failure

### Requirement: Tolerate bad files
The system SHALL NOT abort an import run because one file is corrupt, truncated or unsupported. It SHALL skip that file, record the reason, and continue.

#### Scenario: Corrupt file in a batch
- **WHEN** one of ten files cannot be parsed
- **THEN** nine activities are imported and the failure with its filename and reason is listed in the run result

#### Scenario: Non-activity FIT file
- **WHEN** a FIT file contains no session message (for example a settings or monitoring file)
- **THEN** it is skipped with a "not an activity" reason

#### Scenario: Failed file is retried after being fixed
- **WHEN** a previously failed file is replaced with a valid one
- **THEN** the next scan imports it

### Requirement: Array-valued record fields
The system SHALL import activities whose records hold several samples in one field, as some devices write for speed and altitude, using the most recent sample of each record, and SHALL NOT fail the file because a field has more than one value.

#### Scenario: Several samples per record
- **WHEN** a file's records carry three speed values and three altitude values each
- **THEN** the activity is imported with one sample per second, using the last value of each

### Requirement: Retry failed files on request
The system SHALL provide an import option that re-reads files which failed earlier and are unchanged, while files already imported are not read again. Without the option, unchanged failed files stay skipped.

#### Scenario: Retry after fixing the cause
- **WHEN** a file failed because of a fixed defect, is unchanged, and an import runs with the retry option
- **THEN** the file is read again and imported, and its failure record is cleared

#### Scenario: Retry only when asked
- **WHEN** an import runs without the retry option and an unchanged file had failed before
- **THEN** the file is skipped as unchanged

#### Scenario: Imported files are not re-read
- **WHEN** an import runs with the retry option
- **THEN** files that were imported or skipped as duplicates are not read again
