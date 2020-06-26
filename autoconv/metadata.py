import json
import logging
import os
import re

from .utils import sha1_file_dir


META_TIME_CODES = {1: '00', 2: '06', 3: '12', 4: '24', 5: '36', 6: '48'}


class Metadata:
    def __init__(self, project_id, patient_id, time_id, site_id=None, project_shortname=None,
                 no_project_subdir=False):
        self.ProjectID = project_id
        self.PatientID = patient_id
        self.TimeID = time_id
        self.SiteID = site_id
        self.ProjectShortName = self.ProjectID.upper() if project_shortname is None else project_shortname
        self.TMSMetaFile = None
        self.TMSMetaFileHash = None
        self._RawMetaFileObj = None
        self._NoProjectSubdir = no_project_subdir

    @classmethod
    def from_tms_metadata(cls, metadata_file, no_project_subdir=False):
        with open(metadata_file) as fp:
            metadata_obj = json.load(fp)['metadataFieldsToValues']
        site_id, patient_id = metadata_obj['patient_id'].split('-')
        time_id = None
        for key in metadata_obj.keys():
            if re.match(r'mri_timepoint\(\d+\)', key):
                tp_num = int(re.findall(r'\d+', key)[0])
                time_id = str(83 + tp_num) if tp_num > 6 else META_TIME_CODES[tp_num]
                break
        out_cls = cls('treatms', patient_id, time_id, site_id, no_project_subdir=no_project_subdir)
        out_cls.TMSMetaFile = metadata_file
        out_cls.TMSMetaFileHash = sha1_file_dir(metadata_file)
        out_cls._RawMetaFileObj = {re.sub(r'\([0-9]*\)', '', k): v for k, v in metadata_obj.items()}
        return out_cls

    def __repr_json__(self):
        skip_keys = []
        if self.TMSMetaFile is None:
            skip_keys += ['TMSMetaFile', 'TMSMetaFileHash', '_RawMetaFileObj']
        return {k: v for k, v in self.__dict__.items() if k not in skip_keys}

    def check_metadata(self):
        if self._RawMetaFileObj is not None and self.SiteID != self._RawMetaFileObj['site_id']:
            logging.warning('Site ID (%s) does not match site portion of Patient ID (%s). '
                            'Using %s as Site ID.' %
                            (self._RawMetaFileObj['site_id'], self.SiteID, self.SiteID))

    def prefix_to_str(self):
        if self.SiteID is None:
            return self.ProjectShortName + '-' + self.PatientID + '_' + self.TimeID
        else:
            return self.ProjectShortName + '-' + self.SiteID + '-' + \
                   self.PatientID + '_' + self.TimeID

    def dir_to_str(self):
        patient_id = self.ProjectShortName + '-' + self.PatientID if self.SiteID is None \
            else self.ProjectShortName + '-' + self.SiteID + '-' + self.PatientID
        output_dir = os.path.join(patient_id, self.TimeID)
        if not self._NoProjectSubdir:
            output_dir = os.path.join(self.ProjectID, output_dir)
        return output_dir
