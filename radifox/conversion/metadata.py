from __future__ import annotations
import json
import logging
from pathlib import Path
import re
from typing import Optional

from .utils import hash_file_dir

META_TIME_CODES = {1: "00", 2: "06", 3: "12", 4: "24", 5: "36", 6: "48"}


class Metadata:
    def __init__(
        self,
        project_id: str,
        subject_id: str,
        session_id: str,
        site_id: Optional[str] = None,
        no_project_subdir: bool = False,
    ) -> None:
        self.ProjectID = project_id.upper()
        self.SubjectID = subject_id.upper()
        self.SessionID = session_id.upper()
        self.SiteID = site_id.upper() if site_id is not None else None
        self.AttemptNum = None
        self.TMSMetaFileHash = None
        self._RawMetaFileObj = None
        self._NoProjectSubdir = no_project_subdir

    @classmethod
    def from_tms_metadata(cls, metadata_file: Path, no_project_subdir: bool = False) -> Metadata:
        metadata_obj = json.loads(metadata_file.read_text())["metadataFieldsToValues"]
        if "patient_id" in metadata_obj:
            site_id, subject_id = metadata_obj["patient_id"].split("-")
        else:
            site_id, subject_id = metadata_obj["site_id"], "900"
        if subject_id == "900":
            session_id = "99"
        else:
            session_id = None
            for key in metadata_obj.keys():
                if re.match(r"mri_timepoint\(\d+\)", key):
                    tp_num = int(re.findall(r"\d+", key)[0])
                    session_id = str(83 + tp_num) if tp_num > 6 else META_TIME_CODES[tp_num]
                    break
        out_cls = cls(
            "treatms", subject_id, session_id, site_id, no_project_subdir=no_project_subdir
        )
        out_cls.TMSMetaFileHash = hash_file_dir(metadata_file)
        out_cls._RawMetaFileObj = {re.sub(r"\([0-9]*\)", "", k): v for k, v in metadata_obj.items()}
        return out_cls

    @classmethod
    def from_dict(cls, dict_obj: dict) -> Metadata:
        out_cls = cls(
            dict_obj["ProjectID"],
            dict_obj["SubjectID"],
            dict_obj["SessionID"],
            dict_obj["SiteID"],
            dict_obj["_NoProjectSubdir"],
        )
        if "TMSMetaFileHash" in dict_obj:
            out_cls.TMSMetaFileHash = dict_obj["TMSMetaFileHash"]
            out_cls._RawMetaFileObj = dict_obj["_RawMetaFileObj"]
        return out_cls

    def __repr_json__(self) -> dict:
        skip_keys = ["AttemptNum"]
        if self.TMSMetaFileHash is None:
            skip_keys += ["TMSMetaFileHash", "_RawMetaFileObj"]
        return {k: v for k, v in self.__dict__.items() if k not in skip_keys}

    @property
    def projectname(self) -> str:
        return self.ProjectID.lower()

    def check_metadata(self) -> None:
        if self._RawMetaFileObj is not None and self.SiteID != self._RawMetaFileObj["site_id"]:
            logging.warning(
                "Site ID (%s) does not match site portion of Subject ID (%s). "
                "Using %s as Site ID." % (self._RawMetaFileObj["site_id"], self.SiteID, self.SiteID)
            )

    def prefix_to_str(self) -> str:
        if self.SiteID is None:
            return f"{self.ProjectID}-{self.SubjectID}_{self.SessionID}"
        else:
            return f"{self.ProjectID}-{self.SiteID}-{self.SubjectID}_{self.SessionID}"

    def dir_to_str(self) -> Path:
        subject_str = (
            f"{self.ProjectID}-{self.SubjectID}"
            if self.SiteID is None
            else f"{self.ProjectID}-{self.SiteID}-{self.SubjectID}"
        )
        # noinspection PyStringFormat
        output_dir = Path(
            subject_str,
            self.SessionID + ("" if self.AttemptNum is None else ("-%d" % self.AttemptNum)),
        )
        if not self._NoProjectSubdir:
            output_dir = Path(self.projectname, output_dir)
        return output_dir
