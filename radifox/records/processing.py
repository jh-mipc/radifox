from abc import ABC, abstractmethod
import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

from .utils import safe_append_to_file
from ..conversion import hash_file, create_loggers
from ..naming import ImageFile
from ..qa import create_qa_image


class ProcessingModule(ABC):
    name: str = None
    version: str = None
    log_uses_filename: bool = True

    def __init__(self, args: list[str] | None = None) -> None:
        self.verify_container()
        self.cli_call = " ".join(sys.argv[1:] if args is None else args)
        self.parsed_args = self.cli(args)
        if self.parsed_args is None:  # CLI call returned None, so we're done
            return
        self.create_loggers()
        try:
            logging.info(f"Beginning processing using: {self.name} v{self.version}.")
            logging.info(f"Command: {self.cli_call}")
            self.outputs = self.run(**self.parsed_args)
            logging.info(f"Generating QA imagees.")
            self.generate_qa_images()
            logging.info(f"Generating provenance records.")
            self.generate_prov()
            logging.info(f"Processing complete.")
        except Exception as e:
            logging.error(f"An error occurred during processing: {e}.", exc_info=True)
            raise

    @staticmethod
    @abstractmethod
    def cli(args: list[str] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def run(*args, **kwargs) -> dict[str, Path] | list[dict[str, Path]]:
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
            if any(lbl not in labels for lbl in ["ci.image", "ci.tag", "ci.commit", "ci.digest"]):
                raise ValueError("Container is missing required labels.")
        else:
            raise ValueError("Container labels not found. Running outside of container?")

    def create_prov(self, args: dict[str], outputs: dict[str, Path | list[Path]]) -> str:
        lbls = self.get_container_labels()
        user = os.environ["USER"] if "USER" in os.environ else Path(os.environ["HOME"]).name
        prov_str = (
            f"Module: {self.name}:{self.version}\n"
            f"Container: {lbls['ci.image']}:{lbls['ci.tag']} ({lbls['ci.commit']}) "
            f"{lbls['ci.digest']}\n"
            f"User: {user}\n"
            f"TimeStamp: {datetime.datetime.utcnow().isoformat()}\n"
            f"Inputs: \n"
        )
        inputs = {
            k: v
            for k, v in args.items()
            if isinstance(v, (Path, ImageFile))
            or (isinstance(v, list) and isinstance(v[0], (Path, ImageFile)))
        }
        if len(inputs) > 0:
            for k, v in inputs.items():
                v_list = v if isinstance(v, list) else [v]
                for item in v_list:
                    prov_str += (
                        f"  - {k}:{str(item)}:sha256:{hash_file(item, include_names=False)}\n"
                    )
        prov_str += f"Outputs: \n"
        if len(outputs) > 0:
            for k, v in outputs.items():
                v_list = v if isinstance(v, list) else [v]
                for item in v_list:
                    prov_str += (
                        f"  - {k}:{str(item)}:sha256:{hash_file(item, include_names=False)}\n"
                    )
        params = {k: v for k, v in args.items() if k not in inputs}
        prov_str += f"Parameters: \n"
        if len(params) > 0:
            for k, v in params.items():
                v_list = v if isinstance(v, list) else [v]
                for item in v_list:
                    prov_str += f"  - {k}:{str(item)}\n"
        prov_str += f"Command: {self.cli_call}\n"
        hashobj = hashlib.sha256()
        hashobj.update(prov_str.encode("utf-8"))
        prov_str = f"Id: {hashobj.hexdigest()}\n" + prov_str + f"---\n"
        return prov_str

    @staticmethod
    def write_prov(prov_str: str, outputs: dict[str, Path | list[Path]]) -> None:
        outs = []
        for out in outputs.values():
            outs.extend(out if isinstance(out, list) else [out])
        for j, output in enumerate(outs):
            if j == 0:
                session_dir = output.parent.parent
                session_file = "_".join(
                    [session_dir.parent.name, session_dir.name, "Provenance.txt"]
                )
                safe_append_to_file(session_dir / session_file, prov_str)
            suffix = "".join(output.suffixes)
            prov_path = output.parent / output.name.replace(suffix, ".prov")
            with open(prov_path, "w") as f:
                f.write(prov_str)

    def check_multi_inputs(self) -> bool:
        return all(
            isinstance(arg, list) and len(arg) == len(list(self.parsed_args.values())[0])
            for arg in self.parsed_args.values()
        )

    def check_multi_run(self) -> bool:
        return self.check_multi_inputs() and len(self.outputs) == len(
            list(self.parsed_args.values())[0]
        )

    def generate_prov(self) -> None:
        if self.check_multi_run():
            for i in range(len(list(self.parsed_args.values())[0])):
                prov_str = self.create_prov(
                    {k: v[i] for k, v in self.parsed_args.items()},
                    self.outputs[i],
                )
                self.write_prov(prov_str, self.outputs[i])
        else:
            prov_str = self.create_prov(self.parsed_args, self.outputs)
            self.write_prov(prov_str, self.outputs)

    @staticmethod
    def create_qa(outputs: dict[str, Path | list[Path]], name: str) -> None:
        outs = []
        for out in outputs.values():
            outs.extend(out if isinstance(out, list) else [out])
        out_dir = outs[0].parent.parent / "qa" / name
        out_dir.mkdir(exist_ok=True, parents=True)
        for out in outs:
            if not str(out).endswith(".nii.gz"):
                continue
            create_qa_image(str(out), out_dir / f"{out.name.split('.')[0]}.png")

    def generate_qa_images(self) -> None:
        if self.check_multi_run():
            for i in range(len(list(self.parsed_args.values())[0])):
                self.create_qa(self.outputs[i], self.name)
        else:
            self.create_qa(self.outputs, self.name)

    def create_loggers(self):
        out_paths = None
        if self.check_multi_inputs():
            for arg_list in self.parsed_args.values():
                if isinstance(arg_list[0], (Path, ImageFile)):
                    out_paths = arg_list
                    break
                elif isinstance(arg_list[0], list) and isinstance(
                    arg_list[0][0], (Path, ImageFile)
                ):
                    out_paths = [item[0] for item in arg_list]
                    break
        else:
            for arg in self.parsed_args.values():
                if isinstance(arg, (Path, ImageFile)):
                    out_paths = [arg]
                    break
        if out_paths is None:
            raise ValueError("Could not find any Path or ImageFile inputs.")
        for i, out_path in enumerate(out_paths):
            if self.log_uses_filename:
                log_dir = out_path.parent.parent / "logs" / self.name
                log_filename = out_path.name.split(".")[0]
            else:
                log_dir = out_path.parent.parent / "logs"
                log_filename = self.name
            create_loggers(log_dir, log_filename, add_stream_handler=i == 0)


