import argparse
import json
import logging
from pathlib import Path
import shutil
from typing import List, Optional

from .._version import __version__
from .exec import run_conversion, ExecError
from .lut import LookupTable
from .metadata import Metadata
from .utils import hash_file_dir, silentremove, mkdir_p, version_check


def convert(args: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Source directory/file to convert.")
    parser.add_argument(
        "-o", "--output-root", type=Path, help="Output root directory.", required=True
    )
    parser.add_argument("-l", "--lut-file", type=Path, help="Lookup table file.")
    parser.add_argument("-p", "--project-id", type=str, help="Project ID.")
    parser.add_argument("-s", "--subject-id", type=str, help="Subject ID.")
    parser.add_argument("-e", "--session-id", type=str, help="Session ID.")
    parser.add_argument("--site-id", type=str, help="Site ID.")
    parser.add_argument("--tms-metafile", type=Path, help="TMS metadata file.")
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")
    parser.add_argument(
        "--force", action="store_true", help="Force run even if it would be skipped."
    )
    parser.add_argument(
        "--reckless", action="store_true", help="Force run and overwrite existing data."
    )
    parser.add_argument(
        "--safe", action="store_true", help="Add -N to session ID, if session exists."
    )
    parser.add_argument(
        "--no-project-subdir", action="store_true", help="Do not create project subdirectory."
    )
    parser.add_argument("--parrec", action="store_true", help="Source is PARREC.")
    parser.add_argument(
        "--symlink",
        action="store_true",
        help="Create symbolic links to source data instead of copying.",
    )
    parser.add_argument(
        "--hardlink",
        action="store_true",
        help="Create hard links to source data instead of copying.",
    )
    parser.add_argument("--institution", type=str, help="Institution name.")
    parser.add_argument("--field-strength", type=int, help="Magnetic field strength.")
    parser.add_argument("--anonymize", action="store_true", help="Anonymize DICOM data.")
    parser.add_argument("--date-shift-days", type=int, help="Number of days to shift dates.")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)

    args = parser.parse_args(args)

    for argname in ["source", "output_root", "lut_file", "tms_metafile"]:
        if getattr(args, argname) is not None:
            setattr(args, argname, getattr(args, argname).resolve())

    if args.hardlink and args.symlink:
        raise ValueError("Only one of --symlink and --hardlink can be used.")
    linking = "hardlink" if args.hardlink else ("symlink" if args.symlink else None)

    mapping = {"subject_id": "SubjectID", "session_id": "SessionID", "site_id": "SiteID"}
    if args.tms_metafile:
        metadata = Metadata.from_tms_metadata(args.tms_metafile, args.no_project_subdir)
        for argname in ["subject_id", "session_id", "site_id"]:
            if getattr(args, argname) is not None:
                setattr(metadata, mapping[argname], getattr(args, argname))
    else:
        for argname in ["project_id", "subject_id", "session_id"]:
            if getattr(args, argname) is None:
                raise ValueError(
                    "%s is a required argument when no metadata file is provided." % argname
                )
        metadata = Metadata(
            args.project_id,
            args.subject_id,
            args.session_id,
            args.site_id,
            args.no_project_subdir,
        )

    if args.lut_file is None:
        lut_file = (
            (args.output_root / (metadata.projectname + "-lut.csv"))
            if args.no_project_subdir
            else (args.output_root / metadata.projectname / (metadata.projectname + "-lut.csv"))
        )
    else:
        lut_file = args.lut_file

    manual_json_file = (
        args.output_root / metadata.dir_to_str() / (metadata.prefix_to_str() + "_ManualNaming.json")
    )
    manual_names = json.loads(manual_json_file.read_text()) if manual_json_file.exists() else {}

    type_dirname = "%s" % "parrec" if args.parrec else "dcm"
    if (args.output_root / metadata.dir_to_str() / type_dirname).exists():
        if args.safe:
            metadata.AttemptNum = 2
            while (args.output_root / metadata.dir_to_str() / type_dirname).exists():
                metadata.AttemptNum += 1
        elif args.force or args.reckless:
            if not args.reckless:
                json_file = (
                    args.output_root
                    / metadata.dir_to_str()
                    / (metadata.prefix_to_str() + "_UnconvertedInfo.json")
                )
                if not json_file.exists():
                    raise ValueError(
                        "Unconverted info file (%s) does not exist for consistency checking. "
                        "Cannot use --force, use --reckless instead." % json_file
                    )
                json_obj = json.loads(json_file.read_text())
                if json_obj["Metadata"]["TMSMetaFileHash"] is not None:
                    if metadata.TMSMetaFileHash is None:
                        raise ValueError(
                            "Previous conversion did not use a TMS metadata file, "
                            "run with --reckless to ignore this error."
                        )
                    if json_obj["Metadata"]["TMSMetaFileHash"] != metadata.TMSMetaFileHash:
                        raise ValueError(
                            "TMS meta data file has changed since last conversion, "
                            "run with --reckless to ignore this error."
                        )
                elif (
                    json_obj["Metadata"]["TMSMetaFileHash"] is None
                    and metadata.TMSMetaFileHash is not None
                ):
                    raise ValueError(
                        "Previous conversion used a TMS metadata file, "
                        "run with --reckless to ignore this error."
                    )
                if hash_file_dir(args.source, False) != json_obj["InputHash"]:
                    raise ValueError(
                        "Source file(s) have changed since last conversion, "
                        "run with --reckless to ignore this error."
                    )
            shutil.rmtree(args.output_root / metadata.dir_to_str() / type_dirname)
            silentremove(args.output_root / metadata.dir_to_str() / "nii")
            for filepath in (args.output_root / metadata.dir_to_str()).glob("*.json"):
                silentremove(filepath)
        else:
            raise RuntimeError(
                "Output directory exists, run with --force to remove outputs and re-run."
            )

    manual_arg = {
        "MagneticiFieldStrength": args.field_strength,
        "InstitutionName": args.institution,
    }

    run_conversion(
        args.source,
        args.output_root,
        metadata,
        lut_file,
        args.verbose,
        args.parrec,
        False,
        linking,
        manual_arg,
        args.anonymize,
        args.date_shift_days,
        manual_names,
        None,
    )


def update(args: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path, help="Existing RADIFOX Directory to update.")
    parser.add_argument("-l", "--lut-file", type=Path, help="Lookup table file.")
    parser.add_argument(
        "--force", action="store_true", help="Force run even if it would be skipped."
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)

    args = parser.parse_args(args)

    session_id = args.directory.name
    subj_id = args.directory.parent.name

    json_file = args.directory / "_".join([subj_id, session_id, "UnconvertedInfo.json"])
    if not json_file.exists():
        safe_json_file = args.directory / "_".join(
            [subj_id, "-".join(session_id.split("-")[:-1]), "UnconvertedInfo.json"]
        )
        if not safe_json_file.exists():
            raise ValueError("Unconverted info file (%s) does not exist." % json_file)
        json_file = safe_json_file
    json_obj = json.loads(json_file.read_text())

    metadata = Metadata.from_dict(json_obj["Metadata"])
    if session_id != metadata.SessionID:
        metadata.AttemptNum = int(session_id.split("-")[-1])
    # noinspection PyProtectedMember
    output_root = (
        Path(*args.directory.parts[:-2])
        if metadata._NoProjectSubdir
        else Path(*args.directory.parts[:-3])
    )

    if args.lut_file is None:
        # noinspection PyProtectedMember
        if metadata._NoProjectSubdir:
            lut_file = output_root / (metadata.projectname + "-lut.csv")
        else:
            lut_file = (
                output_root / metadata.projectname / (metadata.projectname + "-lut.csv")
            )
    else:
        lut_file = args.lut_file
    lookup_dict = (
        LookupTable(lut_file, metadata.ProjectID, metadata.SiteID).LookupDict
        if lut_file.exists()
        else {}
    )

    manual_json_file = args.directory / (metadata.prefix_to_str() + "_ManualNaming.json")
    manual_names = json.loads(manual_json_file.read_text()) if manual_json_file.exists() else {}

    if not args.force and (
        version_check(json_obj["__version__"]["radifox"], __version__)
        and json_obj["LookupTable"]["LookupDict"] == lookup_dict
        and json_obj["ManualNames"] == manual_names
    ):
        print(
            "No action required. Software version, LUT dictionary and naming dictionary match for %s."
            % args.directory
        )
        return

    parrec = (args.directory / "parrec").exists()
    type_dir = args.directory / ("%s" % "parrec" if parrec else "dcm")

    mkdir_p(args.directory / "prev")
    for filename in ["nii", "qa", json_file.name]:
        if (args.directory / filename).exists():
            (args.directory / filename).rename(args.directory / "prev" / filename)
    try:
        run_conversion(
            type_dir,
            output_root,
            metadata,
            lut_file,
            args.verbose,
            parrec,
            True,
            None,
            json_obj.get("ManualArgs", {}),
            False,
            0,
            manual_names,
            json_obj["InputHash"],
        )
    except ExecError:
        logging.info("Exception caught during update. Resetting to previous state.")
        for filename in ["nii", "qa", json_file.name]:
            silentremove(args.directory / filename)
            if (args.directory / "prev" / filename).exists():
                (args.directory / "prev" / filename).rename(args.directory / filename)
    else:
        for dirname in ["stage", "proc"]:
            if (args.directory / dirname).exists():
                (args.directory / dirname / "CHECK").touch()
    silentremove(args.directory / "prev")


# TODO: Add "rename" command to rename sessions
