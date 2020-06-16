import json
import os
import re


META_TIME_CODES = {1: '00', 2: '06', 3: '12', 4: '24', 5: '36', 6: '48'}


class Metadata:
    def __init__(self, project_id, patient_id, time_id, site_id=None, project_shortname=None):
        self.project_id = project_id
        self.patient_id = patient_id
        self.time_id = time_id
        self.site_id = site_id
        self.project_shortname = self.project_id.upper() if project_shortname is None else project_shortname

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
        return cls('treatms', patient_id, time_id, site_id, 'TMS')

    def __repr_json__(self):
        return self.__dict__

    def prefix_to_str(self):
        if self.site_id is None:
            return self.project_shortname + '-' + self.patient_id + '_' + self.time_id
        else:
            return self.project_shortname + '-' + self.site_id + '-' + \
                   self.patient_id + '_' + self.time_id

    def dir_to_str(self):
        if self.site_id is None:
            return os.path.join(self.project_id, self.patient_id, self.time_id)
        else:
            return os.path.join(self.project_id, self.site_id + '-' + self.patient_id, self.time_id)
