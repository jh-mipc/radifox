from __future__ import annotations
import json
import logging
from pathlib import Path
import re
from typing import Optional

from .utils import hash_file_dir


META_TIME_CODES = {1: '00', 2: '06', 3: '12', 4: '24', 5: '36', 6: '48'}


class Metadata:
    def __init__(self, project_id: str, patient_id: str, time_id: str, site_id: Optional[str] = None,
                 project_shortname: Optional[str] = None, no_project_subdir: bool = False) -> None:
        self.ProjectID = project_id
        self.PatientID = patient_id
        self.TimeID = time_id
        self.SiteID = site_id
        self.AttemptNum = None
        self.ProjectShortName = self.ProjectID.upper() if project_shortname is None else project_shortname
        self.TMSMetaFileHash = None
        self._RawMetaFileObj = None
        self._NoProjectSubdir = no_project_subdir

    @classmethod
    def from_tms_metadata(cls, metadata_file: Path, no_project_subdir: bool = False) -> Metadata:
        metadata_obj = json.loads(metadata_file.read_text())['metadataFieldsToValues']
        site_id, patient_id = metadata_obj['patient_id'].split('-')
        time_id = None
        for key in metadata_obj.keys():
            if re.match(r'mri_timepoint\(\d+\)', key):
                tp_num = int(re.findall(r'\d+', key)[0])
                time_id = str(83 + tp_num) if tp_num > 6 else META_TIME_CODES[tp_num]
                break
        out_cls = cls('treatms', patient_id, time_id, site_id, no_project_subdir=no_project_subdir)
        out_cls.TMSMetaFileHash = hash_file_dir(metadata_file)
        out_cls._RawMetaFileObj = {re.sub(r'\([0-9]*\)', '', k): v for k, v in metadata_obj.items()}
        return out_cls

    @classmethod
    def from_dict(cls, dict_obj: dict) -> Metadata:
        out_cls = cls(dict_obj['ProjectID'], dict_obj['PatientID'], dict_obj['TimeID'],
                      dict_obj['SiteID'], dict_obj['ProjectShortName'], dict_obj['_NoProjectSubdir'])
        if 'TMSMetaFileHash' in dict_obj:
            out_cls.TMSMetaFileHash = dict_obj['TMSMetaFileHash']
            out_cls._RawMetaFileObj = dict_obj['_RawMetaFileObj']
        return out_cls

    def __repr_json__(self) -> dict:
        skip_keys = ['AttemptNum']
        if self.TMSMetaFileHash is None:
            skip_keys += ['TMSMetaFileHash', '_RawMetaFileObj']
        return {k: v for k, v in self.__dict__.items() if k not in skip_keys}

    def check_metadata(self) -> None:
        if self._RawMetaFileObj is not None and self.SiteID != self._RawMetaFileObj['site_id']:
            logging.warning('Site ID (%s) does not match site portion of Patient ID (%s). '
                            'Using %s as Site ID.' %
                            (self._RawMetaFileObj['site_id'], self.SiteID, self.SiteID))

    def prefix_to_str(self) -> str:
        if self.SiteID is None:
            return self.ProjectShortName + '-' + self.PatientID + '_' + self.TimeID
        else:
            return self.ProjectShortName + '-' + self.SiteID + '-' + \
                   self.PatientID + '_' + self.TimeID

    def dir_to_str(self) -> Path:
        patient_id = self.ProjectShortName + '-' + self.PatientID if self.SiteID is None \
            else self.ProjectShortName + '-' + self.SiteID + '-' + self.PatientID
        # noinspection PyStringFormat
        output_dir = Path(patient_id, self.TimeID + ('' if self.AttemptNum is None else ('-%d' % self.AttemptNum)))
        if not self._NoProjectSubdir:
            output_dir = Path(self.ProjectID, output_dir)
        return output_dir
