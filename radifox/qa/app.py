import base64
import os
import json
from pathlib import Path

from flask import Flask, request, render_template, jsonify, send_from_directory

from ..conversion.json import JSONObjectEncoder, NoIndent

DATA_DIR = Path(os.environ.get("QA_DATA_DIR", "/data")).resolve()

app = Flask(__name__)


def encode_image(filepath):
    with filepath.open("rb") as fp:
        b64_str = base64.b64encode(fp.read())
    return b64_str


@app.route("/qa/")
def index():
    projects = sorted([proj.name for proj in DATA_DIR.glob("*") if proj.is_dir()])
    return render_template("index.html", projects=projects)


@app.route("/qa/<project_id>/")
def project(project_id):
    proj_dir = DATA_DIR / project_id
    subjects = sorted([pat.name for pat in proj_dir.glob("*") if pat.is_dir()])
    return render_template("project.html", project_id=project_id, subjects=subjects)


@app.route("/qa/<project_id>/<subject_id>/")
def subject(project_id, subject_id):
    pat_dir = DATA_DIR / project_id / subject_id
    sessions = sorted([session.name for session in pat_dir.glob("*")])
    return render_template(
        "subject.html", project_id=project_id, subject_id=subject_id, sessions=sessions
    )


@app.route("/qa/<project_id>/<subject_id>/<session_id>/")
def qa(project_id, subject_id, session_id):
    session_dir = DATA_DIR / project_id / subject_id / session_id
    subjects = sorted(
        [pat.name for pat in (DATA_DIR / project_id).glob(project_id.upper() + "*")]
    )
    pat_idx = subjects.index(subject_id)
    prev_subject = subjects[pat_idx - 1] if pat_idx > 0 else None
    next_subject = subjects[pat_idx + 1] if pat_idx < (len(subjects) - 1) else None
    sessions = sorted([session.name for session in (DATA_DIR / project_id / subject_id).glob("*")])
    session_idx = sessions.index(session_id)
    prev_session = sessions[session_idx - 1] if session_idx > 0 else None
    next_session = sessions[session_idx + 1] if session_idx < (len(sessions) - 1) else None
    json_files = (session_dir / "nii").glob("*.json")
    manual_json_path = (
        DATA_DIR
        / project_id
        / subject_id
        / session_id
        / "_".join([subject_id, session_id, "ManualNaming.json"])
    )
    manual_json = json.loads(manual_json_path.read_text()) if manual_json_path.exists() else {}
    images = []
    for jsonfile in json_files:
        si = json.loads(jsonfile.read_text())["SeriesInfo"]
        created_by = (
            "MANUAL"
            if any([item is not None for item in si["ManualName"]])
            else ("LOOKUP" if any([item is not None for item in si["LookupName"]]) else "PREDICTED")
        )
        manual_name = ""
        if si["SourcePath"] in manual_json:
            if manual_json[si["SourcePath"]] is False:
                created_by = "IGNORED"
            else:
                image_arr = si["NiftiName"].split("_")[-1].split("-")[:-1]
                manual_name = "/".join(
                    [item if item is not None else "--" for item in manual_json[si["SourcePath"]]]
                )
                if any(
                    [
                        j is not None and i != j
                        for i, j in zip(image_arr, manual_json[si["SourcePath"]])
                    ]
                ):
                    created_by = "MODIFIED"
        study_num, series_num = si["NiftiName"].split("_")[-2].split("-")
        image_obj = {
            "acq_date_time": si["AcqDateTime"],
            "series_number": series_num,
            "study_number": study_num,
            "acq_number": "%02d" % int(si["SeriesUID"].split(".")[-1]),
            "image_name": si["NiftiName"].split("_")[-1],
            "created_by": created_by,
            "institution_name": si["InstitutionName"],
            "manufacturer": si["Manufacturer"].upper(),
            "model": si["ScannerModelName"],
            "field_strength": si["MagneticFieldStrength"],
            "series_description": si["SeriesDescription"],
            "sequence_type": si["SequenceType"],
            "sequence_name": si["SequenceName"],
            "sequence_variant": si["SequenceVariant"],
            "scan_options": si["ScanOptions"],
            "acquired_resolution": (
                si["AcquiredResolution"] if si["AcquiredResolution"] is not None else [0, 0]
            ),
            "field_of_view": si["FieldOfView"] if si["FieldOfView"] is not None else [0, 0],
            "slice_thickness": si["SliceThickness"],
            "slice_spacing": si["SliceSpacing"],
            "num_slices": si["NumFiles"],
            "echo_time": si["EchoTime"],
            "repetition_time": si["RepetitionTime"],
            "inversion_time": si["InversionTime"],
            "flip_angle": si["FlipAngle"],
            "echo_train_length": si["EchoTrainLength"],
            "contrast_agent": si["ExContrastAgent"],
            "study_description": si["StudyDescription"],
            "body_part": si["BodyPartExamined"],
            "source_path": si["SourcePath"],
            "manual_name": manual_name,
        }
        img_path = session_dir / "qa" / "autoconv" / jsonfile.name.replace(".json", ".png")
        if img_path.exists():
            image_obj["image_src"] = img_path.name
        images.append(image_obj)
    return render_template(
        "session.html",
        images=sorted(
            images, key=lambda x: (x["study_number"], x["series_number"], x["acq_number"])
        ),
        project_id=project_id,
        subject_id=subject_id,
        session_id=session_id,
        next_session=next_session,
        prev_session=prev_session,
        prev_subject=prev_subject,
        next_subject=next_subject,
    )


def save_manual(json_obj, filepath):
    for key in json_obj:
        json_obj[key] = NoIndent(json_obj[key])

    filepath.write_text(json.dumps(json_obj, indent=4, sort_keys=True, cls=JSONObjectEncoder))
    filepath.chmod(0o660)


def add_manual_entry(project_id, subject_id, session_id, key, value):
    filepath = (
        DATA_DIR
        / project_id
        / subject_id
        / session_id
        / "_".join([subject_id, session_id, "ManualNaming.json"])
    )
    json_obj = json.loads(filepath.read_text()) if filepath.exists() else {}
    json_obj[key] = value
    save_manual(json_obj, filepath)


def update_manual_entry(project_id, subject_id, session_id, data):
    filepath = (
        DATA_DIR
        / project_id
        / subject_id
        / session_id
        / "_".join([subject_id, session_id, "ManualNaming.json"])
    )
    json_obj = json.loads(filepath.read_text()) if filepath.exists() else {}

    name_list = [
        data.get(key).upper()
        for key in ["body_part", "modality", "technique", "acq_dim", "orient", "ex_contrast"]
    ]
    name_list = [None if item.strip() == "" else item for item in name_list]

    existing = [False] * 6
    if data["source"] in json_obj and json_obj[data["source"]] is not False:
        existing = [item is not None for item in json_obj[data["source"]]]

    name_list = [
        None if (new == old and not exist) else new
        for new, old, exist in zip(name_list, data["original"].split("-"), existing)
    ]

    json_obj[data["source"]] = name_list

    save_manual(json_obj, filepath)


@app.route("/qa/manual-entry", methods=["POST"])
def manual_entry():
    data = request.form
    update_manual_entry(
        data["project"],
        data["subject"],
        data["session"],
        data,
    )
    return "Manual Name Added/Updated"


@app.route("/qa/ignore-entry", methods=["POST"])
def ignore_entry():
    data = request.form
    add_manual_entry(
        data["project"],
        data["subject"],
        data["session"],
        data["source"],
        False,
    )
    return "Image Ignored"


@app.route("/qa/ignore-btn", methods=["POST"])
def ignore_btn():
    data = request.get_json()
    add_manual_entry(
        data["project"],
        data["subject"],
        data["session"],
        data["source"],
        False,
    )
    return jsonify(message="Image Ignored")


@app.route("/qa/change-btn", methods=["POST"])
def change_btn():
    data = request.get_json()
    update_manual_entry(
        data["project"],
        data["subject"],
        data["session"],
        data,
    )
    return jsonify(message="Body Part Updated")


@app.route("/image/<project_id>/<subject_id>/<session_id>/<image_name>")
def image(project_id, subject_id, session_id, image_name):
    return send_from_directory(
        str(DATA_DIR / project_id / subject_id / session_id / "qa" / "autoconv"), image_name
    )
