import json
import os
import re


META_TIME_CODES = {1: '00', 2: '06', 3: '12', 4: '24', 5: '36', 6: '48'}


class Metadata:
    def __init__(self, project_id, patient_id, time_id, site_id=None, project_shortname=None):
        self.ProjectID = project_id
        self.PatientID = patient_id
        self.TimeID = time_id
        self.SiteID = site_id
        self.ProjectShortName = self.ProjectID.upper() if project_shortname is None else project_shortname
        self.TMSMetaFile = None

    @classmethod
    def from_tms_metadata(cls, metadata_file):
        with open(metadata_file) as fp:
            metadata_obj = json.load(fp)['metadataFieldsToValues']
        site_id, patient_id = metadata_obj['patient_id'].split('-')
        time_id = None
        for key in metadata_obj.keys():
            if re.match(r'mri_timepoint\(\d+\)', key):
                tp_num = int(re.findall(r'\d+', key)[0])
                time_id = str(83 + tp_num) if tp_num > 6 else META_TIME_CODES[tp_num]
                break
        out_cls = cls('treatms', patient_id, time_id, site_id, 'TMS')
        out_cls.TMSMetaFile = metadata_file
        return out_cls

    def __repr_json__(self):
        return self.__dict__ if self.TMSMetaFile is not None \
            else {k: v for k, v in self.__dict__.items() if k != 'tms_metadata_file'}

    def prefix_to_str(self):
        if self.SiteID is None:
            return self.ProjectShortName + '-' + self.PatientID + '_' + self.TimeID
        else:
            return self.ProjectShortName + '-' + self.SiteID + '-' + \
                   self.PatientID + '_' + self.TimeID

    def dir_to_str(self):
        if self.SiteID is None:
            return os.path.join(self.ProjectID, self.ProjectShortName + '-' + self.PatientID, self.TimeID)
        else:
            return os.path.join(self.ProjectID, self.ProjectShortName + '-'
                                + self.SiteID + '-' + self.PatientID, self.TimeID)
