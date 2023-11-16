from pathlib import Path
from typing import Union, List, Optional

from .utils import read_csv, is_intstr, hash_value


class LookupTable:
    def __init__(self, lut_file: Path, project_id: str, site_id: str) -> None:
        filename = lut_file.resolve().expanduser()
        lut = read_csv(filename)
        if site_id is None:
            site_id = "NONE"
        self.LookupDict = {}
        for row, (project, site) in enumerate(zip(lut["Project"], lut["Site"])):
            site_name = "NONE" if site.upper() == "NONE" else site
            if is_intstr(site_name) and is_intstr(site_id):
                site_name = str(int(site_name))
                site_id = str(int(site_id))
            if site_name == site_id and project == project_id:
                inst_name = (
                    "NONE"
                    if lut["InstitutionName"][row].upper() == "NONE"
                    else lut["InstitutionName"][row]
                )
                if inst_name not in self.LookupDict:
                    self.LookupDict[inst_name] = {}
                if lut["SeriesDescription"][row] in self.LookupDict[inst_name]:
                    raise ValueError(
                        "Series description (%s) already exists for site (%s) and institution name (%s)"
                        % (lut["SeriesDescription"][row], site_id, inst_name)
                    )
                self.LookupDict[inst_name][lut["SeriesDescription"][row]] = lut["OutputFilename"][
                    row
                ]

    def __repr_json__(self) -> dict:
        return self.__dict__

    def anonymize(self):
        old_inst_names = []
        for inst_name in self.LookupDict:
            if inst_name.upper() != "NONE":
                self.LookupDict[hash_value(inst_name)] = self.LookupDict[inst_name]
                old_inst_names.append(inst_name)
        for key in old_inst_names:
            del self.LookupDict[key]

    def check(self, inst_name: str, series_desc: str) -> Union[List[Optional[str]], bool]:
        # Deal with extras from PARRECs
        if series_desc.startswith("WIP "):
            series_desc = series_desc[4:]
        if series_desc.endswith(" CLEAR") or series_desc.endswith(" SENSE"):
            series_desc = series_desc[:-6]
        for item in [inst_name, "NONE"]:
            if item in self.LookupDict:
                if series_desc in self.LookupDict[item]:
                    if self.LookupDict[item][series_desc].upper() == "FALSE":
                        return False
                    lookup_arr = self.LookupDict[item][series_desc].split("-")
                    if len(lookup_arr) < 6:
                        lookup_arr += ["None"] * (6 - len(lookup_arr))
                    return [None if item.upper() == "NONE" else item for item in lookup_arr]
        return [None] * 6
