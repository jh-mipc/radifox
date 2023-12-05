# CHANGELOG

All notable changes to `radifox` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.3] - 2023-12-05

### Added
 - Secured QA webapp with secret key displayed at start
 - Added `radifox-stage` command to stage images for processing
 - Added processing mode to QA webapp

## [1.0.2] - 2023-11-29

### Added
 - Add LICENSE file
 - Filled out CHANGELOG
 - Add README changes from v1.0.1

### Changed
 - Fixed .gitattributes for rename
 - Add `timestamp` and `builder` values to container labels
 - Add GitHub Actions for docker creation and pypi publishing
 - Reformat prov record (new container labels, relative paths, yaml compliance)
 - Harmonize GitLab CI and GitHub Actions workflows
 - Update URL for GitHub move
 - Update Dockerfile to use Debian bookworm fixing a ldconfig bug

## [1.0.1] - 2023-11-16
This is a small correction release after 1.0.0 that makes some convenience changes to the provenance record files.

### Changed
 - Add the system hostname to the `User` field
 - Change `TimeStamp` to `StartTime`
 - Add a `Duration` field
 - Change all timestamps to local time

## [1.0.0] - 2023-11-15
This represents the code that will go into the first major release of RADIFOX (previously autoconv) and includes breaking changes!

### Added
 - Added record keeping (provenance) through abstract base class ProcessingModule
 - Added automatic provenance, logging and QA image generation through ProcessingModule 
 - Added convenience utilities that understand RADIFOX naming conventions 
 - Added internal support for multi-frame enhanced DICOMs to replace emf2sf 
 - Added code to run the QA webapp 
 - Added extensive README 

### Changed
 - Renamed project to RADIFOX to represent all features (not just conversion)
 - Reorganized to multiple subpackages for easier expansion
 - Changed "PatientID" to "SubjectID" and "TimeID" to "SessionID" for more general usage 
 - Use resize from the new radifox-utils in QA image generation 
 - Removed dependency on dcmdjpeg and emf2sf (decompression support removed)
 - Updated dcm2niix version in Dockerfile 
 - Simplified and updated Dockerfile and CI task
 - Used black for code style (line-length:100)
 - Changed CLI option --append to --safe 
 - Removed ProjectShortName and CLI option --project-short-name 
 - Removed Modality and --modality CLI option (changes names mr-dcm to dcm, etc.) and removed accidentally hard-coded MR values 
 - Update hash to use SHA256 across the board (this may be a bit slower on some machines, but simplifies the process)
 - Updated how versions are stored in JSON sidecars (`__version__` key)

## [0.4.2] - 2023-11-02
Two bug fixes to work with Philips data with questionable de-identification.

### Changed
 - Skip images that have a "T2MAP" ImageType (processed image that Philips puts as [Primary, Original])
 - Use ProtocolName instead of SeriesDescription (if SeriesDescription is missing)

## [0.4.1] - 2023-09-18
This is a bug fix release for a number of issues that were found in the automatic naming process.

### Changed
 - Fix spinal cord naming (bad matching on cervical/thoracic)
 - Fix MP2RAGE inversion time (stored as trigger time)
 - Add "pride" to skip list to avoid reconstructed images
 - Fix other naming issues

## [0.4.0] - 2023-04-27
This is a feature version that could introduce breaking changes
We have made the decision to remove the ACQ# from the end of the filename and introduce study_id and series_id values before the body_part designation.
Filenames are now:
```
PROJECTID[-SITEID]-SUBJECTID_SESSIONID_STUDYID-SERIESID_BODYPART-MODALITY-TECHNIQUE-ACQDIM-ORIENTATION-EXCONTRAST
```
This version also includes a number of bug fixes.

### Changed
 - Simplifying body_part parsing using regex against the SeriesDescription, BodyPartExamined, and StudyDescription fields (in that order)
 - Changing numbering of series and studies to give better information about what scans were taken together
 - Introduce a POS# extra for images that are multiple physical locations in the same series
 - Better management of multiple extras that are added in the naming process
 - Other naming related fixes

## [0.3.9] - 2022-09-28
This is a small bugfix update.

### Changed
 - Reverts change to auto-name ORBITS for small axial volumes
 - Stricter rules on SPINE naming (must be SPINE image and no manual naming).

## [0.3.8] - 2022-09-22
This release fixes a number of bugs related to SPINE naming. Versioning is now controlled by miniver.

### Added
 - Versioning is now automatic using miniver.

### Changed
 - Updates to Dockerfile (use HTTPS for dcm2niix)
 - Update versions on dependencies
 - SPINE scans can now be separated by a different scan and still be transformed to CSPINE and TSPINE
 - Axial T1-VIBE scans are now marked as SPINE
 - "Upper"/"Lower" mappings are now moved to the end of name prediction

## [0.3.7] - 2021-12-08
Addresses issues with PARREC resolution calculation, naming and automatic versioning of releases.

### Changed
 - The reconstructed resolution was incorrectly stored as an integer for PARREC scans, changed to float.
 - When SPINE scans are renamed to CSPINE and TSPINE, use "_SPINE-" as a replacement value to avoid replacing "SPINE" strings elsewhere in the name
 - Update naming checks for scans with multiple dynamics (echoes, mag/phase, etc.). This change fixes scans where different names are predicted for the same root UID.
 - Add a check for a Philips specific DICOM tag for inversion time (TI).
 - Change string checks in automatic naming to use re.search.
 - Only change permissions of directories if the permissions are incorrect rather than every time.
 - Default LUT file location should be in the project ID directory unless NoProjectSubdir is true.
 - Fixed gitattributes to allow all tarballs to have automatic versioning.


## [0.3.6] - 2021-03-21
This release fixes a number of issues where ND scans (Siemens) are included in the session, and also includes updates for anonymization and naming.

### Changed
 - Updates naming to allow for ND (no distortion correction images) to be included in final name
 - Updates to MT naming to cover ND images and moves dynamic checking to after ND/MT/SUM/SPINE renaming
 - Consolidation of name alteration code to a single function in BaseInfo. Updates name and does logging
 - Updates anonymization to include StudyUID and SeriesUID which could contain dates and removes SourcePath, which could contain original SeriesUID
 - Updates naming function to allow LUT or manual name to have more than the 6 basic pieces (i.e. MTOFF/MTON)

## [0.3.5] - 2020-03-12
This hotfix release fixes a bug in the MT renaming section of `generate_unique_names()`.
The `find_closest` function now correctly returns the index, not the position of the index in the candidate list.

## [0.3.4] - 2020-03-10
This is a feature release that makes conversion simpler when no LUT is required.

### Added
 - Makes converting simpler when no LUT is required. If the LUT file path specified (or generated) does not exist, a blank LUT file (headers only) is created in that location. This blank file is used for conversion.

## [0.3.3] - 2021-03-09
This is a feature release that adds an experimental anonymization feature to the `convert` routine.

### Added
 - Add an anonymization routine to the `convert` routine (`--anonymize`). This will hash potentially sensitive information in the sidecar files, remove the copied source files and optionally shift the date (using the `--date-shift-days` option).

## [0.3.2] - 2020-11-24
This is a feature release that adds a number of new features and fixes a few bugs.

### Added
 - Allow partial renaming by specifying "None" as a piece of the naming string (or not including it). For example, to provide a lookup value for just the body part portion of the name, you could put "BRAIN" in as the output filename in the lookup table file. This would automatically fill in the remaining portions of the name, but manually mark the body part as BRAIN. This will also work for manual naming JSON files.

### Changed
 - Lookup table convention changes to use "None" as a missing value for Site or InstitutionName. A OutputFilename value of "False" will force autoconv to not convert the image. The same "False" value can be used in manual naming JSON files.
 - Fail more gracefully if there is an error during automatic renaming. As this is the part of the code that most often runs through technical values, this avoids a crash if values are not the proper type or missing.

## [0.3.1] - 2020-08-13
This is a bugfix release that fixes issues with the QA image generation and the archive extraction.

### Changed
 - Fixes issue with checking if a file is an allowed archive format, now just look at the file extension at the end of the file name.
 - Fixes QA image generation where the minimum was added, not subtracted

## [0.3.0] - 2020-08-12
This is a bugfix update that quickly added a number of new features and added new dependencies, so version was increased to 0.3.0.

### New Dependencies
 - scipy
 - Pillow
(Both are used for QA image generation features)

### Added
 - Add `--append` feature to convert allow for non-destructive processing, incrementing numbers will be appended to the session ID to prevent naming conflicts. This is only in the directory naming, so directories can just be renamed, if a later attempt should be used as the primary.
 - Add automatic QA image generation for each converted nifti image
 - More verbose version checking in update, now dev versions (either saved or current) will force an update
 - Check for manual naming changes when running update
 - Add support for dummy scans with no patient ID in the TMS metadata file
 - Add simple log line at beginning and end that specifies the output name

### Changed
 - Keep old logs after a bad update call, since we are moving back all of the old files
 - Only catch derived images with "MPR" in the series description
 - Remove input file path from metadata to avoid any possible PHI
 - Correct Philips IRFSPGR being called FGRE
 - Include "ct spine" as ctspine
 - "ctspine" etc. no longer incorrectly classified as tspine
 - Create a sortable value if InstanceCreationTime is not present
 - Fixed a bug in logic on extraction of imaging date/time
 - Allow missing manufacturer value
 - Skip dicom files on KeyError

## [0.2.4] - 2020-07-24
Add `--hardlink` option to `convert` to allow input files to be hardlinked into the source directory.

## [0.2.3] - 2020-07-21
Adds new CLI feature and improves portability.

### Added
 - Add `--symlink` option to `convert` to allow input files to be symlinked into the source directory.

### Changed
 - Makes datasets more portable by removing absolute paths from info files.

## [0.2.2] - 2020-07-14
Fixes bug when using `-t/-a/-s` as an override for a TMS dataset with metadata file.
Adds STDERR to output for `dcm2niix` if return code is non-zero for easier debugging.

## [0.2.1] - 2020-07-14
Fixes bug when using `convert` with the `--force` option.

## [0.2.0] - 2020-07-09
Feature release with new functionality and bug fixes.

### Added
 - Allow sharing of LUT values for an entire site
 - Hash inputs and outputs for record keeping
 - Store old files during update in case of error
 - Flexible archive extraction using `shutil.extract_archive`
 - Improved type hints
 - Combine files with multiple timings into a 4D file

### Changed
 - Use `pathlib` instead of `os.path`
 - Update parrec sorting (fewer collision chances and skip if already sorted)
 - Improved naming for GE scans
 - Clean up naming in general (specifically reducing the number of "short" matching strings <3 chars)

## [0.1.0] - 2020-06-30
This is the initial release of the `autoconv` package for automatic conversion of MR imaging files.