import json
import uuid


class NoIndent:
    def __init__(self, value):
        self.value = value


class JSONObjectEncoder(json.JSONEncoder):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kwargs = dict(kwargs)
        del self.kwargs['indent']
        self._replacement_map = {}

    def default(self, o):
        if isinstance(o, NoIndent):
            key = uuid.uuid4().hex
            self._replacement_map[key] = json.dumps(o.value, **self.kwargs, cls=JSONObjectEncoder)
            return "@@%s@@" % (key,)
        elif hasattr(o, '__repr_json__') and callable(o.__repr_json__):
            return o.__repr_json__()
        else:
            return super().default(o)

    def encode(self, o):
        result = super().encode(o)
        for k, v in self._replacement_map.items():
            result = result.replace('"@@%s@@"' % (k,), v)
        return result
