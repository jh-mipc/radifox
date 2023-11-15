import logging
from pathlib import Path
import shutil
from typing import Optional

from .._version import __version__
from .dicom import DicomSet, sort_dicoms
from .logging import create_loggers
from .metadata import Metadata
from .lut import LookupTable
from .parrec import ParrecSet, sort_parrecs
from .utils import (
    mkdir_p,
    extract_archive,
    allowed_archives,
    recursive_chmod,
    copytree_link,
    DIR_OCTAL,
    has_permissions,
    hash_value,
)


class ExecError(Exception):
    pass


def run_conversion(
    source: Optional[Path],
    output_root: Path,
    metadata: Metadata,
    lut_file: Path,
    verbose: bool,
    parrec: bool,
    rerun: bool,
    link: Optional[str],
    manual_args: dict,
    remove_identifiers: bool,
    date_shift_days: int,
    manual_names: dict,
    input_hash: Optional[str] = None,
) -> None:
    session_path = output_root / metadata.dir_to_str()
    mkdir_p(session_path)
    if not has_permissions(session_path, DIR_OCTAL):
        session_path.chmod(DIR_OCTAL)
    if not has_permissions(session_path.parent, DIR_OCTAL):
        session_path.parent.chmod(mode=DIR_OCTAL)

    create_loggers(output_root / metadata.dir_to_str() / "logs", "conversion", verbose)
    metadata.check_metadata()

    try:
        logging.info("Beginning scan conversion using RADIFOX v" + __version__)
        if remove_identifiers:
            logging.info(
                "Anonymization will be performed, including removal of copied source folders."
            )
        if not lut_file.exists():
            logging.warning("LUT file does not exist. Creating a blank file at %s." % lut_file)
            lut_file.write_text("Project,Site,InstitutionName,SeriesDescription,OutputFilename\n")
        lut = LookupTable(lut_file, metadata.ProjectID, metadata.SiteID)
        if metadata.AttemptNum is not None:
            logging.info("Multiple attempts found. This will be attempt #%d" % metadata.AttemptNum)
        if parrec:
            inst_name = (
                hash_value(manual_args["InstitutionName"])
                if remove_identifiers
                else manual_args["InstitutionName"]
            )
            logging.info(
                "PARREC source indicated. Using InstitutionName=%s and MagneticFieldStrength=%d"
                % (inst_name, manual_args["MagneticFieldStrength"])
            )
        logging.info("RADIFOX conversion starting: %s" % metadata.dir_to_str())
        type_folder = session_path / ("parrec" if parrec else "dcm")
        sort_func = sort_parrecs if parrec else sort_dicoms
        if not rerun:
            if source.is_dir():
                if link is not None:
                    logging.info("Linking files from source to %s folder" % type_folder.name)
                    if link not in ["symlink", "hardlink"]:
                        raise ValueError("Unsupported linking type.")
                    copytree_link(source, type_folder, link == "symlink")
                    logging.info("Linking complete")
                else:
                    logging.info("Copying files from source to %s folder" % type_folder.name)
                    # noinspection PyTypeChecker
                    shutil.copytree(source, type_folder, copy_function=shutil.copyfile)
                    logging.info("Copying complete")
            elif any([source.name.endswith(ext) for ext in allowed_archives()[1]]):
                extract_archive(source, type_folder)
            else:
                raise ValueError(
                    "Source is not a directory, but does not match one of "
                    "the available archive formats (%s)" % ", ".join(allowed_archives()[0])
                )
            recursive_chmod(type_folder)
            sort_func(type_folder)
            recursive_chmod(type_folder)

        if parrec:
            img_set = ParrecSet(
                source,
                output_root,
                metadata,
                lut,
                remove_identifiers,
                date_shift_days,
                manual_names,
                input_hash=input_hash,
                manual_args=manual_args,
            )
        else:
            img_set = DicomSet(
                source,
                output_root,
                metadata,
                lut,
                remove_identifiers,
                date_shift_days,
                manual_names,
                input_hash=input_hash,
            )
        img_set.create_all_nii()
        recursive_chmod(session_path / "nii")
        recursive_chmod(session_path / "qa")
        img_set.generate_unconverted_info()

        recursive_chmod(session_path / "logs")
        if remove_identifiers:
            shutil.rmtree(type_folder)
        logging.info("RADIFOX conversion finished: %s" % metadata.dir_to_str())
    except KeyboardInterrupt:
        raise
    except:
        logging.exception("Fatal error occurred.")
        raise ExecError()
