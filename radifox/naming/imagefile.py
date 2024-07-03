from __future__ import annotations

from functools import cached_property
from glob import iglob as standard_iglob
import json
import os
from pathlib import Path
from typing import Generator


class ImageFile:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path).resolve()
        self._info = None

    def open(self, mode: str = "r"):
        return self.path.open(mode)

    def __str__(self):
        return str(self.path)

    def __lt__(self, other):
        return self.path < other.path

    @property
    def info(self) -> ImageInfo:
        if self._info is None:
            if self.path.parent.name == "nii":
                self._info = ImageInfo(self.path.parent / self.path.name.replace(self.ext, ".json"))
            elif self.path.parent.name == "proc" or self.path.parent.name == "stage":
                self._info = ImageInfo(
                    self.path.parent.parent / "nii" / ("_".join(self._name_arr[:4]) + ".json")
                )
            else:
                raise ValueError(
                    f"ImageFile.info is not available for {self.path}. "
                    f"Check the parent folders."
                )
        return self._info

    @property
    def path(self) -> Path:
        return self._path

    def is_relative_to(self, other: Path | str) -> bool:
        return self.path.is_relative_to(other)

    def relative_to(self, other: Path | str) -> Path:
        return self.path.relative_to(other)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stem(self) -> str:
        return self.path.name.split(".")[0]

    @property
    def suffixes(self) -> list[str]:
        return self.path.suffixes

    @property
    def ext(self) -> str:
        return "".join(self.suffixes)

    @cached_property
    def _name_arr(self) -> list[str]:
        return self.name.split(".")[0].split("_")

    @property
    def parent(self) -> Path:
        return self.path.parent

    @property
    def subject_id(self) -> str:
        return self._name_arr[0]

    @property
    def session_id(self) -> str:
        return self._name_arr[1]

    @property
    def image_id(self) -> str:
        return self._name_arr[2]

    @property
    def series_id(self) -> str:
        return self.image_id.split("-")[0]

    @property
    def image_type(self) -> str:
        return self._name_arr[3]

    @cached_property
    def _image_type_arr(self) -> list[str]:
        return self._name_arr[3].split("-")

    @property
    def bodypart(self) -> str:
        return self._image_type_arr[0]

    @property
    def modality(self) -> str:
        return self._image_type_arr[1]

    @property
    def technique(self) -> str:
        return self._image_type_arr[2]

    @property
    def acqdim(self) -> str:
        return self._image_type_arr[3]

    @property
    def orientation(self) -> str:
        return self._image_type_arr[4]

    @property
    def excontrast(self) -> str:
        return self._image_type_arr[5]

    @property
    def extras(self) -> list[str]:
        if len(self._image_type_arr) < 7:
            return []
        return self._image_type_arr[6:]

    @property
    def tags(self) -> list[str]:
        if len(self._name_arr) < 5:
            return []
        return self._name_arr[4:]


class ImageInfo:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path).resolve()
        self._info = json.loads(self._path.read_text())["SeriesInfo"]

    def __getattr__(self, item):
        if item in self._info:
            return self._info[item]
        item = "".join([i.title() for i in item.split("_")])
        if item in self._info:
            return self._info[item]
        raise AttributeError(f"No attribute {item} found.")


class ImageFilter:
    allowed_keys = (
        "bodypart",
        "modality",
        "technique",
        "acqdim",
        "orientation",
        "excontrast",
        "extras",
        "tags",
    )

    def __init__(self, **kwargs):
        for key in kwargs.keys():
            if key not in self.allowed_keys:
                raise ValueError(
                    f"Invalid key provided {key}. Allowed keys are: {', '.join(self.allowed_keys)}\n"
                    f"Keys provided: {', '.join(kwargs.keys())}"
                )
        self._filter_dict = kwargs

    def __str__(self):
        return ";".join([f"{key}={str(value)}" for key, value in self._filter_dict.items()])

    def __getattr__(self, item):
        if item in self.allowed_keys:
            return self._filter_dict.get(item)
        raise AttributeError(
            f"Invalid key provided {item}. "
            f"Allowed keys are: {', '.join(self.allowed_keys)}"
        )

    @classmethod
    def from_string(cls, filter_str) -> ImageFilter:
        filter_dict = dict([item.split("=") for item in filter_str.split(";")])
        for key, value in filter_dict.items():
            if key in ["extras", "tags"]:
                if value.upper() in ["NONE", "()", "[]"]:
                    filter_dict[key] = []
                else:
                    if value[0] in ["(", "["]:
                        value = value[1:]
                    if value[-1] in [")", "]"]:
                        value = value[:-1]
                    if key == "extras":
                        filter_dict[key] = [item.upper() for item in value.split(",")]
                    else:
                        filter_dict[key] = value.split(",")
            else:
                filter_dict[key] = value.upper()
        return cls(**filter_dict)

    def iterfilter(self, imgs: list[ImageFile]) -> Generator[ImageFile, None, None]:
        for img in imgs:
            if self.check(img):
                yield img

    def filter(self, imgs: list[ImageFile]) -> list[ImageFile]:
        return list(self.iterfilter(imgs))

    def check(self, img: ImageFile) -> bool:
        return all(
            [self.match_attr(getattr(img, key), value) for key, value in self._filter_dict.items()]
        )

    @staticmethod
    def match_attr(img_value, dict_value) -> bool:
        if isinstance(dict_value, list):
            return len(img_value) == len(dict_value) and all(
                x == y for x, y in zip(img_value, dict_value)
            )
        elif callable(dict_value):
            return dict_value(img_value)
        return img_value == dict_value


def iglob(path: str | os.PathLike[str], recursive: bool = False) -> list[ImageFile]:
    for p in standard_iglob(str(path), recursive=recursive):
        yield ImageFile(p)


def glob(path: str | os.PathLike[str], recursive: bool = False) -> list[ImageFile]:
    return list(iglob(path, recursive=recursive))
