from abc import ABC, abstractmethod
import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import sys
from typing import Any

import nibabel as nib

from .utils import safe_append_to_file, format_timedelta
from .hashing import hash_file
from .logging import create_loggers
from ..naming import ImageFile
from ..qa.create import create_qa_image, create_surface_qa_image

CONTAINER_LABELS = [
    "ci.image",
    "ci.tag",
    "ci.commit",
    "ci.builder",
    "ci.timestamp",
    "ci.digest",
]


class ProcessingModule(ABC):
    name: str = None
    version: str = None
    log_uses_filename: bool = True
    skip_prov_write: tuple[str] = tuple()

    def __init__(self, args: list[str] | None = None) -> None:
        self.verify_container()
        self.cli_call = " ".join(sys.argv[1:] if args is None else args)
        self.start_time = datetime.datetime.now()
        self.parsed_args = self.cli(args)
        if self.parsed_args is None:  # CLI call returned None, so we're done
            return
        self.create_loggers()
        try:
            logging.info(f"Beginning processing using: {self.name} v{self.version}.")
            logging.info(f"Command: {self.cli_call}")
            self.outputs = self.run(**self.parsed_args)
            if not self.check_outputs():
                logging.error(f"Processing failed. No outputs reported.")
                return
            logging.info(f"Generating QA images.")
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
            if any(lbl not in labels for lbl in CONTAINER_LABELS):
                raise ValueError("Container is missing required labels.")
        else:
            raise ValueError("Container labels not found. Running outside of container?")

    def check_outputs(self) -> bool:
        if self.outputs is None:
            return False
        if self.check_multi_inputs():
            return (
                isinstance(self.outputs, list)
                and len(self.outputs) > 0
                and all(isinstance(out, dict) or (out is None) for out in self.outputs)
            )
        else:
            return isinstance(self.outputs, dict) and len(self.outputs) > 0

    def create_prov(self, args: dict[str], outputs: dict[str, Path | list[Path]]) -> str:
        lbls = self.get_container_labels()
        project_root = [
            (el[0] if isinstance(el, tuple) else el)
            for sub in outputs.values()
            for el in (sub if isinstance(sub, list) else [sub])
        ][0].parent.parent.parent.parent
        user = os.environ["USER"] if "USER" in os.environ else Path(os.environ["HOME"]).name
        prov_str = (
            f"Module: {self.name}:{self.version}\n"
            f"Container: \n"
            f"  url: {lbls['ci.image']}:{lbls['ci.tag']}@{lbls['ci.commit'][:8]}\n"
            f"  hash: {lbls['ci.digest']}\n"
            f"  builder: {lbls['ci.builder']}\n"
            f"  timestamp: {lbls['ci.timestamp']}\n"
            f"User: {user}@{socket.getfqdn()}\n"
            f"StartTime: {self.start_time.isoformat(timespec='seconds')}\n"
            f"Duration: {format_timedelta(datetime.datetime.now() - self.start_time)}\n"
            f"ProjectRoot: {project_root}\n"
            f"Inputs: "
        )
        inputs = {
            k: v
            for k, v in args.items()
            if isinstance(v, (Path, ImageFile))
            or (isinstance(v, list) and isinstance(v[0], (Path, ImageFile)))
        }
        if len(inputs) > 0:
            prov_str += "\n"
            prov_str += self.get_prov_path_strs(inputs, project_root)
        else:
            prov_str += "None\n"
        prov_str += f"Outputs: \n"
        prov_str += self.get_prov_path_strs(outputs, project_root)
        params = {k: v for k, v in args.items() if k not in inputs}
        prov_str += f"Parameters: "
        if len(params) > 0:
            prov_str += "\n"
            for k, v in params.items():
                if isinstance(v, list):
                    prov_str += f"  {k}:\n"
                    for item in v:
                        prov_str += f"    - {str(item)}\n"
                else:
                    prov_str += f"  {k}: {str(v)}\n"
        else:
            prov_str += "None\n"
        prov_str += f"Command: {self.cli_call}\n"
        hashobj = hashlib.sha256()
        hashobj.update(prov_str.encode("utf-8"))
        prov_str = f"---\nId: {hashobj.hexdigest()}\n" + prov_str + f"...\n"
        return prov_str

    @staticmethod
    def get_prov_path_strs(path_dict: dict[str, Path | list[Path] | None], project_root: Path) -> str:
        prov_str = ""
        for k, v in path_dict.items():
            if v is None:
                prov_str += f"  {k}: None\n"
            elif isinstance(v, list):
                prov_str += f"  {k}:\n"
                for item in v:
                    val = item[0] if isinstance(item, tuple) else item
                    rel_path = (
                        val.relative_to(project_root) if val.is_relative_to(project_root) else val
                    )
                    prov_str += (
                        f"    - {str(rel_path)}:sha256:{hash_file(val, include_names=False)}\n"
                    )
            else:
                val = v[0] if isinstance(v, tuple) else v
                rel_path = (
                    val.relative_to(project_root) if val.is_relative_to(project_root) else val
                )
                prov_str += f"  {k}: {str(rel_path)}:sha256:{hash_file(val, include_names=False)}\n"
        return prov_str

    @staticmethod
    def write_prov(
        prov_str: str,
        outputs: dict[str, Path | list[Path] | None],
        skip_prov_write: tuple[str],
    ) -> None:
        outs = [
            (el[0] if isinstance(el, tuple) else el)
            for key, sub in outputs.items()
            if key not in skip_prov_write
            for el in (sub if isinstance(sub, list) else [sub])
        ]
        if len(outs) == 0:
            return
        first = True
        for output in outs:
            if output is None:
                continue
            if first:
                session_dir = output.parent.parent
                session_file = "_".join(
                    [session_dir.parent.name, session_dir.name, "Provenance.yml"]
                )
                safe_append_to_file(session_dir / session_file, prov_str)
                first = False
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
                if self.outputs[i] is not None:
                    prov_str = self.create_prov(
                        {k: v[i] for k, v in self.parsed_args.items()},
                        self.outputs[i],
                    )
                    self.write_prov(prov_str, self.outputs[i], self.skip_prov_write)
        else:
            prov_str = self.create_prov(self.parsed_args, self.outputs)
            self.write_prov(prov_str, self.outputs, self.skip_prov_write)

    @staticmethod
    def create_qa(
        outputs: dict[str, Path | list[Path] | None],
        name: str,
        skip_prov_write: tuple[str],
    ) -> None:
        outs = [
            el
            for key, sub in outputs.items()
            if key not in skip_prov_write
            for el in (sub if isinstance(sub, list) else [sub])
        ]
        if len(outs) == 0:
            return
        out = outs[0][0] if isinstance(outs[0], tuple) else outs[0]
        out_dir = out.parent.parent / "qa" / name
        out_dir.mkdir(exist_ok=True, parents=True)
        for out in outs:
            if out is None:
                continue
            if isinstance(out, tuple):
                overlay = out[0]
                bg_image = out[1]
                lut = out[2] if len(out) > 2 else "binary"
                out_name = f"{overlay.name.split('.')[0]}.png"
            else:
                overlay = None
                bg_image = out
                lut = "binary"
                out_name = f"{bg_image.name.split('.')[0]}.png"
            if not str(bg_image).endswith(".nii.gz"):
                continue
            if overlay is not None and overlay.name.endswith(".gii"):
                if len(nib.GiftiImage.load(overlay).agg_data('pointset')) == 0 \
                        or len(nib.GiftiImage.load(overlay).agg_data('triangle')) == 0:
                    continue
                create_surface_qa_image(
                    overlay,
                    bg_image,
                    out_dir / out_name,
                    color=lut,
                )
            else:
                create_qa_image(
                    str(bg_image),
                    out_dir / out_name,
                    str(overlay) if overlay is not None else None,
                    lut,
                )

    def generate_qa_images(self) -> None:
        if self.check_multi_run():
            for i in range(len(list(self.parsed_args.values())[0])):
                if self.outputs[i] is not None:
                    self.create_qa(self.outputs[i], self.name, self.skip_prov_write)
        else:
            self.create_qa(self.outputs, self.name, self.skip_prov_write)

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
