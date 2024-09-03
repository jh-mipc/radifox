![RADIFOX](header.svg)
RADIFOX is an organization and management system for medical images.
There are multiple components under the RADIFOX umbrella:
 - A detailed, type-based naming system for medical images (including a Python API)
 - An organizational system flexible enough for a multitude of study designs
 - An auto-provenance system to track the provenance of processing results
 - An auto-qa system to generate QA images from processing results

Additionally, other tools are developed on top of the radifox system:
 - A conversion system to convert from DICOM to NIfTI using DCM2NIIX
 - A web-based quality assurance system

RADIFOX is designed to be flexible and extensible.


**Note:** Looking for conversion scripts? They have been moved to the [radifox-convert](https://github.com/jh-mipc/radifox-convert) repository.
The QA webapp has also moved to [radifox-qa](https://github.com/jh-mipc/radifox-qa).

## Table of Contents
- [Overview](#overview)
- [Installation](#installation)
- [Basic Usage](#basic-usage)
  - [CLI Scripts](#cli-scripts)
    - [`radifox-stage`](#radifox-stage)
  - [Python API](#python-api)
    - [`ImageFile`](#imagefile)
    - [`ImageFilter`](#imagefilter)
    - [`ProcessingModule`](#processingmodule)
- [RADIFOX Components](#radifox-components)
  - [File Organization](#file-organization)
  - [Naming](#naming)
  - [Provenance](#provenance)
- [Additional Information](#additional-information)
    - [Advanced CLI Usage](#advanced-cli-usage)
        - [`radifox-stage`](#radifox-stage-1)
    - [Container Creation](#container-creation)

## Overview
The core of the RADIFOX system is the naming and organization system.
This system is designed to be flexible, but also can be opinionated.
The directory organization can be simplified to:
```
<output-root>/<project-id>/<subject-id>/<session-id>/...
```

The naming system is a detailed, type-based naming system optimized for medical images.
It can be simplified to:
```
<subject-id>_<session-id>_<image-id>_<image-type>.ext
```
The image type can be futher broken down into a number of components:
```
<bodypart>-<modality>-<technique>-<acqdim>-<orientation>-<excontrast>[-<extras>]
```

This organzation allows for the implementation of features such as auto-provenance.

## Installation
RADIFOX is available on PyPI and can be installed with pip:
```bash
pip install radifox
```
This base install will cover the core functionality of RADIFOX.
However, to run conversions, you will need the [dcm2niix](https://github.com/rordenlab/dcm2niix) tool installed on your system (and included in your PATH).

## Basic Usage
### CLI Scripts
The `radifox` package includes a number of CLI scripts to access various components of RADIFOX.
These scripts are installed to your PATH when you install the `radifox` package.
For a full listing of command line options, see [Advanced CLI Usage](#advanced-cli-usage).

#### 'radifox-stage'
"Staging" is the process of filtering images for processing.
`radifox-stage` is a processing module that is uses ImageFilters to accomplish this.
`radifox-stage` looks over an entire subject and filters images based on provided `--image-types`.
By default, all images matching the filter will be staged for processing.
To keep only the best resolution images for each filter, use the `--keep-best-res` option.
Additionally, it can generate registration targets based on provided `--reg-filters`.
Plugins derived from the `StagingPlugin` abstract class can be used to add additional functionality to `radifox-stage`.
Two default plugins `MEMPRAGEPlugin` and `MP2RAGEPlugin` are included with RADIFOX.
These can be skipped by providing the `--skip-default-plugins` option.
Staged results have the sform and qform matrices set to be equal by default.
To skip this, use the `--skip-set-sform` option.

A good default call of `radifox-stage` might be:
```bash
radifox-stage \
    --keep-best-res \
    --subject-dir /path/to/output/study/STUDY-123456 \
    --image-types \
        'bodypart=BRAIN;modality=T1;excontrast=PRE' \
        'bodypart=BRAIN;modality=T1;excontrast=POST' \
        'bodypart=BRAIN;modality=T2' \
        'bodypart=BRAIN;modality=PD' \
        'bodypart=BRAIN;modality=FLAIR' \
    --reg-filters \
        'bodypart=BRAIN;modality=T1;acqdim=3D;excontrast=PRE' \
        'bodypart=BRAIN;modality=T1;acqdim=3D;excontrast=POST' \
        'bodypart=BRAIN;acqdim=3D' \
        'bodypart=BRAIN;acqdim=2D'
```

### Python API
The `radifox` package also includes a Python API for accessing additional components.

#### `ImageFile`
The `ImageFile` class is used to represent a single image file, including its name and metadata.
It is a wrapper around a lot of `pathlib.Path` functions, so it can be used in place of a `Path` object in many cases.
It additionally defines a number of properties to access naming breakdowns and metadata.

Example Usage:
```python
from radifox.naming import ImageFile
img = ImageFile('/path/to/output/study/STUDY-123456/1/nii/STUDY-123456_01-03_BRAIN-T1-IRFSPGR-3D-SAGITTAL-PRE.nii.gz')
print(img.bodypart) # prints 'BRAIN'
print(img.modality) # prints 'T1'
print(img.parent) # prints Path object for '/path/to/output/study/STUDY-123456/1/nii'
print(img.name) # prints 'STUDY-123456_01-03_BRAIN-T1-IRFSPGR-3D-SAGITTAL-PRE.nii.gz'
print(img.info.series_description) # prints 'IRFSPGR 3D SAGITTAL PRE'
```

Multiple `pathlib.Path` functions are available directly (like `Path.name`) and others are available through the `path` property (like `Path.iterdir`).
These functions will return `Path` objects, not `ImageFile` objects.
```python
print(img.path) # prints Path object for '/path/to/output/study/STUDY-123456/1/nii/STUDY-123456_01-03_BRAIN-T1-IRFSPGR-3D-SAGITTAL-PRE.nii.gz'
```

#### `ImageFilter`
The `ImageFilter` class is used to represent a filter for images based on naming.
It is a wrapper around a `dict` that defines a set of key-value pairs that must be present in the image name.
It can be defined as keyword arguments in the class constructer or by passing a formatted string to `ImageFile.from_string`.

Example Usage:
```python
from radifox.naming import ImageFilter, ImageFile

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
import logging
from pathlib import Path

import nibabel as nib
from radifox.records import ProcessingModule

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
        out_dir.mkdir(exist_ok=True, parents=True)
        
        logging.info(f"Multiplying {in_file} by {mult_factor}.")
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


#### `StagingPlugin`
The `StagingPlugin` class is used to represent a plugin for use in the `radifox-stage` module.
Plugins should inherit from this class and implement the `filter` and `run` methods.
The `filter` method should take a list of `ImageFile` objects and return a list of `ImageFile` objects.
The most common way to achieve this would be to define an `ImageFilter` and use the `filter` method of that class.
The `run` method should take a list of `ImageFile` objects and return a list of `ImageFile` objects.
This method should perform the actual processing of the images.

Below is an example that calculates the sum of a list of multi-echo images of an MEMPRAGE acquisition.
```python
import nibabel as nib
import numpy as np

from radifox.naming import ImageFile, ImageFilter
from radifox.modules import StagingPlugin

class MEMPRAGEPlugin(StagingPlugin):
    @staticmethod
    def filter(images: list[ImageFile]) -> list[ImageFile]:
        return ImageFilter(
            modality="T1",
            technique="IRFSPGR",
            extras=lambda x: any("ECHO" in s or s == "SUM" for s in x),
        ).filter(images)

    @staticmethod
    def run(images: list[ImageFile]) -> list[ImageFile]:
        out_imgs = []
        for img_set in MEMPRAGEPlugin.sort_by_series(images):
            # Choose a SUM image if both echoes and SUM are available
            sum_imgs = [img for img in img_set if "SUM" in img.extras]
            if sum_imgs:
                out_imgs.append(sum_imgs[0])
            else:
                out_imgs.append(MEMPRAGEPlugin.sum_memprage(img_set))
        return out_imgs

    @staticmethod
    def sum_memprage(imgs: list[ImageFile]) -> ImageFile:
        """Create a sum image from a list of MEMPRAGE echo images."""
        temp_img = sorted(imgs, key=lambda x: x.name)[0]
        out_fpath = temp_img.path.parent.parent / "stage" / f"{temp_img.stem}_sum.nii.gz"
        obj = nib.load(temp_img.path)
        sum_data = np.sum(
            [nib.Nifti1Image.load(img.path).get_fdata(dtype=np.float32) for img in imgs], axis=0
        )
        nib.Nifti1Image(sum_data, None, obj.header).to_filename(out_fpath)
        return ImageFile(out_fpath)
```

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

## Provenance
The auto-provenance system is a system for tracking the provenance of processing results.
It allows developers to easily include RADIFOX management features into their processing scripts in a consistent way.
This includes automatic generation of provenance records, automatic logging during execution and automatic generation of QA images from outputs.

The auto-provenance system is based on the `ProcessingModule` class.
This is an abstract class that defines the basic structure of a processing module.
Developers should inherit from this class and implement the `cli` and `run` methods, as well as define the `name` and `version` class attributes.
See [ProcessingModule](#processingmodule) for more details.

### Provenance Records
Provenance from this system is stored in two different ways.
The first is at the session level in the `<subject-id>_<session-id>_Provenance.yml` file.
This is an append-only text file that contains the provenance records of all processing steps for the session.
The second is a provenance text file (`.prov`) that is stored with each processed file.
This contains the provenance record for the process that created the processed file only.

Provenance records are stored in the YAML format that is human-readable, but also easily parsed by Python.
The format is as follows:
```yaml
---
Id: <record-id>
Module: <module-name>:<module-version>
Container: 
  url: <container-url>:<container-tag>@<container-commit>
  hash: <container-hash>
  builder: <container-builder>
  timestamp: <container-timestamp>
User: <user-name>@<hostname>
StartTime: <start-timestamp>
Duration: <duration-days-hours-minutes-seconds>
Inputs:
  <input-key-1>: <input-filename-1>:<input-hash-1>
  <input-key-2>: 
    - <input-filename-2>:<input-hash-2>
    - <input-filename-3>:<input-hash-3>
Outputs:
  <output-key-1>: <output-filename-1>:<output-hash-1>
  <output-key-2>: 
    - <output-filename-2>:<output-hash-2>
    - <output-filename-3>:<output-hash-3>
Parameters:
  <parameter-key-1>: <parameter-value-1>
  <parameter-key-2>: <parameter-value-2>
Command: <command-string>
...
```

The `<record-id>` is a unique identifier for the record created from a hash of the rest of record.
The `<module-name>` and `<module-version>` are the name and version of the processing module that created the record (defined in `ProcessingModule` subclass).
The `<container-url>`, `<container-tag>`, `<container-commit>` and `<container-hash>` values are the URL, tag, commit, and hash of the container used to run the processing module.
The `<container-timestamp>`, `<container-builder>` values are the timestamp and builder identity of the container used to run the processing module.
These are derived from specific labels set during container creation.
For more information on how compatible containers are created, see [Container Creation](#container-creation).
The `<user-name>` and `<timestamp>` are the user name of the user that ran the processing module and the timestamp of the processing module run completion.
The `<input-key>`s, `<input-filename>`s, and `<input-hash>`s are the input names, filenames, and hashes of the input files to the processing module.
Outputs are structured the same way.
The `<parameter-key>`s and `<parameter-value>`s are the key-value pairs of the parameters passed to the processing module (that are not files).
The `<command-string>` is the exact command string that was used to run the processing module.

### Automatic Logging
The auto-provenance system also includes automatic logging during execution.
This is done by setting up a `logging` handler that writes to the `logs` directory in the session directory.
This handler is set up by default to log all messages to the `logs/<module-name>/<first-input-filename>-<timestamp>-info.log` file.
This can be adjusted to `logs/<module-name>-<timestamp>-info.log` by setting `log_uses_filename` to `False` in the `ProcessingModule` subclass.
Currently, there is support for `INFO`, `WARNING` and `ERROR` level messages.
They can be accessed at any point in the `run` method by calling `logging.info(message)` (or `warning` or `error`).
You must import `logging` at the top of the file to use this feature.
If there are warnings or errors produced during execution, they will be written to additional log files (`-warning.log` and `-error.log`) for easy viewing.
There is currently no support for `DEBUG` level messages, but that is planned for the future.

### Automatic QA Images
The auto-provenance system also includes automatic generation of QA images from outputs.
Any output that is returned from the `run` method will have a QA image generated automatically, if it is a NIfTI file (ends in `.nii.gz`).

# Additional Information

## Advanced CLI Usage

### `radifox-stage`
| Option                   | Description                                                               | Default    |
|--------------------------|---------------------------------------------------------------------------|------------|
| `--subject-dir`          | The path to the subject directory to stage.                               | `required` |
| `--image-types`          | A set of `ImageFilter` strings used to filter the images for staging      | `required` |
| `--reg-filters`          | A set of `ImageFilter` strings used for determining registration targets. | `None`     |
| `--keep-best-res`        | Only keep the highest resolution image for each filter.                   | `False`    |
| `--plugin-paths`         | A list of additional plugin paths to add.                                 | `None`     |
| `--skip-default-plugins` | Skip the default plugins included with staging.                           | `False`    |
| `--skip-set-sform`       | Skip setting the sform matrix for staged images.                          | `False`    |

## Container Creation
For reproducibility, processing must be done in a container.
This can be Docker or Apptainer/Singularity, but requires a few specific labels to be set to maintain strict accounting of the container used.

The labels are:
 - `ci.timestamp`: Timestamp of the container image creation (`%Y-%m-%dT%H:%M:%SZ`)
 - `ci.builder`: The username of the builder of the container image (who initiated the build)
 - `ci.image`: URL of the container image in a repository (e.g. Docker Hub)
 - `ci.tag`: Version tag of the container image
 - `ci.commit`: Commit hash of the Dockerfile/repo used to build the container image
 - `ci.digest`: Digest hash of the container image

These labels are most easily set by using Continuous Integration (CI) to create your images.
This is an example `.gitlab-ci.yml` to achieve this on GitLab:
```yaml
variables:
  GIT_STRATEGY: clone
  GIT_DEPTH: 0

build:
  image: docker:20.10.16
  stage: build
  services:
    - docker:20.10.16-dind
  variables:
    TAG: $CI_REGISTRY_IMAGE:$CI_COMMIT_REF_NAME
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build 
      --label ci.timestamp=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
      --label ci.builder=$GITLAB_USER_LOGIN
      --label ci.image=$CI_REGISTRY_IMAGE
      --label ci.tag=$CI_COMMIT_REF_NAME
      --label ci.commit=$CI_COMMIT_SHA 
      -t $TAG .
    - DIGEST=$(docker inspect --format='{{index .Id}}' $TAG)
    - echo "FROM $TAG" | docker buildx build --label ci.digest=$DIGEST -t $TAG --push -
  only:
    - tags
```

Using a GitHub action is similar and can be done with GitHub Actions:
```yaml
name: Publish Docker Image to GHCR

on:
  push:
    branches:
      - 'main'
    tags:
      - '*'

jobs:
  docker:
    name: Build and Push Docker Image
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      -
        name: Get build time
        id: build_time
        run: echo "time=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" >> "$GITHUB_OUTPUT"
      -
        name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: ${{ github.ref_name }}
      -
        name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
        with:
          driver: docker
      -
        name: Login to Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ github.token }}
      -
        name: Build image
        id: docker_build
        uses: docker/build-push-action@v5
        with:
          context: .
          load: true
          labels: |
            ci.timestamp=${{ steps.build_time.outputs.time }}
            ci.image=${{ github.repository }}
            ci.tag=${{ github.ref_name }}
            ci.commit=${{ github.sha }}
            ci.builder=${{ github.triggering_actor }}
          tags: ghcr.io/${{ github.repository }}:${{ github.ref_name }}
          build-args: |
            BUILDKIT_CONTEXT_KEEP_GIT_DIR=true
      -
        name: Write new Dockerfile
        run: echo "FROM ghcr.io/${{ github.repository }}:${{ github.ref_name }}" > Dockerfile.new

      - name: Build labeled image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: Dockerfile.new
          push: true
          labels: ci.digest=${{ steps.docker_build.outputs.digest }}
          tags: ghcr.io/${{ github.repository }}:${{ github.ref_name }}

```
