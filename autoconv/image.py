from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Callable, Dict, List, Optional, Union


class ImageSeries:
    def __init__(self, filepath: Path):
        self.img_path = filepath
        self.json_path = filepath.parent / filepath.name.replace('.nii.gz', '.json')
        if not (self.img_path.exists() and self.json_path.exists()):
            raise ValueError('Both image and metadata file must exist for %s' % self.img_path)
        self._full_metadata = json.loads(self.json_path.read_text())
        self.patient_id, self.scan_id, self._series_id = self.img_path.name.split('.')[0].split('_')
        self.body_part, self.contrast, self.sequence, self.acq_dim, \
            self.orientation, self.ex_contrast, acq_num, *extras = self._series_id.split('-')
        self.acq_num = int(acq_num[3:])
        self.extras = self.parse_extras(extras)

    @property
    def series_info(self):
        return self._full_metadata['SeriesInfo']

    @staticmethod
    def parse_extras(extras):
        extra_dict = {}
        for extra in extras:
            if re.match(r'[A-z]*[0-9]+', extra):
                extra_dict[re.sub(r'[0-9]*', '', extra).lower()] = int(re.sub(r'[A-z]*', '', extra))
            else:
                extra_dict[extra.lower()] = True
        return extra_dict


class ScanSession:
    def __init__(self, images: Union[List[ImageSeries], List[Path]]):
        self.images = [ImageSeries(img) if isinstance(img, Path) else img for img in images]

    def meets_criteria(self, query: Query):
        return query(self.images)


class Criterion:
    def __init__(self, body_part: str = r'.*', contrast: str = r'.*', sequence: str = r'.*',
                 acq_dim: str = r'.*', orientation: str = r'.*', ex_contrast: str = r'.*',
                 extras: Optional[Dict[str, Union[bool, int]]] = None,
                 metadata: Optional[List[Callable]] = None):
        self.regex_checks = {'body_part': re.compile(body_part, re.IGNORECASE),
                             'contrast': re.compile(contrast, re.IGNORECASE),
                             'sequence': re.compile(sequence, re.IGNORECASE),
                             'acq_dim': re.compile(acq_dim, re.IGNORECASE),
                             'orientation': re.compile(orientation, re.IGNORECASE),
                             'ex_contrast': re.compile(ex_contrast, re.IGNORECASE)}
        self.extras = {} if extras is None else extras
        self.metadata = [] if metadata is None else metadata

    def __call__(self, images: Union[ImageSeries, List[ImageSeries]]) -> Optional[ImageSeries]:
        if isinstance(images, ImageSeries):
            images = [images]
        results = []
        for image in images:
            result = self.check(image)
            if result:
                results.append(result)
        return results if len(results) > 0 else None

    def check(self, image: ImageSeries) -> Optional[ImageSeries]:
        for key, regex in self.regex_checks.items():
            if regex.match(getattr(image, key)) is None:
                return None
        for key, value in self.extras:
            if image.extras.get(key.lower(), None) != value:
                return None
        for func in self.metadata:
            if not func(image.series_info):
                return None
        return image

    def __and__(self, other: Union[Criterion, Query]):
        return AndQuery(self, other)

    def __or__(self, other: Union[Criterion, Query]):
        return OrQuery(self, other)


class Query:
    def __init__(self, *criteria: Union[Query, Criterion]):
        self.criteria = criteria

    def __call__(self, images: List[ImageSeries]):
        raise NotImplementedError

    def __and__(self, other: Union[Criterion, Query]):
        return AndQuery(self, other)

    def __or__(self, other: Union[Criterion, Query]):
        return OrQuery(self, other)


class AndQuery(Query):
    def __call__(self, images: List[ImageSeries]) -> Optional[List[ImageSeries]]:
        results = []
        for criterion in self.criteria:
            result = criterion(images)
            if not result:
                return None
            results.extend(result if isinstance(result, list) else [result])
        return results


class OrQuery(Query):
    def __call__(self, images: List[ImageSeries]) -> Optional[ImageSeries]:
        for criterion in self.criteria:
            result = criterion(images)
            if result:
                return result
        return None
