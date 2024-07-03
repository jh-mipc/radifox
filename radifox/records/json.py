import json
from pathlib import PurePath
from typing import Any, Union
import uuid


class NoIndent:
    def __init__(self, value: Any) -> None:
        self.value = value


class JSONObjectEncoder(json.JSONEncoder):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.kwargs = dict(kwargs)
        del self.kwargs["indent"]
        self._replacement_map = {}

    def default(self, o: Any) -> Union[str, dict]:
        if isinstance(o, NoIndent):
            key = uuid.uuid4().hex
            self._replacement_map[key] = json.dumps(o.value, **self.kwargs, cls=JSONObjectEncoder)
            return "@@%s@@" % (key,)
        elif isinstance(o, PurePath):
            return str(o)
        elif hasattr(o, "__repr_json__") and callable(o.__repr_json__):
            return o.__repr_json__()
        else:
            return super().default(o)

    def encode(self, o: Any) -> str:
        result = super().encode(o)
        for k, v in self._replacement_map.items():
            result = result.replace('"@@%s@@"' % (k,), v)
        return result
