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
There are also optional dependencies that can be installed with pip to ensure the full functionality of some features.

If you do not have [dcm2niix](https://github.com/rordanlab/dcm2niix) installed, you can install that with the `dcm2niix` extra:
```bash
pip install radifox[dcm2niix]
```
To include the web-based quality assurance system, install with the `qa` extra:
```bash
pip install radifox[qa]
```

## Basic Usage


# RADIFOX Components

## File Organization

## Naming

## Conversion

## Provenance

## Quality Assurance