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

### Python API
The `radifox` package also includes a Python API for accessing additional components.

#### `ImageFile`
The `ImageFile` class is used to represent a single image file, including its name and metadata.
It is a wrapper around a lot of `pathlib.Path` functions, so it can be used in place of a `Path` object in many cases.
It additionally defines a number of properties to access naming breakdowns and metadata.

Example Usage:
```python
from radifox.ontology.imagefile import ImageFile
img = ImageFile('/path/to/output/study/STUDY-123456/1/nii/STUDY-123456_01-03_BRAIN-T1-IRFSPGR-3D-SAGITTAL-PRE.nii.gz')
print(img.body_part) # prints 'BRAIN'
print(img.modality) # prints 'T1'
print(img.name) # prints 'STUDY-123456_01-03_BRAIN-T1-IRFSPGR-3D-SAGITTAL-PRE.nii.gz'
print(img.info.series_description) # prints 'IRFSPGR 3D SAGITTAL PRE'
```

#### `ImageFilter`
The `ImageFilter` class is used to represent a filter for images based on naming.
It is a wrapper around a `dict` that defines a set of key-value pairs that must be present in the image name.
It can be defined as keyword arguments in the class constructer or by passing a formatted string to `ImageFile.from_string`.

Example Usage:
```python
from radifox.ontology.imagefile import ImageFilter

imgs = [
    ImageFile('/path/to/output/study/STUDY-123456/1/nii/STUDY-123456_01-03_BRAIN-T1-IRFSPGR-3D-SAGITTAL-PRE.nii.gz'),
    ImageFile('/path/to/output/study/STUDY-123456/1/nii/STUDY-123456_01-04_BRAIN-T2-FSE-2D-AXIAL-POST.nii.gz'),
]

filt = ImageFilter(body_part='BRAIN', modality='T1')
print(filt) # prints "body_part=BRAIN,modality=T1"
print(filt.filter(imgs)) # prints ['/path/to/output/study/STUDY-123456/1/nii/STUDY-123456_01-03_BRAIN-T1-IRFSPGR-3D-SAGITTAL-PRE.nii.gz']

filt = ImageFilter.from_string('body_part=BRAIN,modality=T2')
print(filt) # prints "body_part=BRAIN,modality=T2"
print(filt.filter(imgs)) # prints ['/path/to/output/study/STUDY-123456/1/nii/STUDY-123456_01-04_BRAIN-T2-FSE-2D-AXIAL-POST.nii.gz']
```

#### `ProcessingModule`
The `ProcessingModule` class is used to represent a processing module for use in the auto-provenance system.
Module code should inherit from this class and implement the `cli` and `run` methods, as well as define the `name` and `version` class attributes.
The `cli` method should take either a list of options/arguments or None to pull from `sys.argv`.
It should return a `dict` of keywards and arguments to pass directly to the `run` method.
The `run` method should take a `dict` of keywords and arguments and return a `dict` of results.

Example Usage:
```python
import argparse
from pathlib import Path

import nibabel as nib
from radifox.provenance.provenance import ProcessingModule
from radifox.conversion.utils import mkdir_p

class MyModule(ProcessingModule):
    name = "my-module"
    version = "1.0.0"

    @staticmethod
    def cli(args=None):
        parser = argparse.ArgumentParser()
        parser.add_argument("--input", type=Path, required=True)
        parser.add_argument("--mult-factor", type=float, required=True)
        parsed = parser.parse_args(args)
        
        return {
            "input": parsed.input,
            "mult_factor": parsed.mult_factor,
        }

    @staticmethod
    def run(in_file: Path, mult_factor: float):
        out_stem = in_file.name.split(".")[0]
        out_dir = in_file.parent.parent / "proc"
        mkdir_p(out_dir)
        
        
        obj = nib.Nifti1Image.load(in_file)
        data = obj.get_fdata()
        new_obj = nib.Nifti1Image(data * mult_factor, obj.affine, obj.header)
        new_obj.to_filename(out_dir/ f"{out_stem}_mult-{mult_factor}.nii.gz")
        return {
            'output': out_dir / f"{out_stem}_mult-{mult_factor}.nii.gz"
        }
```

A `ProcessingModule` subclass can then be run as `MyModule()` or `MyModule(args)` (where args is as list of strings for `argparse` to parse).
This can be used to make a processing script by adding:
```python
if __name__ == "__main__":
    MyModule()
```
to the end of the file.

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
The RADIFOX naming system is a detailed, type-based naming system for medical images.
It is currently focused on MRI images, but it is expected to extend to other modalities.
There are six main components to the naming system:
 - `bodypart`: The body part being imaged (e.g. BRAIN, CSPINE, etc.)
 - `modality`: The imaging modality (e.g. T1, T2, etc.)
 - `technique`: The imaging technique (e.g. IRFSPGR, FSE, etc.)
 - `acqdim`: The acquisition dimension (2D or 3D)
 - `orientation`: The imaging plane (AXIAL, SAGITTAL, CORONAL)
 - `excontrast`: The exogenous contrast (PRE, POST, etc.)

An image filename is then constructed by combining these components with hyphens.
```
<subject-id>_<session-id>_<image-id>_<bodypart>-<modality>-<technique>-<acqdim>-<orientation>-<excontrast>.nii.gz
```
The `image-id` is a unique identifier for the image within the session, it is created from a study number (in case multiple imaging studies are in the same session) and an image number (in each study).

Additionally, image names can have `extras` appended to the end of the core name.
These are additional descriptors that are not part of the core naming system, but are useful for identifying images.
`extras` are connected to the main name with a hyphen (and multiple extras are separated by hyphens).
Common uses for `extras` are echo numbers (e.g. ECHO1, ECHO2, etc.) in multi-echo sequences and complex image components (like MAG and PHA) in complex images.
However, this can be used for any additional descriptor of the acquired image that may help route it through processing.

For example:
```
STUDY-123456_01-03_BRAIN-T2-FSE-2D-AXIAL-PRE-ECHO1.nii.gz
STUDY-123456_01-03_BRAIN-T2-FSE-2D-AXIAL-PRE-ECHO2.nii.gz
```

Processed images also have tags appended to the end of the name.
This is to indicate the processing steps that were applied to the image.
These tags are separated from the main name with an underscore (and multiple tags are separated by underscores).
In general, new tags are appended to existing tags (so the order of tags is important).
This is to ensure that the processing history of the image is preserved in the filename.

For example:
```
STUDY-123456_01-03_BRAIN-T2-FSE-2D-AXIAL-PRE-ECHO1_n4.nii.gz
```

## Conversion
The conversion system is a wrapper around the `dcm2niix` tool.
It uses the RADIFOX naming system to organize the output files.
`radifox-convert` is the core command for this function.

The conversion process is as follows:
 1. Copy the DICOM files to the `dcm` directory in the session directory.
 2. Sort the DICOM files into series directories in the `dcm` directory and remove any duplicates.
 3. Check for series that should be skipped (scouts, localizers, derived images, etc.).
 4. Generate image names automatically from the DICOM metadata, look-up tables, and manual naming entries.
 5. Convert the DICOM files to NIfTI using `dcm2niix` and rename to RADIFOX naming.
 6. Create the JSON sidecar files for the NIfTI files (contains some DICOM metadata).
 7. Create QA images for the converted NIfTI files.

### Look-up Tables
The look-up tables are a set of rules for automatically naming images based on the DICOM `SeriesDescription` tag.
They are stored in a comma-separated values (CSV) file in each project folder.
They have a specific name format: `<project-id>_lut.csv`.
If no look-up table is found for a project, a blank look-up table is written.
Look-up table values take precidence over automatic naming, but are overwritten by manual names.

The look-up table file has five total columns: `Project`, `Site`, `InstitutionName`, `SeriesDescription`, and `OutputFilename`.

The first three columns (`Project`, `Site`, and `InstitutionName`) narrow down which images are affected.
These columns match the project and site IDs and the DICOM `InstitutionName` tag.
This means that if a particular site or even scanning center uses a specific `SeriesDescription`, it can be handled differently than others.
The `Site` and `InstitutionName` columns are optional and can be `None`.

The `SeriesDescription` column is a string and must **exactly** match the DICOM `SeriesDescription` tag.
This may mean that multiple rows are needed to cover all possible values of the `SeriesDescription` tag for a particular name.

The `OutputFilename` column is where the RADIFOX naming is specified.
You do not have to specify all components of the name, only the ones that need to be changed.
For example, if you only want to change the `bodypart` to `BRAIN` for a specific `SeriesDescription`, you can specify `BRAIN` in the `OutputFilename` column.
However, you must specify all components that come prior to the one you want to change as `None`.
For example, to change the `modality` to `T1` for a specific `SeriesDescription`, you must specify `None-T1` in the `OutputFilename` column.
This can also be used to change the `extras`, by specifying them at the end of the `OutputFilename` column.
For example, to add `ECHO1` to the end of the name for a specific `SeriesDescription`, but change nothing else, you must specify `None-None-None-None-None-None-ECHO1` in the `OutputFilename` column.

### Manual Naming
Manual naming entries are the most specific way to name images.
They are stored as a JSON file in each session directory (`<subject-id>_<session-id>_ManualNaming.json`).
This JSON file is a dictionary with the DICOM series directory path (`dcm/...`) as the key and the new name as the value.
This series path can be found as the `SourcePath` in the sidecar JSON file for the image.
Manual naming entries take precidence over look-up tables and automatic naming.
The naming convention for manual naming entries is the same as for look-up tables.

The simplest way to create manual naming entries is to use the `radifox-qa` webapp.

### JSON Sidecar Files
JSON sidecar files are created for each NIfTI file during conversion.
They contain information about the conversion process (versions, look-up table values, manual naming, etc.) as well as critical DICOM metadata.
The JSON sidecar files are stored in the `nii` directory in eact session directory next to their corresponding NIfTI file.

Sidecar files are human-readable, but can also be accessed in Python using the `json` standard package.
Most of the crutial information will be in the `SeriesInfo` key of the sidecar file.

```python
import json

obj = json.load(open('/path/to/output/study/STUDY-123456/1/nii/STUDY-123456_01-03_BRAIN-T1-IRFSPGR-3D-SAGITTAL-PRE.json'))
print(obj['SeriesInfo']['SeriesDescription']) # prints 'IRFSPGR 3D SAGITTAL PRE'
print(obj('SeriesInfo')['SliceThickness']) # prints 1.0
```

A complete record of the sidecar JSON format is below [JSON Sidecar Format](#json-sidecar-format).

## Provenance
The auto-provenance system is a system for tracking the provenance of processing results.
It allows developers to easily include RADIFOX management features into their processing scripts in a consistent way.
Currently, this is limited to automatic provenance generation, but will likely include automatic logging and QA image generation.

The auto-provenance system is based on the `ProcessingModule` class.
This is an abstract class that defines the basic structure of a processing module.
Developers should inherit from this class and implement the `cli` and `run` methods, as well as define the `name` and `version` class attributes.
See [ProcessingModule](#processingmodule) for more details.

Provenance from this system is stored in two different ways.
The first is at the session level in the `<subject-id>_<session-id>_Provenance.txt` file.
This is an append-only text file that contains the provenance records of all processing steps for the session.
The second is a provenance text file (`.prov`) that is stored with each processed file.
This contains the provenance record for the process that created the processed file only.

Provenance records are stored in a custom format that is human-readable, but will also be parsable by RADIFOX in the future.
The format is as follows:
```
Id: <record-id>
Module: <module-name>:<module-version>
Container: <container-url>:<container-tag> <container-hash>
User: <user-name>
TimeStamp: <timestamp>
Inputs:
  - <input-key-1>: <input-filename-1>:<input-hash-1>
  - <input-key-2>: <input-filename-2>:<input-hash-2>
  - ...
Outputs:
  - <output-key-1>: <output-filename-1>:<output-hash-1>
  - <output-key-2>: <output-filename-2>:<output-hash-2>
  - ...
Parameters:
  - <parameter-key-1>: <parameter-value-1>
  - <parameter-key-2>: <parameter-value-2>
  - ...
Command: <command-string>
```



## Quality Assurance

# Additional Information

## Advanced CLI Usage

## JSON Sidecar Format