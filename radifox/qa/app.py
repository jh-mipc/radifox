import os
import datetime
import itertools
import json
from collections import defaultdict
from pathlib import Path
import secrets

from flask import (
    Flask,
    request,
    render_template,
    jsonify,
    send_from_directory,
    url_for,
    session,
    redirect,
)
import yaml

from ..records.json import JSONObjectEncoder, NoIndent

DATA_DIR = Path(os.environ.get("QA_DATA_DIR", "/data")).resolve()
SECRET_KEY = os.environ.get("QA_SECRET_KEY", secrets.token_urlsafe())

app = Flask(__name__)
app.secret_key = secrets.token_hex()

with app.app_context():
    print(
        f"Access the QA Webapp Directly at: "
        f"http://{os.environ['QA_HOST']}:{os.environ['QA_PORT']}/login?key={SECRET_KEY}"
    )
    print(f"QA Data Directory: {DATA_DIR}")
    print(f"QA Secret Key: {SECRET_KEY}")


@app.before_request
def require_authentication():
    if session.get("qa_secret_key") != SECRET_KEY and request.endpoint != "login":
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        key = request.form["key"]
        user = request.form["user"]
    else:
        key = request.args.get("key", "")
        user = ""

    if key:
        if key == SECRET_KEY:
            if user:
                session["qa_user"] = user
                session["qa_secret_key"] = key
                return redirect(url_for("index"))
            else:
                error = "Please enter a username"
        else:
            error = "Invalid Key"
    return render_template("login.html", error=error, key=key, user=user)


@app.route("/")
def index():
    projects = sorted([proj.name for proj in DATA_DIR.glob("*") if proj.is_dir()])
    return render_template("index.html", projects=projects)


@app.route("/<project_id>/")
def project(project_id):
    proj_dir = DATA_DIR / project_id
    subjects = sorted(
        [
            pat.name
            for pat in proj_dir.glob("*")
            if pat.is_dir()
            if pat.is_dir() and not pat.name.startswith(".")
        ]
    )
    return render_template("project.html", project_id=project_id, subjects=subjects)


@app.route("/<project_id>/<subject_id>/")
def subject(project_id, subject_id):
    pat_dir = DATA_DIR / project_id / subject_id
    sessions = sorted(
        [
            session_path.name
            for session_path in pat_dir.glob("*")
            if session_path.is_dir() and not session_path.name.startswith(".")
        ]
    )
    return render_template(
        "subject.html", project_id=project_id, subject_id=subject_id, sessions=sessions
    )


@app.route("/set_mode/<mode>/")
def set_mode(mode):
    session["qa_mode"] = mode
    return redirect(request.referrer)


@app.route("/<project_id>/<subject_id>/<session_id>/")
def qa_page(project_id, subject_id, session_id):
    if session.get("qa_mode", "conversion") == "conversion":
        return conversion_qa(project_id, subject_id, session_id)
    else:
        return processing_qa(project_id, subject_id, session_id)


def conversion_qa(project_id, subject_id, session_id):
    # Get subject and session information
    session_dir = DATA_DIR / project_id / subject_id / session_id
    subjects = sorted(
        [
            pat.name
            for pat in (DATA_DIR / project_id).glob("*")
            if pat.is_dir() and not pat.name.startswith(".")
        ]
    )
    pat_idx = subjects.index(subject_id)
    prev_subject = subjects[pat_idx - 1] if pat_idx > 0 else None
    next_subject = subjects[pat_idx + 1] if pat_idx < (len(subjects) - 1) else None
    sessions = sorted(
        [
            session_path.name
            for session_path in (DATA_DIR / project_id / subject_id).glob("*")
            if session_path.is_dir() and not session_path.name.startswith(".")
        ]
    )
    session_idx = sessions.index(session_id)
    prev_session = sessions[session_idx - 1] if session_idx > 0 else None
    next_session = sessions[session_idx + 1] if session_idx < (len(sessions) - 1) else None

    # Get conversion information
    json_files = (session_dir / "nii").glob("*.json")
    manual_json_path = (
        DATA_DIR
        / project_id
        / subject_id
        / session_id
        / "_".join([subject_id, session_id, "ManualNaming.json"])
    )
    manual_json = json.loads(manual_json_path.read_text()) if manual_json_path.exists() else {}
    conversion_images = []
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
        elif created_by == "LOOKUP":
            manual_name = "/".join(
                [item if item is not None else "--" for item in si["LookupName"]]
            )
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
        img_path = session_dir / "qa" / "conversion" / jsonfile.name.replace(".json", ".png")
        if img_path.exists():
            image_obj["image_src"] = img_path.name
        conversion_images.append(image_obj)

    return render_template(
        "conversion.html",
        conversion_images=sorted(
            conversion_images,
            key=lambda x: (x["study_number"], x["series_number"], x["acq_number"]),
        ),
        project_id=project_id,
        subject_id=subject_id,
        session_id=session_id,
        next_session=next_session,
        prev_session=prev_session,
        prev_subject=prev_subject,
        next_subject=next_subject,
    )


NO_QA_SUFFIXES = (".mat",)


def processing_qa(project_id, subject_id, session_id):
    # Get subject and session information
    session_dir = DATA_DIR / project_id / subject_id / session_id
    subjects = sorted(
        [
            pat.name
            for pat in (DATA_DIR / project_id).glob("*")
            if pat.is_dir() and not pat.name.startswith(".")
        ]
    )
    pat_idx = subjects.index(subject_id)
    prev_subject = subjects[pat_idx - 1] if pat_idx > 0 else None
    next_subject = subjects[pat_idx + 1] if pat_idx < (len(subjects) - 1) else None
    sessions = sorted(
        [
            session_path.name
            for session_path in (DATA_DIR / project_id / subject_id).glob("*")
            if session_path.is_dir() and not session_path.name.startswith(".")
        ]
    )
    session_idx = sessions.index(session_id)
    prev_session = sessions[session_idx - 1] if session_idx > 0 else None
    next_session = sessions[session_idx + 1] if session_idx < (len(sessions) - 1) else None

    # Get processing information
    prov_files = list(
        itertools.chain(
            (session_dir / "stage").glob("*.prov"),
            (session_dir / "proc").glob("*.prov"),
        )
    )
    prov_objs = defaultdict(dict)
    for provfile in prov_files:
        prov_obj = yaml.safe_load(provfile.read_text())
        prov_objs[prov_obj["Module"]][prov_obj["Id"]] = prov_obj
    prov_objs = {
        k: v
        for k, v in sorted(
            prov_objs.items(), key=lambda x: min(value["StartTime"] for value in x[1].values())
        )
    }

    qa_filepath = (
            DATA_DIR
            / project_id
            / subject_id
            / session_id
            / "_".join([subject_id, session_id, "QA.yml"])
    )
    qa_data = yaml.safe_load_all(qa_filepath.read_text()) if qa_filepath.exists() else []
    qa_dict = {}
    for entry in qa_data:
        qa_dict[entry["file"]] = entry["status"]

    for module_str, provs in prov_objs.items():
        for idstr, prov_obj in provs.items():
            prov_obj["OutputQA"] = {}
            for key, val in prov_obj["Outputs"].items():
                prov_obj["OutputQA"][key] = {}
                if not isinstance(val, list):
                    val = [val]
                for v in val:
                    filestr = v.split(":")[0]
                    existing_qa = qa_dict.get(filestr, "")
                    filepath = session_dir.parent.parent / filestr
                    qa_path = (
                        filepath.parent.parent
                        / "qa"
                        / module_str.split(":")[0]
                        / (filepath.name.split('.')[0] + '.png')
                    )
                    if filestr.endswith(NO_QA_SUFFIXES) or not qa_path.exists():
                        continue
                    display_name = (
                        filestr.split("_")[2]
                        + "_"
                        + " / ".join(filestr.split(".")[0].split("_")[3:])
                    )
                    prov_obj["OutputQA"][key][filepath.name.split('.')[0]] = (
                        (
                            qa_path.parent.parent.parent.name,
                            qa_path.parent.name,
                            qa_path.name,
                            display_name,
                            existing_qa,
                        )
                        if qa_path.exists()
                        else None
                    )
                if len(prov_obj["OutputQA"][key]) == 0:
                    del prov_obj["OutputQA"][key]

    return render_template(
        "processing.html",
        processing_results=prov_objs,
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


def add_qa_entry(project_id, subject_id, session_id, key, value):
    filepath = (
        DATA_DIR
        / project_id
        / subject_id
        / session_id
        / "_".join([subject_id, session_id, "QA.yml"])
    )
    yml_obj = {
        "user": session["qa_user"],
        "timestamp": datetime.datetime.now().isoformat(),
        "file": key,
        "status": value,
    }
    with open(filepath, "a") as f:
        yaml.safe_dump(yml_obj, f, explicit_start=True, explicit_end=True, sort_keys=True)


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
        data.get(key, "").upper()
        for key in ["body_part", "modality", "technique", "acq_dim", "orient", "ex_contrast"]
    ]
    name_list = [None if item.strip() == "" else item for item in name_list]

    existing = [False] * 6
    if data["source"] in json_obj and json_obj[data["source"]] is not False:
        existing = [item is not None for item in json_obj[data["source"]]]

    name_list = [
        None if (new == old and not exist) else new
        for new, old, exist in zip(name_list, data["original_name"].split("-"), existing)
    ]

    if all([item is None for item in name_list]):
        del json_obj[data["source"]]
    else:
        json_obj[data["source"]] = name_list

    save_manual(json_obj, filepath)


@app.route("/manual-entry", methods=["POST"])
def manual_entry():
    data = request.form
    update_manual_entry(
        data["project"],
        data["subject"],
        data["session"],
        data,
    )
    return "Manual Name Added/Updated"


@app.route("/ignore-entry", methods=["POST"])
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


@app.route("/ignore-btn", methods=["POST"])
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


@app.route("/qa/qa-pass-btn", methods=["POST"])
def qa_pass_btn():
    data = request.get_json()
    add_qa_entry(
        data["project"],
        data["subject"],
        data["session"],
        data["source"],
        'pass',
    )
    return jsonify(message="QA Pass")


@app.route("/qa/qa-fail-btn", methods=["POST"])
def qa_fail_btn():
    data = request.get_json()
    add_qa_entry(
        data["project"],
        data["subject"],
        data["session"],
        data["source"],
        'fail',
    )
    return jsonify(message="QA Fail")


@app.route("/change-btn", methods=["POST"])
def change_btn():
    data = request.get_json()
    update_manual_entry(
        data["project"],
        data["subject"],
        data["session"],
        data,
    )
    return jsonify(message="Body Part Updated")


@app.route("/image/<project_id>/<subject_id>/<session_id>/<qa_dir>/<image_name>")
def image(project_id, subject_id, session_id, qa_dir, image_name):
    return send_from_directory(
        str(DATA_DIR / project_id / subject_id / session_id / "qa" / qa_dir), image_name
    )
