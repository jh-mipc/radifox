import argparse
import os

from gunicorn.app.wsgiapp import WSGIApplication


class StandaloneApplication(WSGIApplication):
    def __init__(self, app_uri, options=None):
        self.options = options or {}
        self.app_uri = app_uri
        super().__init__()

    def load_config(self):
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)


def run(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default="5000")
    parser.add_argument("--root-directory")
    parser.add_argument("--secret-key")
    parser.add_argument("--workers", type=int, default=1)
    parsed = parser.parse_args(args)

    os.environ["QA_HOST"] = parsed.host
    os.environ["QA_PORT"] = parsed.port
    if parsed.root_directory is not None:
        os.environ["QA_DATA_DIR"] = parsed.root_directory
    if parsed.secret_key is not None:
        os.environ["QA_SECRET_KEY"] = parsed.secret_key

    options = {
        "bind": "%s:%s" % (parsed.host, parsed.port),
        "workers": parsed.workers,
    }
    StandaloneApplication("radifox.qa.app:app", options).run()
