# Spec Delta

## ADDED Requirements

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
