![RADIFOX](header.svg)
RADIFOX is an organization and management system for medical images.
There are multiple components under the RADIFOX umbrella:
 - A detailed, type-based naming system for medical images (including a Python API)
 - An organizational system flexible enough for a multitude of study designs
 - A conversion system to convert from DICOM to NIfTI using DCM2NIIX
 - A auto-provenance system to track the provenance of processing results
 - A web-based quality assurance system

## Installation
RADIFOX is available on PyPI and can be installed with pip:
```bash
pip install radifox
```
This base install will cover the core functionality of RADIFOX.
However, to run conversions, you will need the [dcm2niix](https://github.com/rordenlab/dcm2niix) tool installed on your system (and included in your PATH).

To include the dependencies for the web-based quality assurance system, install with the `qa` extra:
```bash
pip install radifox[qa]
```

## Basic Usage
### CLI Scripts
The `radifox` package includes a number of CLI scripts to access various components of RADIFOX.
These scripts are installed to your PATH when you install the `radifox` package.
For a full listing of command line options, see [Advanced CLI Usage](#advanced-cli-usage).

#### `radifox-convert`
The `radifox-convert` script is used to convert DICOM files to NIfTI files using the `dcm2niix` tool.
It is a wrapper around `dcm2niix` that uses the RADIFOX naming system to organize the output files.

Example Usage:
```bash
radifox-convert \
    --output-root /path/to/output \
    --project-id study \
    --subject-id 123456 \
    --session-id 1 \
    /path/to/dicom_files
```
This will copy the files in the direction `/path/to/dicom_files` to the output directory `/path/to/output/study/123456/STUDY-1/dcm`, organize them and convert them to NIfTI.
The NIfTI files (and their JSON sidecar files) will be placed in `/path/to/output/study/STUDY-123456/1/nii`.

#### `radifox-update`
The `radifox-update` script is used to update naming for a directory of images.
This is commonly done after an update to RADIFOX to ensure that all images are named according to the latest version of the naming system.
It also could be done to incorporate a new look-up table or manual naming entries after QA.

Example Usage:
```bash
radifox-update --directory /path/to/output/study/STUDY-123456/1
```
This will update the naming for all images in the existing RADIFOX session directory `/path/to/output/study/STUDY-123456/1`.
If the RADIFOX version, look-up table, or manual naming entries have changed, the images will be renamed to reflect the new information.
If none of these have changed, the update will be skipped.

#### `radifox-qa`
The `radifox-qa` script is used to run the web-based quality assurance system.

Example Usage:
```bash
radifox-qa --port 8888 --root-directory /path/to/output
```
This will launch the QA webapp on port 8888, pointing to `/path/to/output`.
The QA webapp will be accessible at `http://localhost:8888` and will show projects in `/path/to/output`.

# RADIFOX Components
RADIFOX is a collection of components that work together to provide a comprehensive system for managing medical images.

## File Organization
The file organization structure is multi-level allowing for multiple projects to be stored together while being easily separated.
The directory structure is as follows:
```
<root-directory>
└── <project-id>
    └── <subject-id>
        └── <session-id>
```

This is easily extensible to include multiple sessions per subject, multiple subjects per project, and multiple projects per root directory.
The `project-id`, `subject-id`, and `session-id` are all user-defined and can be any string.

For example:
```
/path/to/output
└── study
    └── STUDY-123456
        └── 1
        └── 2
    └── STUDY-789012
        └── 1
        └── 2
```
Note: The `subject-id` is prefixed with the `project-id` to ensure that the `subject-id` is unique across projects.

Within each session directory, there are a number of subdirectories that are the same for every session:
```
...
└── <session-id>
    └── dcm
    └── nii
    └── logs
    └── qa
```
The `dcm` directory is where the original DICOM files are stored.
The `nii` directory is where the converted NIfTI files (and JSON sidecars) are stored.
The `logs` directory is where the logs from processing are stored.
The `qa` directory is where the images for QA are stored.

In addition to these directories, there are a few files that stored in the session directory.
The `<subject-id>_<session-id>_UnconvertedInfo.json` file is a JSON file that contains information from DICOM files that were skipped during conversion.
The `<subject-id>_<session-id>_ManualNaming.json` file is a JSON file that contains manual naming entries for images in the session.
The `<subject-id>_<session-id>_Provenance.txt` file is a text file that contains the provenance of the processing steps for the session.
 
After processing starts, a few other directories will be added to the session directory:
```
...
└── <session-id>
    └── proc
    └── stage
    └── tmp
```
The `proc` directory is where the processed images and fiels are stored.
The `stage` directory is where the filtered images are placed prior to processing.
The `tmp` directory is where intermediate files are stored during processing.

## Naming


## Conversion

## Provenance

## Quality Assurance

# Additional Information

## Advanced CLI Usage