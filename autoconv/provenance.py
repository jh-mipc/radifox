from abc import ABC, abstractmethod
import datetime
import json
import os
from pathlib import Path
from typing import Any

from .utils import hash_file


class ProcessingModule(ABC):
    name: str = None
    version: str = None

    def __init(self, args: list[str] | None = None) -> None:
        self.verify_container()
        self.cli_call = " ".join(args)
        self.parsed_args = self.cli(args)
        self.outputs = self.run(**self.parsed_args)
        self.write_prov()

    @staticmethod
    @abstractmethod
    def cli(args: list[str] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def run(*args, **kwargs) -> dict[str, Path]:
        raise NotImplementedError

    @staticmethod
    def get_container_labels() -> dict[str, str]:
        with open("/.singularity.d/labels.json", "r") as f:
            labels = json.load(f)
        return labels

    @staticmethod
    def verify_container() -> None:
        if Path("/.singularity.d/labels.json").exists():
            labels = ProcessingModule.get_container_labels()
            if any(lbl not in labels for lbl in ["image", "tag", "commit", "digest"]):
                raise ValueError("Container is missing required labels.")
        else:
            raise ValueError("Container labels not found. Running outside of container?")

    def create_prov(self) -> str:
        lbls = self.get_container_labels()
        prov_str = (
            f"Module: {self.name}:{self.version}\n"
            f"Container: {lbls['image']}:{lbls['tag']} ({lbls['commit']}) sha256:{lbls['digest']}\n"
            f"User: {os.environ['USER']}\n"
            f"TimeStamp: {datetime.datetime.utcnow().isoformat()}\n"
            f"Inputs: \n"
        )
        inputs = {k: v for k, v in self.parsed_args.items() if isinstance(v, Path)}
        if len(inputs) > 0:
            for k, v in inputs.items():
                prov_str += f"  - {k}:{v}:sha256:{hash_file(v, include_names=False)}\n"
        prov_str += f"Outputs: \n"
        if len(self.outputs) > 0:
            for k, v in self.outputs.items():
                prov_str += f"  - {k}:{v}:sha256:{hash_file(v, include_names=False)}\n"
        params = {k: v for k, v in self.parsed_args.items() if not isinstance(v, Path)}
        prov_str += f"Parameters: \n"
        if len(params) > 0:
            for k, v in params.items():
                prov_str += f"  - {k}:{v}\n"
        prov_str += f"Command: {self.cli_call}\n"
        prov_str += f"---\n"
        return prov_str

    def write_prov(self) -> None:
        prov_str = self.create_prov()
        for i, output in enumerate(self.outputs.values()):
            if i == 0:
                session_dir = output.parent.parent
                session_file = "_".join(
                    [session_dir.parent.name, session_dir.name, "_Provenance.txt"]
                )
                with open(session_dir / session_file, "a") as f:
                    f.write(prov_str)
            suffix = "".join(output.suffixes)
            prov_path = output.parent / output.name.replace(suffix, ".prov")
            with open(prov_path, "w") as f:
                f.write(prov_str)
