from copy import deepcopy
from pathlib import Path
from string import Template
import secrets
from typing import List

import numpy as np
from nibabel.volumeutils import array_to_file
from nibabel.openers import ImageOpener

from .nib_parrec_fork import PARRECImage, PARRECHeader, PARRECArrayProxy, vol_numbers


def array_string_func(format_str, sep=" "):
    return lambda x: sep.join([format_str] * len(x)).format(
        *tuple(x.squeeze().tolist()) if len(x) > 1 else (x[0],)
    )


def numpy_str_replace():
    return lambda x: "{:s}".format((x if type(x) == str else x.decode("UTF-8")).replace(" ", "-"))


def gen_dict_strings(format_dict, value_dict_array):
    if isinstance(value_dict_array, np.record):
        value_dict_array = {k: v for k, v in zip(value_dict_array.dtype.names, value_dict_array)}
    return {
        k: func(value_dict_array.get(k, default))
        if callable(func)
        else func.format(value_dict_array.get(k, default))
        for k, (func, default) in format_dict.items()
    }


gen_info_types = {
    "patient_name": ("{:s}", ""),
    "exam_name": ("{:s}", ""),
    "protocol_name": ("{:s}", ""),
    "exam_date": ("{:s}", ""),
    "series_type": ("{:s}", ""),
    "acq_nr": ("{:d}", 0),
    "recon_nr": ("{:d}", 0),
    "scan_duration": ("{:.1f}", 0.0),
    "max_cardiac_phases": ("{:d}", 0),
    "max_echoes": ("{:d}", 0),
    "max_slices": ("{:d}", 0),
    "max_dynamics": ("{:d}", 0),
    "max_mixes": ("{:d}", 0),
    "patient_position": ("{:s}", ""),
    "prep_direction": ("{:s}", ""),
    "tech": ("{:s}", ""),
    "scan_resolution": (array_string_func("{:d}"), np.array([0.0, 0.0])),
    "scan_mode": ("{:s}", ""),
    "repetition_time": (array_string_func("{:.3f}"), np.array([0.0])),
    "fov": (array_string_func("{:.3f}"), np.array([0.0, 0.0, 0.0])),
    "water_fat_shift": ("{:.3f}", 0.0),
    "angulation": (array_string_func("{:.3f}"), np.array([0.0, 0.0, 0.0])),
    "off_center": (array_string_func("{:.3f}"), np.array([0.0, 0.0, 0.0])),
    "flow_compensation": ("{:d}", 0),
    "presaturation": ("{:d}", 0),
    "phase_enc_velocity": (array_string_func("{:.6f}"), np.array([0.0, 0.0, 0.0])),
    "mtc": ("{:d}", 0),
    "spir": ("{:d}", 0),
    "epi_factor": ("{:d}", 1),
    "dyn_scan": ("{:d}", 0),
    "diffusion": ("{:d}", 0),
    "diffusion_echo_time": ("{:.4f}", 0.0),
    "max_diffusion_values": ("{:d}", 1),
    "max_gradient_orient": ("{:d}", 1),
    "nr_label_types": ("{:d}", 0),
}

image_def_types = {
    "slice_number": ("{:d}", 0),
    "echo_number": ("{:d}", 0),
    "dynamic_scan_number": ("{:d}", 0),
    "cardiac_phase_number": ("{:d}", 0),
    "image_type_mr": ("{:d}", 0),
    "scanning_sequence": ("{:d}", 0),
    "index_in_rec_file": ("{:d}", 0),
    "image_pixel_size": ("{:d}", 0),
    "scan_percentage": ("{:d}", 0),
    "recon_resolution": (array_string_func("{:d}"), np.array([0, 0])),
    "rescale_intercept": ("{:.5f}", 0.0),
    "rescale_slope": ("{:.5f}", 0.0),
    "scale_slope": ("{:.5e}", 0.0),
    "window_center": (lambda x: "{:d}".format(int(x)), 0.0),
    "window_width": (lambda x: "{:d}".format(int(x)), 0.0),
    "image_angulation": (array_string_func("{:.2f}"), np.array([0.0, 0.0, 0.0])),
    "image_offcentre": (array_string_func("{:.2f}"), np.array([0.0, 0.0, 0.0])),
    "slice_thickness": ("{:.3f}", 0.0),
    "slice_gap": ("{:.3f}", 0.0),
    "image_display_orientation": ("{:d}", 0),
    "slice_orientation": ("{:d}", 0),
    "fmri_status_indication": ("{:d}", 0),
    "image_type_ed_es": ("{:d}", 0),
    "pixel_spacing": (array_string_func("{:.3f}"), np.array([0.0, 0.0])),
    "echo_time": ("{:.2f}", 0.0),
    "dyn_scan_begin_time": ("{:.2f}", 0.0),
    "trigger_time": ("{:.2f}", 0.0),
    "diffusion_b_factor": ("{:.2f}", 0.0),
    "number_of_averages": ("{:d}", 0),
    "image_flip_angle": ("{:.2f}", 0.0),
    "cardiac_frequency": ("{:d}", 0),
    "minimum_rr_interval": ("{:d}", 0),
    "maximum_rr_interval": ("{:d}", 0),
    "turbo_factor": ("{:d}", 0),
    "inversion_delay": ("{:.1f}", 0.0),
    "diffusion_b_value_number": ("{:d}", 0),
    "gradient_orientation_number": ("{:d}", 0),
    "contrast_type": ("{:d}", 0),
    "diffusion_anisotropy_type": ("{:d}", 0),
    "diffusion": (array_string_func("{:.3f}"), np.array([0.0, 0.0, 0.0])),
    "label_type": ("{:d}", 0),
    "contrast_bolus_agent": (numpy_str_replace(), ""),
    "contrast_bolus_route": (numpy_str_replace(), ""),
    "contrast_bolus_volume": ("{:.6f}", 0.0),
    "contrast_bolus_start_time": (numpy_str_replace(), ""),
    "contrast_bolus_total_dose": ("{:.6f}", 0.0),
    "contrast_bolus_ingredient": (numpy_str_replace(), ""),
    "contrast_bolus_ingredient_concentration": ("{:.6f}", 0.0),
}

parrec_templates = Path(__file__).parent / "parrec_templates"

top_header_template = Template((parrec_templates / "top_header.txt").read_text())
gen_info_template = Template((parrec_templates / "gen_info.txt").read_text())
image_def_template = Template("  ".join(["$" + k for k in image_def_types]) + "\n")


def generate_par_file(dataset_name: str, header: PARRECHeader, filename: Path) -> None:
    with filename.open("w") as fp:
        fp.write(top_header_template.substitute({"dataset_name": dataset_name}))
        fp.write(
            gen_info_template.substitute(gen_dict_strings(gen_info_types, header.general_info))
        )
        fp.write((parrec_templates / "pixel_values.txt").read_text())
        image_defs = header.image_defs.view(np.recarray)
        for i in range(len(image_defs)):
            fp.write(
                image_def_template.substitute(gen_dict_strings(image_def_types, image_defs[i]))
            )
        fp.write(
            "\n# === END OF DATA DESCRIPTION FILE ===============================================\n"
        )


def split_fix_parrec(in_filename: Path, study_uid, outdir) -> List[str]:
    file_map = PARRECImage.filespec_to_file_map(str(in_filename))
    with file_map["header"].get_prepare_fileobj("rt") as hdr_fobj:
        hdr = PARRECHeader.from_fileobj(hdr_fobj, permit_truncated=False, strict_sort=False)

    idefs = hdr.image_defs
    split_types = ["echo_number", "image_type_mr"]
    slice_vols = np.array(vol_numbers(idefs["slice_number"]))
    split_defs = set(zip(zip(*[idefs[def_name].tolist() for def_name in split_types]), slice_vols))
    split_vols = {}
    for split_def, vol_num in split_defs:
        if split_def not in split_vols:
            split_vols[split_def] = []
        split_vols[split_def].append(vol_num)

    series_uid = (
        study_uid
        + (".%02d.%02d." % (hdr.general_info["acq_nr"], hdr.general_info["recon_nr"]))
        + str(int(str(secrets.randbits(16))))
    )
    for i, vol_nums in enumerate(sorted(split_vols.values())):
        this_hdr = deepcopy(hdr)
        this_hdr.image_defs = idefs[np.in1d(slice_vols, vol_nums)]
        this_hdr.image_defs["echo_number"] = [1] * len(this_hdr.image_defs["echo_number"])
        generate_par_file(
            str(in_filename), this_hdr, outdir / (series_uid + (".%02d" % (i + 1)) + ".par")
        )
    if len(split_vols) == 1:
        Path(file_map["image"].filename).rename(outdir / (series_uid + ".01.rec"))
    else:
        rec_fobj = file_map["image"].get_prepare_fileobj()
        data = PARRECArrayProxy(rec_fobj, hdr).get_unscaled()
        for i, vol_nums in enumerate(sorted(split_vols.values())):
            with ImageOpener(
                outdir / (series_uid + (".%02d" % (i + 1)) + ".rec"), mode="wb"
            ) as fileobj:
                array_to_file(
                    data[..., np.in1d(range(data.shape[-1]), vol_nums)],
                    fileobj,
                    hdr.get_data_dtype(),
                    order="F",
                )

    return [series_uid + (".%02d" % (i + 1)) + ".par" for i in range(len(split_vols))] + [
        series_uid + (".%02d" % (i + 1)) + ".rec" for i in range(len(split_vols))
    ]
