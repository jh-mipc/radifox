#!/usr/bin/env python
from __future__ import annotations
from abc import ABC, abstractmethod
import argparse
from collections import defaultdict
import importlib.util
import inspect
import logging
from pathlib import Path

import nibabel as nib
import numpy as np
from .._version import __version__
from ..naming import ImageFile, ImageFilter, glob
from ..records import ProcessingModule

__all__ = ["Staging", "StagingPlugin"]


class Staging(ProcessingModule):
    name = "staging"
    version = __version__
    log_uses_filename = False
    skip_prov_write = ("session_target", "subject_target")

    @staticmethod
    def cli(args=None):
        parser = argparse.ArgumentParser()
        parser.add_argument("-s", "--subject-dir", type=Path, required=True)
        parser.add_argument("--image-types", type=str, nargs="+", required=True)
        parser.add_argument("--reg-filters", type=str, nargs="+", default=None)
        parser.add_argument("--keep-best-res", action="store_true", default=False)
        parser.add_argument("--update", action="store_true", default=False)
        parser.add_argument("--plugin-paths", type=Path, nargs="+", default=None)
        parser.add_argument("--skip-default-plugins", action="store_true", default=False)
        parser.add_argument("--skip-set-sform", action="store_true", default=False)
        parsed = parser.parse_args(args)

        parsed.subject_dir = parsed.subject_dir.resolve()
        if not parsed.subject_dir.is_dir():
            parser.error(f"Subject directory ({parsed.subject_dir}) does not exist.")

        parsed.image_types = [
            ImageFilter.from_string(filter_str) for filter_str in parsed.image_types
        ]

        if parsed.plugin_paths is not None:
            parsed.plugin_paths = [p.resolve() for p in parsed.plugin_paths]
            for plugin_path in parsed.plugin_paths:
                if not plugin_path.is_file():
                    parser.error(f"Plugin file ({plugin_path}) does not exist.")

        if parsed.reg_filters is not None:
            parsed.reg_filters = [
                ImageFilter.from_string(filter_str) for filter_str in parsed.reg_filters
            ]
            for reg_filter in parsed.reg_filters:
                if reg_filter.acqdim is None:
                    parser.error(
                        f"Registration filters must provide an 'acqdim' filter."
                        f"{str(reg_filter)} was provided."
                    )

        session_imgs = {}
        subject_target = None
        for session in sorted(parsed.subject_dir.iterdir()):
            # Skip non-directories (if they exist)
            if not session.is_dir():
                continue
            # Return an error if the session has already been staged
            # If we are updating, skip sessions that already have staged images
            if (session / "stage").exists():
                if parsed.update:
                    subject_target = ImageFile((session / "stage" / "subject-target").resolve())
                    continue
                else:
                    parser.error('Session has already been staged. Use "--update" to skip existing.')
            # Get all images in session "nii" directory, sort by reverse name and skip "ND"
            all_imgs = glob(session / "nii" / "*.nii.gz")
            all_imgs = sorted(all_imgs, key=lambda x: x.name, reverse=True)
            all_imgs = [img for img in all_imgs if "ND" not in img.extras]
            if all_imgs:
                session_imgs[session] = all_imgs

        if len(session_imgs) == 0:
            parser.error("No images found for this subject.")

        if parsed.update and (subject_target is None or not subject_target.path.exists()):
            parser.error("No subject target found for updating.")

        return {
            "session_filepaths": list(session_imgs.values()),
            "image_types": [parsed.image_types] * len(session_imgs),
            "keep_best_res": [parsed.keep_best_res] * len(session_imgs),
            "reg_filters": [parsed.reg_filters] * len(session_imgs),
            "plugin_paths": [parsed.plugin_paths] * len(session_imgs),
            "skip_default_plugins": [parsed.skip_default_plugins] * len(session_imgs),
            "skip_set_sform": [parsed.skip_set_sform] * len(session_imgs),
            "subject_target": [subject_target] * len(session_imgs),
        }

    @staticmethod
    def run(
        session_filepaths: list[list[ImageFile]],
        image_types: list[list[ImageFilter]],
        keep_best_res: list[bool],
        plugin_paths: list[list[Path]],
        reg_filters: list[list[ImageFilter] | None],
        skip_default_plugins: list[bool],
        skip_set_sform: list[bool],
        subject_target: list[Path | None],
    ):
        # For each session, find images that match the contrast filters
        session_imgs = {}
        for (
            all_imgs,
            img_filters,
            best_res,
            proc_plugin_paths,
            skip_defaults,
            skip_set_sform_qform,
        ) in zip(
            session_filepaths,
            image_types,
            keep_best_res,
            plugin_paths,
            skip_default_plugins,
            skip_set_sform,
        ):
            if not all_imgs:
                continue
            # Create "stage" directory
            session = all_imgs[0].parent.parent
            (session / "stage").mkdir(exist_ok=True, parents=True)

            # Filter images by image filters
            filtered_imgs = []
            for img_filter in img_filters:
                # Get a list of images that match the filter (continue if none)
                imgs = img_filter.filter(all_imgs)
                if not imgs:
                    continue

                # Load plugins
                proc_plugins = []
                if proc_plugin_paths is not None:
                    for plugin_path in proc_plugin_paths:
                        proc_plugins.extend(load_plugins(plugin_path))
                if not skip_defaults:
                    proc_plugins.extend([MEMPRAGEPlugin, MP2RAGEPlugin])

                for plugin in proc_plugins:
                    plugin_imgs = plugin.filter(imgs)
                    other_imgs = [img for img in imgs if img not in plugin_imgs]
                    out_imgs = plugin.run(plugin_imgs)
                    imgs = out_imgs + other_imgs

                # Keep only the best resolution image from each contrast (if needed)
                if best_res:
                    # Get existing images in "stage" directory
                    stage_imgs = [img for img in imgs if img.parent.name == "stage"]
                    # If there is are 3D images, pick the one that is the "most isotropic"
                    imgs_3d = ImageFilter(acqdim="3D").filter(imgs)
                    if imgs_3d:
                        # Select the image with the lowest anisotropy
                        imgs = [pick_most_isotropic(imgs_3d)]
                    else:
                        # Sort images by slice spacing and/or slice thickness (select first)
                        imgs = [pick_smallest_slices(imgs)]
                    # Remove staged images that are not the best resolution
                    for img in stage_imgs:
                        if img not in imgs:
                            logging.warning(
                                f"Removing staged {img} because it is not the best image."
                            )
                            # img.path.unlink()
                # Add image(s) to filtered image list
                filtered_imgs.extend(imgs)
            if not skip_set_sform_qform:
                # Fix sform/qform of filtered images
                filtered_imgs = [fix_sform_qform(img) for img in filtered_imgs]

            # Remove staged images that are not in the filtered image list
            for stage_img in (session / "stage").iterdir():
                if stage_img.name not in [img.name for img in filtered_imgs]:
                    stage_img.unlink()

            if not filtered_imgs:
                logging.warning(f"No matching images found for {session}. Skipping.")
                (session / "stage").rmdir()
                session_imgs[session] = None
                continue
            else:
                session_imgs[session] = filtered_imgs

        reg_filters = reg_filters[0]
        if reg_filters is None:
            # No registration targets
            logging.info("No registration targets provided. Skipping.")
            session_targets = {session: None for session in session_imgs}
            subject_target = None
        else:
            # Subject targets are chosen over all sessions (first for tie)
            # Session targets are chosen over all images in each session
            # Ties in priority are resolved by resolution:
            # 1. For 3D images, most isotropic
            # 2. For 2D images, thinnest slice spacing
            # Find session targets
            session_targets: dict[Path, ImageFile] = {}
            for session, imgs in session_imgs.items():
                if imgs is None:
                    continue
                for reg_filter in reg_filters:
                    # Currenly use private _filter_dict to check acqdim
                    # Radifox should be updated to expose these parameters readonly
                    best_func = (
                        pick_most_isotropic if reg_filter.acqdim == "3D" else pick_smallest_slices
                    )
                    filtered = reg_filter.filter(imgs)
                    if filtered:
                        session_targets[session] = best_func(filtered)
                        break

            # Find subject target
            subject_target = subject_target[0]
            if subject_target is None:
                for img_filter in reg_filters:
                    filtered = img_filter.filter(list(session_targets.values()))
                    if filtered:
                        subject_target = filtered[0]
                        break

            # Symlink target images
            for session, img in session_targets.items():
                (session / "stage" / "session-target").symlink_to(
                    Path("..", img.path.relative_to(session))
                )
                (session / "stage" / "subject-target").symlink_to(
                    Path("..", "..", subject_target.path.relative_to(session.parent))
                )

            for session, imgs in session_imgs.items():
                if imgs is None:
                    continue
                logging.info("---")
                logging.info(session)
                logging.info("---")
                for img in imgs:
                    logging.info(f"{str(img.path)}")
            if subject_target is not None:
                logging.info("---")
                logging.info("Registration Targets")
                logging.info("---")
                logging.info(subject_target.path)
                for session, img in session_targets.items():
                    logging.info(f"{session}: {str(img.path)}")

        return [
            {
                "staged_files": imgs,
                "session_target": session_targets[session] if session in session_targets else None,
                "subject_target": subject_target if session in session_targets else None,
            }
            if imgs is not None else None
            for session, imgs in session_imgs.items()
        ]


def fix_sform_qform(img: ImageFile) -> ImageFile:
    """Conform the qform/sform matrix of an image header."""
    out_fpath = img.parent.parent / "stage" / f"{img.stem}_hdrfix.nii.gz"
    obj = nib.Nifti1Image.load(img.path)
    obj.set_qform(obj.get_sform(), 2)
    obj.set_sform(obj.get_qform(), 1)
    obj.to_filename(out_fpath)
    return ImageFile(out_fpath)


def pick_most_isotropic(imgs: list[ImageFile]) -> ImageFile:
    """Pick the most isotropic image from a list of images."""
    # Return first image if only one image
    if len(imgs) == 1:
        return imgs[0]
    # Calculate aniontropy for each 3D image
    aniso = [
        np.abs(1 - (np.mean(img.info.AcquiredResolution) / img.info.SliceThickness)) for img in imgs
    ]
    # Select the image with the lowest anisotropy
    return imgs[np.argmin(aniso)]


def pick_smallest_slices(imgs: list[ImageFile]) -> ImageFile:
    """Pick the image with the smallest slice spacing from a list of images."""
    # Return first image if only one image
    if len(imgs) == 1:
        return imgs[0]
    # Get slice spacing for each image, sort, and pick first
    return sorted(
        imgs,
        key=lambda x: x.info.SliceThickness if x.info.SliceSpacing is None else x.info.SliceSpacing,
    )[0]


def load_plugins(plugin_path: Path) -> list[StagingPlugin]:
    """Load plugins from a plugin file."""
    # Get the module name from the plugin file name
    spec = importlib.util.spec_from_file_location(plugin_path.stem, plugin_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Inspect the module and find all subclasses of the specified base class
    return [
        member
        for name, member in inspect.getmembers(module, inspect.isclass)
        if issubclass(member, StagingPlugin) and member is not StagingPlugin
    ]


class StagingPlugin(ABC):
    @staticmethod
    @abstractmethod
    def filter(images: list[ImageFile]) -> list[ImageFile]:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def run(images: list[ImageFile]) -> list[ImageFile]:
        raise NotImplementedError

    @staticmethod
    def sort_by_series(imgs: list[ImageFile]) -> list[list[ImageFile]]:
        """Sort images by series ID and return a list of images for each series ID."""
        series_dict = {}
        for img in imgs:
            if img.series_id not in series_dict:
                series_dict[img.series_id] = []
            series_dict[img.series_id].append(img)
        return list(series_dict.values())


class MEMPRAGEPlugin(StagingPlugin):
    @staticmethod
    def filter(images: list[ImageFile]) -> list[ImageFile]:
        return ImageFilter(
            modality="T1",
            technique="IRFSPGR",
            extras=lambda x: any("ECHO" in s or s == "SUM" for s in x),
        ).filter(images)

    @staticmethod
    def run(images: list[ImageFile]) -> list[ImageFile]:
        out_imgs = []
        for img_set in MEMPRAGEPlugin.sort_by_series(images):
            # Choose a SUM image if both echoes and SUM are available
            sum_imgs = [img for img in img_set if "SUM" in img.extras]
            if sum_imgs:
                out_imgs.append(sum_imgs[0])
            else:
                out_imgs.append(MEMPRAGEPlugin.sum_memprage(img_set))
        return out_imgs

    @staticmethod
    def sum_memprage(imgs: list[ImageFile]) -> ImageFile:
        """Create a sum image from a list of MEMPRAGE echo images."""
        temp_img = sorted(imgs, key=lambda x: x.name)[0]
        out_fpath = temp_img.path.parent.parent / "stage" / f"{temp_img.stem}_sum.nii.gz"
        obj = nib.load(temp_img.path)
        sum_data = np.sum(
            [nib.Nifti1Image.load(img.path).get_fdata(dtype=np.float32) for img in imgs], axis=0
        )
        nib.Nifti1Image(sum_data, None, obj.header).to_filename(out_fpath)
        return ImageFile(out_fpath)


class MP2RAGEPlugin(StagingPlugin):
    CMPLX_IMG_TYPES = ("MAG", "PHA", "REA", "IMA")

    @staticmethod
    def filter(images: list[ImageFile]) -> list[ImageFile]:
        return ImageFilter(
            modality="T1",
            technique="IRFSPGR",
            extras=lambda x: any("INV" in s for s in x),
        ).filter(images)

    @staticmethod
    def run(images: list[ImageFile]) -> list[ImageFile]:
        out_imgs = []
        for img_set in MP2RAGEPlugin.sort_by_series(images):
            out_imgs.append(MP2RAGEPlugin.create_uniden(img_set))
        return out_imgs

    @staticmethod
    def create_uniden(imgs: list[ImageFile], gamma: float = 1e9) -> ImageFile:
        """Create an UNIDEN (denoised uniform) image from the MP2RAGE complex component images."""
        img_dict = defaultdict(list)
        for img in imgs:
            inv = next(ex for ex in img.extras if "INV" in ex)
            cmplx_type = next(
                (ct for ct in MP2RAGEPlugin.CMPLX_IMG_TYPES if ct in img.extras), "MAG"
            )
            img_dict[f"{inv}-{cmplx_type}"].append(img)
        data = {
            key: nib.Nifti1Image.load(img_dict[key][0].path).get_fdata(dtype=np.float32)
            for key in img_dict
        }
        if all(len(img_dict[f"INV{i}-{comp}"]) == 1 for i in (1, 2) for comp in ["REA", "IMA"]):
            temp_img = img_dict["INV1-REA"][0]
            for inv in ["INV1", "INV2"]:
                data[f"{inv}-CPX"] = data[f"{inv}-REA"] + data[f"{inv}-IMA"] * 1j
        elif all(len(img_dict[f"INV{i}-{comp}"]) == 1 for i in (1, 2) for comp in ["MAG", "PHA"]):
            temp_img = img_dict["INV1-MAG"][0]
            for inv in ["INV1", "INV2"]:
                data[f"{inv}-PHA"] = (
                    (data["INV1-PHA"] - data["INV1-PHA"].min())
                    / (data["INV1-PHA"].max() - data["INV1-PHA"].min())
                    * (2 * np.pi)
                )
                data[f"{inv}-CPX"] = data[f"{inv}-MAG"] * np.exp(data[f"{inv}-PHA"] * 1j)
        else:
            raise ValueError("Cannot create uniden image from provided images.")
        uniden = np.real(
            ((np.conjugate(data["INV1-CPX"]) * data["INV2-CPX"]) - gamma)
            / (np.abs(data["INV1-CPX"]) ** 2 + np.abs(data["INV2-CPX"]) ** 2 + 2 * gamma)
        )
        uniden = np.clip(uniden, -0.5, 0.5) + 0.5

        obj = nib.Nifti1Image.load(temp_img.path)
        out_fpath = temp_img.parent.parent / "stage" / f"{temp_img.stem}_uniden.nii.gz"
        nib.Nifti1Image(uniden, None, obj.header).to_filename(out_fpath)
        return ImageFile(out_fpath)


if __name__ == "__main__":
    Staging()
