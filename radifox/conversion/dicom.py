import logging
from collections import defaultdict
from pathlib import Path
import shutil
from typing import Optional

from pydicom import dcmread, Dataset, FileDataset
from pydicom.errors import InvalidDicomError
from pydicom.dicomdir import DicomDir

from .base import BaseInfo, BaseSet, ImageOrientation, TruncatedImageValue, MATCHING_ITEMS
from .lut import LookupTable
from .metadata import Metadata
from .utils import mkdir_p, extract_de, create_sf_headers

DCM_HEADER_ATTRS = [
    "InstitutionName",
    "Manufacturer",
    ("ManufacturerModelName", "ScannerModelName"),
    ("DeviceSerialNumber", "DeviceIdentifier"),
    "SeriesDescription",
    "MagneticFieldStrength",
    ("MRAcquisitionType", "AcquisitionDimension"),
    ("SpacingBetweenSlices", "SliceSpacing"),
    "SliceThickness",
    "FlipAngle",
    "RepetitionTime",
    "EchoTime",
    "InversionTime",
    "TriggerTime",
    "EchoTrainLength",
    "AcquisitionMatrix",
    ("ScanningSequence", "SequenceType"),
    "ScanOptions",
    "ImageType",
    "SeriesNumber",
    "ComplexImageComponent",
    "BodyPartExamined",
    "StudyDescription",
    "SequenceVariant",
    ("PixelSpacing", "ReconResolution"),
    "SoftwareVersions",
    "NumberOfAverages",
    "PercentSampling",
    "ReceiveCoilName",
    "PixelBandwidth",
    ("VariableFlipAngleFlag", "VariableFlipAngle"),
]

DCM_HEADER_LISTS = [
    "ScanningSequence",
    "SequenceVariant",
    "ImageType",
    "ScanOptions",
    "SoftwareVersions",
]


class DicomInfo(BaseInfo):
    def __init__(
        self,
        source_path: Path,
        ds: Dataset | FileDataset,
        series_uid: str,
        num_frames: int,
        multiframe: bool,
    ) -> None:
        super().__init__(source_path)
        self.SeriesUID = series_uid
        self.StudyUID = getattr(ds, "StudyInstanceUID", None)
        self.NumFiles = num_frames
        self.MultiFrame = multiframe
        for item in DCM_HEADER_ATTRS:
            get_item, set_item = item if isinstance(item, tuple) else (item, item)
            setattr(
                self,
                set_item,
                extract_de(ds, get_item, self.SeriesUID, get_item in DCM_HEADER_LISTS),
            )
        if self.SeriesDescription is None:
            self.SeriesDescription = ds.ProtocolName if hasattr(ds, "ProtocolName") else ""
        series_date = extract_de(ds, "SeriesDate", self.SeriesUID, False)
        series_time = extract_de(ds, "SeriesTime", self.SeriesUID, False)
        self.AcqDateTime = " ".join(
            [
                str(series_date) if series_date is not None else "0001-01-01",
                str(series_time) if series_date is not None else "00:00:00",
            ]
        )
        self.Manufacturer = (
            "" if self.Manufacturer is None else self.Manufacturer.upper().split(" ")[0]
        )
        if (0x2005, 0x1444) in ds:
            turbo = int(ds[(0x2005, 0x1444)].value)
            self.EchoTrainLength = turbo if turbo > 0 else self.EchoTrainLength
        if (0x2001, 0x1013) in ds:
            try:
                self.EPIFactor = int(ds[(0x2001, 0x1013)].value)
            except ValueError:
                pass
        if self.InversionTime == 0.0 and (0x2001, 0x101B) in ds:
            try:
                self.InversionTime = float(ds[(0x2001, 0x101B)].value)
            except ValueError:
                pass
            if self.TriggerTime is not None and "mp2rage" in self.SeriesDescription.lower():
                self.InversionTime = self.TriggerTime
                self.TriggerTime = None
        self.ReconMatrix = [getattr(ds, "Columns", 0), getattr(ds, "Rows", 0)]
        if self.AcquisitionMatrix is not None:
            # noinspection PyUnresolvedReferences
            self.AcquisitionMatrix = (
                [self.AcquisitionMatrix[0], self.AcquisitionMatrix[3]]
                if self.AcquisitionMatrix[1] == 0
                else [self.AcquisitionMatrix[2], self.AcquisitionMatrix[1]]
            )
        else:
            # Assume ReconMatrix is AcquisitionMatrix if AcquisitionMatrix is not present
            self.AcquisitionMatrix = self.ReconMatrix
        self.FieldOfView = [
            res * num for res, num in zip(self.ReconResolution, self.ReconMatrix)
        ]
        self.AcquiredResolution = [
            fov / num for fov, num in zip(self.FieldOfView, self.AcquisitionMatrix)
        ]
        self.FieldOfView = [round(fov, 2) for fov in self.FieldOfView]
        self.AcquiredResolution = [round(res, 5) for res in self.AcquiredResolution]
        self.ReconResolution = [round(res, 5) for res in self.ReconResolution]

        self.SequenceName = getattr(ds, "SequenceName", getattr(ds, "PulseSequenceName", None))
        if self.SequenceName is None and (0x0019, 0x109C) in ds:
            self.SequenceName = str(ds[(0x0019, 0x109C)].value)
        self.ExContrastAgent = getattr(
            ds, "ContrastBolusAgent", getattr(ds, "ContrastBolusAgentSequence", None)
        )
        self.ImageOrientationPatient = ImageOrientation(
            getattr(ds, "ImageOrientationPatient", None)
        )
        self.SliceOrientation = self.ImageOrientationPatient.get_plane()
        self.ImagePositionPatient = TruncatedImageValue(getattr(ds, "ImagePositionPatient", None))
        if self.ComplexImageComponent is None and any(
            [
                comp in self.ImageType
                for comp in ["M", "P", "R", "I", "MAGNITUDE", "PHASE", "REAL", "IMAGINARY"]
            ]
        ):
            if "M" in self.ImageType or "MAGNITUDE" in self.ImageType:
                self.ComplexImageComponent = "MAGNITUDE"
            elif "P" in self.ImageType or "PHASE" in self.ImageType:
                self.ComplexImageComponent = "PHASE"
            elif "R" in self.ImageType or "REAL" in self.ImageType:
                self.ComplexImageComponent = "REAL"
            elif "I" in self.ImageType or "IMAGINARY" in self.ImageType:
                self.ComplexImageComponent = "IMAGINARY"


class DicomSet(BaseSet):
    def __init__(
        self,
        source: Path,
        output_root: Path,
        metadata_obj: Metadata,
        lut_obj: LookupTable,
        remove_identifiers: bool = False,
        date_shift_days: int = 0,
        manual_names: Optional[dict] = None,
        input_hash: Optional[str] = None,
    ) -> None:
        super().__init__(
            source,
            output_root,
            metadata_obj,
            lut_obj,
            remove_identifiers,
            date_shift_days,
            manual_names,
            input_hash,
        )

        logging.info("Loading DICOMs.")
        for dcmdir in sorted((output_root / self.Metadata.dir_to_str() / "dcm").glob("*")):
            ds = dcmread(str(sorted(dcmdir.glob("*"))[0]), stop_before_pixels=True)
            if ds.SOPClassUID == "1.2.840.10008.5.1.4.1.1.4.1":
                sfds_dict = defaultdict(list)
                for sfds in sorted(create_sf_headers(ds), key=lambda x: x.InstanceNumber):
                    sfds_dict[get_intra_series_meta(sfds)].append(sfds)
                for i, sfds_list in enumerate(sfds_dict.values()):
                    self.SeriesList.append(
                        DicomInfo(
                            dcmdir,
                            sfds_list[0],
                            sfds_list[0].SeriesInstanceUID + (".%02d" % i),
                            len(sfds_list),
                            True,
                        )
                    )
            else:
                self.SeriesList.append(
                    DicomInfo(dcmdir, ds, dcmdir.name, len(list(dcmdir.glob("*"))), False)
                )

        study_nums, series_nums = self.get_unique_study_series(self.SeriesList)
        for di in self.SeriesList:
            logging.info("Processing %s" % di.SourcePath)
            if di.should_convert():
                di.create_image_name(
                    self.Metadata.prefix_to_str(),
                    study_nums[di.SourcePath],
                    series_nums[di.SourcePath],
                    self.LookupTable,
                    self.ManualNames,
                )

        logging.info("Generating unique names")
        self.generate_unique_names()


def get_intra_series_meta(ds: Dataset) -> tuple:
    return tuple(
        ImageOrientation(getattr(ds, item, None))
        if item == "ImageOrientationPatient"
        else extract_de(ds, item, ds.SeriesInstanceUID)
        for item in MATCHING_ITEMS
    )


def sort_dicoms(dcm_dir: Path, force_dicom: bool = False) -> None:
    logging.info("Sorting DICOMs")
    valid_dcms = []
    for filepath in dcm_dir.rglob("*"):
        if filepath.is_file():
            try:
                ds = dcmread(str(filepath), stop_before_pixels=True)
            except (InvalidDicomError, KeyError):
                if force_dicom:
                    try:
                        ds = dcmread(str(filepath), stop_before_pixels=True, force=True)
                        ds.save_as(str(filepath), write_like_original=False)
                    except ValueError:
                        continue
                else:
                    continue
            if isinstance(ds, DicomDir):
                continue
            if ds.SOPClassUID not in ["1.2.840.10008.5.1.4.1.1.4", "1.2.840.10008.5.1.4.1.1.4.1"]:
                continue
            if getattr(ds, "SeriesInstanceUID", None) is None:
                continue
            if ds.SOPClassUID == "1.2.840.10008.5.1.4.1.1.4.1":
                valid_dcms.extend((filepath, sf) for sf in create_sf_headers(ds))
            else:
                valid_dcms.append((filepath, ds))
    if not valid_dcms:
        raise ValueError("No valid DICOMs found in %s, try re-running with --force-dicom" % dcm_dir)

    # Sort valid DICOMs according to series and intra-series metadata
    valid_dcms = sorted(valid_dcms, key=lambda x: (x[1].SeriesInstanceUID, x[1].InstanceNumber))
    dicom_sort_dict = {}
    for dcm_file, dcm_ds in valid_dcms:
        uid = dcm_ds.SeriesInstanceUID
        intra_series = get_intra_series_meta(dcm_ds)
        if (uid, intra_series) not in dicom_sort_dict:
            dicom_sort_dict[(uid, intra_series)] = []
        dicom_sort_dict[(uid, intra_series)].append((dcm_file, dcm_ds))

    # Get new series (based on series/intra-series metadata)
    new_series_uids = {}
    count_dict = defaultdict(int)
    for scan in dicom_sort_dict:
        count_dict[scan[0]] += 1
        new_series_uids[scan] = scan[0] + (".%02d" % count_dict[scan[0]])

    # Find new series that have scans that share DICOM files (multi-frame)
    uids_by_files = defaultdict(list)
    for scan, dcm_list in dicom_sort_dict.items():
        uids_by_files[tuple(sorted(set(dcm[0] for dcm in dcm_list)))].append(scan)
    # Merge new series uids that share DICOM files
    for scans in uids_by_files.values():
        if len(scans) > 1:
            for scan in scans:
                new_series_uids[scan] = ".".join(new_series_uids[scan].split(".")[:-1])

    for new_dcm_dir in new_series_uids.values():
        mkdir_p(dcm_dir / new_dcm_dir)
    inst_nums = defaultdict(lambda: defaultdict(list))
    moved = set()
    for scan, dcm_tuples in dicom_sort_dict.items():
        output_dir = dcm_dir / new_series_uids[scan]
        for dcm_file, dcm_ds in dcm_tuples:
            if dcm_file in moved:
                continue
            dcm_file.rename(output_dir / dcm_file.name)
            moved.add(dcm_file)
            inst_nums[new_series_uids[scan]][dcm_ds.InstanceNumber].append(
                output_dir / dcm_file.name
            )

    new_dirs = list(new_series_uids.values())
    for item in dcm_dir.glob("*"):
        if item.name not in new_dirs:
            if item.is_dir():
                shutil.rmtree(item)
            elif item.is_file():
                item.unlink()

    logging.info("Checking for duplicate DICOM files")
    for uid in inst_nums:
        if any([len(inst_nums[uid][num]) > 1 for num in inst_nums[uid]]):
            logging.info("Possible duplicates found for %s" % uid)
            remove_duplicates(dcm_dir / uid)

    logging.info("Sorting complete")


def remove_duplicates(dcmdir: Path) -> None:
    inst_nums = defaultdict(list)
    for dcmfile in dcmdir.glob("*"):
        ds = dcmread(str(dcmfile), stop_before_pixels=True)
        inst_nums[ds.InstanceNumber].append((dcmfile, ds))
    to_unlink = set()
    for num in inst_nums:
        inst_nums[num] = sorted(
            inst_nums[num], key=lambda x: getattr(x[1], "InstanceCreationTime", 0)
        )
        for i in range(len(inst_nums[num]) - 1):
            for j in range(i + 1, len(inst_nums[num])):
                diff_keys = []
                dcmfile1, ds1 = inst_nums[num][i]
                dcmfile2, ds2 = inst_nums[num][j]
                for key in ds1.keys():
                    if key in [(0x0008, 0x0013), (0x0008, 0x0018)]:
                        continue
                    if (key not in ds2.keys()) or (ds1[key].value != ds2[key].value):
                        diff_keys.append(key)
                if len(diff_keys) == 0:
                    if dcmread(str(dcmfile1)).PixelData == dcmread(str(dcmfile2)).PixelData:
                        logging.debug("Found duplicate of %s" % dcmfile1)
                        logging.debug("Removing duplicate file %s" % dcmfile2)
                        to_unlink.add(dcmfile2)
                        break
    for dcmpath in to_unlink:
        dcmpath.unlink()
    if len(to_unlink) > 0:
        logging.info("Removed %d duplicate DICOM files" % len(to_unlink))
    else:
        logging.info("No duplicate DICOM files found")
