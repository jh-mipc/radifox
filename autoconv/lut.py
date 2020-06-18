import os

from .utils import read_csv, is_intstr


class LookupTable:

    def __init__(self, lut_file, project_id, site_id):
        self.file_name = os.path.realpath(os.path.expanduser(lut_file))
        lut, self.file_hash = read_csv(lut_file)
        if site_id is None:
            site_id = ''
        self.lookup_dict = {}
        for row, (project, site) in enumerate(zip(lut['Project'], lut['Site'])):
            if is_intstr(site) and is_intstr(site_id):
                site = int(site)
                site_id = int(site_id)
            if site == site_id and project == project_id:
                if lut['InstitutionName'][row] not in self.lookup_dict:
                    self.lookup_dict[lut['InstitutionName'][row]] = {}
                if lut['SeriesDescription'][row] in self.lookup_dict[lut['InstitutionName'][row]]:
                    raise ValueError(
                        'Series description (%s) already exists for site (%04d) and institution name (%s)' %
                        (lut['SeriesDescription'][row], int(site_id), lut['InstitutionName'][row]))
                self.lookup_dict[lut['InstitutionName'][row]][lut['SeriesDescription'][row]] = \
                    lut['OutputFilename'][row]

    def __repr_json__(self):
        return self.__dict__

    def check(self, inst_name, series_desc):
        if inst_name in self.lookup_dict:
            if series_desc in self.lookup_dict[inst_name]:
                if self.lookup_dict[inst_name][series_desc] == 'None':
                    return False
                return self.lookup_dict[inst_name][series_desc].split('-')
        return None
