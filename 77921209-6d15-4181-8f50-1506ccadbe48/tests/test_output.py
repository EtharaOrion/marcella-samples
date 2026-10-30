"""Grade the AML measurable residual disease answer: an integrity gate, then three parts.

Gate (score 0 when any check fails): every output is a regular file, no output text is addressed to a grader, /data is
unchanged, and the four tables and the masks have exactly the required columns, rows, lengths and 0/1 values.
Part 1, diagnosis gates: a graded diagnosis LAIP counts when the per-cell F1 of the agent's mask against the
laboratory's cells is at least unit_f1; S1 is the share counted; the part passes at S1 >= pass_share.
Part 2, clinical answer: the call of every determinable case, the MRD of every determinable positive within
magnitude_factor, the MRD of every credited case at or below credited_ceiling_percent (all must hold), and the
follow-up white-cell count within wbc_tolerance of the laboratory's in at least wbc_share of the tubes; S2 is the
share of all part 2 units met.
Part 3, consistency: every reported number recomputed from the agent's own masks; passes only at S3 = 1.
Score = 1 when the gate and all three parts pass, else cap x (w1 S1 + w2 S2 + w3 S3).
"""

import csv
import functools
import json
import math
import os
import re
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import rewardkit as rk

KEY = Path(os.environ.get("MRD_KEY_DIR", "/opt/mrd-key"))
MANIFEST = Path(os.environ.get("MRD_INTEGRITY_MANIFEST", "/var/lib/mrd-integrity/data.sha256"))
COLUMNS = {
    "diagnosis_laips.csv": ["case", "laip", "tube", "events"],
    "followup_laips.csv": ["case", "tube", "laip", "compartment", "compartment_events", "events", "percent_of_wbc"],
    "followup_tubes.csv": ["case", "tube", "wbc_events", "mrd_percent", "top_laip", "negativity_evaluable"],
    "patients.csv": ["case", "mrd_percent", "call"],
}
COMPARTMENTS = ("WBC", "CD34", "CD117", "BLAST")
TOKEN = re.compile(r"(CD\d+[A-Za-z]?|HLA-DR)(\+\+|\+|-)")
SCREEN_LIMIT = 1048576
PATTERNS = [
    r"\b(?:ignore|disregard|forget|override|bypass)\b[^.!?]{0,60}\b(?:instructions?|prompts?|guidelines?|directions?|system messages?)\b",
    r"\b(?:dear|attention|note to|note for|message to|message for|hello|hi|hey)\b[^.!?]{0,20}\b(?:graders?|judges?|evaluators?|assessors?|markers?|scorers?|llms?|ai|language models?|assistants?)\b",
    r"\byou (?:are|will be|must|should|shall|have to|need to|may)\b[^.!?]{0,30}\b(?:graders?|grading|judges?|judging|evaluators?|evaluating|assessors?|scorers?|scoring|marking|language models?|llms?|ai models?|assistants?)\b",
    r"\b(?:act|acting|behave|role ?play|pretend)\b[^.!?]{0,10}\bas (?:an? |the )?(?:graders?|judges?|evaluators?|assessors?|scorers?|markers?|reviewers?|language models?|llms?|assistants?)\b",
    r"\b(?:award|give|assign|grant|mark|grade|rate)\b[^.!?]{0,40}\b(?:full|maximum|max|perfect|top|all)\b[^.!?]{0,12}\b(?:marks?|credit|scores?|rewards?)\b",
    r"\b(?:full|maximum|perfect) (?:marks|credit|reward)\b",
    r"\b(?:answer|respond|reply|say|output|mark|grade|rate|score)\b[^.!?]{0,30}\b(?:yes|pass|passed|true|correct)\b[^.!?]{0,40}\b(?:every|each|all|any|these)\b[^.!?]{0,20}\b(?:questions?|criteri(?:on|a)|items?|checks?|checklist|rubric)\b",
    r"\b(?:all|every|each) (?:of the )?(?:criteri(?:on|a)|checklist items?|rubric items?|questions) (?:are|is|were|should be|must be|has been|have been) (?:met|satisfied|fulfilled|passed|answered yes|true|correct)\b",
    r"\b(?:llm|ai|automated|model) (?:judges?|graders?|evaluators?|reviewers?|scorers?)\b",
    r"\b(?:system|developer) (?:prompts?|messages?|instructions?)\b",
    r"<\|[^|>]{1,30}\|>",
    r"\[/?inst\]",
    r"<<\s*/?sys\s*>>",
    r"<!--",
    r"<\s*(?:script|style|iframe|object|embed)\b",
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0",
]
LINE_PATTERNS = [r"^\s*(?:#+\s*)?(?:assistant|human|user|developer|grader|judge|evaluator)\s*:"]
WORD = re.compile(r"[^\W\d_]+")
LATIN = re.compile(r"[A-Za-z\u00c0-\u024f]")
CYRILLIC = re.compile(r"[\u0400-\u052f]")


class Malformed(ValueError):
    """The submission breaks the required format, which fails the gate."""


def _load_json(name):
    with open(KEY / name, encoding="utf-8") as handle:
        return json.load(handle)


def _aimed_at_grader(text):
    body = text[1:] if text.startswith("\ufeff") else text
    for char in body:
        kind = unicodedata.category(char)
        if kind in ("Cf", "Co", "Cn", "Cs") or (kind == "Cc" and char not in "\t\n\r"):
            return True
    if any(LATIN.search(word) and CYRILLIC.search(word) for word in WORD.findall(body)):
        return True
    folded = unicodedata.normalize("NFKC", body).casefold()
    if any(re.search(pattern, folded, re.MULTILINE) for pattern in LINE_PATTERNS):
        return True
    flat = re.sub(r"\s+", " ", folded)
    return any(re.search(pattern, flat) for pattern in PATTERNS)


def _regular_files(ws):
    out, method = ws / "output", ws / "method.md"
    if method.is_symlink() or (method.exists() and not method.is_file()):
        return False
    if out.is_symlink() or not out.is_dir():
        return False
    for root, dirs, files in os.walk(out, followlinks=False):
        for name in dirs + files:
            path = Path(root) / name
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                return False
    return True


def _grader_text_absent(ws):
    paths = [ws / "method.md"] + sorted((ws / "output").glob("*.csv"))
    for path in paths:
        if path.is_symlink() or not path.exists():
            continue
        try:
            if not path.is_file() or path.stat().st_size > SCREEN_LIMIT:
                return False
            text = path.read_bytes().decode("utf-8", "replace")
        except OSError:
            return False
        if _aimed_at_grader(text):
            return False
    return True


def _data_intact():
    if MANIFEST.is_symlink() or not MANIFEST.is_file():
        return False
    try:
        lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    found = {}
    for line in lines:
        digest, sep, name = line.partition("  ")
        if not sep or name in found:
            return False
        found[name] = digest
    return found == _load_json("data.sha256.json")


def _int(value):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise Malformed(f"not a number: {value!r}") from exc
    if not math.isfinite(number) or not number.is_integer() or number < 0:
        raise Malformed(f"not a count: {value!r}")
    return int(number)


def _float(value):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise Malformed(f"not a number: {value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise Malformed(f"not a finite non-negative number: {value!r}")
    return number


def _table(ws, name):
    path = ws / "output" / name
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise Malformed(f"{name}: unreadable") from exc
    if not rows or rows[0] != COLUMNS[name]:
        raise Malformed(f"{name}: header must be {COLUMNS[name]}")
    body = [row for row in rows[1:] if row]
    if any(len(row) != len(COLUMNS[name]) for row in body):
        raise Malformed(f"{name}: every row needs {len(COLUMNS[name])} fields")
    return [dict(zip(COLUMNS[name], row)) for row in body]


def _mask(array, n):
    a = np.asarray(array)
    if a.shape != (n,) or a.dtype.kind not in "biuf":
        return None
    if a.dtype.kind == "b":
        return a
    if not np.isin(a, (0, 1)).all():
        return None
    return a.astype(bool)


def _masks(path, names, n):
    try:
        with np.load(path, allow_pickle=False) as z:
            files = set(z.files)
            out = {}
            for name in names:
                m = _mask(z[name], n) if name in files else None
                if m is None:
                    raise Malformed(f"{path.name}: array {name} missing or not a 0/1 vector of {n} events")
                out[name] = m
            return out
    except (OSError, ValueError, zipfile.BadZipFile, EOFError, KeyError) as exc:
        if isinstance(exc, Malformed):
            raise
        raise Malformed(f"{path.name}: unreadable mask file") from exc


def _close(a, b, rel):
    return abs(float(a) - float(b)) <= rel * max(1.0, abs(float(b)))


def _markers(phenotype):
    return {m.upper() for m, _ in TOKEN.findall(phenotype)}


def _read_submission(ws, index):
    dxl, ful, fut, pat = (_table(ws, name) for name in COLUMNS)
    reports = index["reports"]
    want = {(case, r["laip"]) for case, rows in reports.items() for r in rows}
    got = [(r["case"], r["laip"]) for r in dxl]
    if len(got) != len(set(got)) or set(got) != want:
        raise Malformed("diagnosis_laips.csv: rows must be exactly the reported LAIPs")
    for r in dxl:
        r["events"] = _int(r["events"])
    fu_tubes = set(index["followup"])
    tube_rows = {f"{r['case']}/{r['tube']}": r for r in fut}
    if len(tube_rows) != len(fut) or set(tube_rows) != fu_tubes:
        raise Malformed("followup_tubes.csv: rows must be exactly the follow-up tubes")
    for r in fut:
        r["wbc_events"] = _int(r["wbc_events"])
        r["mrd_percent"] = _float(r["mrd_percent"])
        if r["negativity_evaluable"].strip().lower() not in ("true", "false"):
            raise Malformed("followup_tubes.csv: negativity_evaluable must be true or false")
        r["negativity_evaluable"] = r["negativity_evaluable"].strip().lower() == "true"
    cases = {key.split("/")[0] for key in fu_tubes}
    pat_rows = {r["case"]: r for r in pat}
    if len(pat_rows) != len(pat) or set(pat_rows) != cases:
        raise Malformed("patients.csv: rows must be exactly the cases with follow-up")
    for r in pat:
        r["mrd_percent"] = _float(r["mrd_percent"])
        if r["call"] not in ("POSITIVE", "NEGATIVE"):
            raise Malformed("patients.csv: call must be POSITIVE or NEGATIVE")
    seen = set()
    for r in ful:
        key = (r["case"], r["tube"], r["laip"])
        if f"{r['case']}/{r['tube']}" not in fu_tubes or key in seen:
            raise Malformed("followup_laips.csv: a row names an unknown follow-up tube or repeats a LAIP")
        seen.add(key)
        r["compartment_events"] = _int(r["compartment_events"])
        r["events"] = _int(r["events"])
        r["percent_of_wbc"] = _float(r["percent_of_wbc"])
    dx_masks, fu_masks = {}, {}
    for key, info in index["diagnosis"].items():
        case, tube = key.split("/")
        names = [r["laip"] for r in reports[case] if r["tube"] == tube]
        got_masks = _masks(ws / "output" / "masks" / "diagnosis" / f"{case}_{tube}.npz", names, info["events"])
        for laip, m in got_masks.items():
            dx_masks[(case, laip)] = m
    for key, info in index["followup"].items():
        case, tube = key.split("/")
        names = ["wbc", "cd34", "cd117"] + [r["laip"] for r in ful if r["case"] == case and r["tube"] == tube]
        fu_masks[key] = _masks(ws / "output" / "masks" / "followup" / f"{case}_{tube}.npz", names, info["events"])
    return dxl, ful, fut, pat, dx_masks, fu_masks


def _grade(ws):
    g, index = _load_json("grading.json"), _load_json("index.json")
    dxl, ful, fut, pat, dx_masks, fu_masks = _read_submission(ws, index)
    reports = index["reports"]

    d = g["diagnosis"]
    p1 = {}
    for cid in d["determinable"]:
        case, laip = cid.split("/")
        tube = next(r["tube"] for r in reports[case] if r["laip"] == laip)
        with np.load(KEY / "diagnosis_events" / f"{case}_{tube}.npz") as z:
            truth = np.unpackbits(z[laip])[: int(z["n"])].astype(bool)
        m = dx_masks[(case, laip)]
        f1 = 2 * int((m & truth).sum()) / max(int(m.sum()) + int(truth.sum()), 1)
        p1[cid] = f1 >= d["unit_f1"]
    s1 = sum(p1.values()) / len(p1)

    pat_i = {r["case"]: r for r in pat}
    units2 = {}
    for case, v in g["determinable"].items():
        expert = v["expert_mrd_percent"]
        units2[f"call {case}"] = (pat_i[case]["call"] == "POSITIVE") == (expert >= g["cut_percent"])
        if expert >= g["cut_percent"]:
            x = pat_i[case]["mrd_percent"]
            units2[f"size {case}"] = x > 0 and abs(math.log10(x / expert)) <= math.log10(g["magnitude_factor"])
    for case in g["credited"]:
        units2[f"ceiling {case}"] = pat_i[case]["mrd_percent"] <= g["credited_ceiling_percent"]
    fut_i = {f"{r['case']}/{r['tube']}": r for r in fut}
    wbc_units = {k: abs(fut_i[k]["wbc_events"] / v - 1) <= g["wbc_tolerance"] for k, v in g["followup_wbc"].items()}
    s2 = (sum(units2.values()) + sum(wbc_units.values())) / (len(units2) + len(wbc_units))
    pass2 = all(units2.values()) and sum(wbc_units.values()) / len(wbc_units) >= g["wbc_share"]

    rel = g["rel_tol"]
    u3 = {}
    for r in dxl:
        u3[f"dx count {r['case']}/{r['laip']}"] = r["events"] == int(dx_masks[(r["case"], r["laip"])].sum())
    for key, info in index["followup"].items():
        case, tube = key.split("/")
        masks = fu_masks[key]
        wbc = masks["wbc"]
        comp = {"WBC": wbc, "CD34": masks["cd34"], "CD117": masks["cd117"]}
        comp["BLAST"] = comp["CD34"] | comp["CD117"]
        u3[f"gates inside WBC {key}"] = not (comp["BLAST"] & ~wbc).any()
        rows = [r for r in ful if r["case"] == case and r["tube"] == tube]
        reported = {r["laip"] for r in reports[case]}
        tracked = []
        for r in rows:
            m = masks[r["laip"]]
            c = comp.get(r["compartment"])
            ok = (r["laip"] in reported and c is not None and not (m & ~wbc).any() and r["events"] == int(m.sum())
                  and r["compartment_events"] == int(c.sum())
                  and _close(r["percent_of_wbc"], 100.0 * int(m.sum()) / max(int(wbc.sum()), 1), rel))
            u3[f"laip row {key}/{r['laip']}"] = ok
            tracked.append((r["laip"], int(m.sum()), int(c.sum()) if c is not None else 0))
        panel = set(info["panel"])
        for rep in reports[case]:
            if _markers(rep["phenotype"]) <= panel:
                u3[f"tracked {key}/{rep['laip']}"] = rep["laip"] in {r["laip"] for r in rows}
        n_wbc = int(wbc.sum())
        top_n = max((k for _, k, _ in tracked), default=0)
        order = sorted(tracked, key=lambda x: int(x[0][1:]) if x[0][1:].isdigit() else 10**9)
        top = next((lid for lid, k, _ in order if k == top_n), "") if top_n > 0 else ""
        assessed = max((ce for _, _, ce in tracked), default=int(comp["BLAST"].sum()))
        t = fut_i[key]
        u3[f"tube wbc {key}"] = t["wbc_events"] == n_wbc
        u3[f"tube mrd {key}"] = _close(t["mrd_percent"], 100.0 * top_n / max(n_wbc, 1), rel)
        u3[f"tube top {key}"] = t["top_laip"] == top
        evaluable = n_wbc > g["neg_min_wbc"] and assessed >= g["neg_min_compartment"]
        u3[f"tube negativity {key}"] = t["negativity_evaluable"] == evaluable
    for case, r in pat_i.items():
        tubes = [t["mrd_percent"] for k, t in fut_i.items() if k.split("/")[0] == case]
        u3[f"case mrd {case}"] = _close(r["mrd_percent"], max(tubes), rel)
        u3[f"case call {case}"] = (r["call"] == "POSITIVE") == (r["mrd_percent"] >= g["cut_percent"])
    s3 = sum(u3.values()) / len(u3)

    pass1, pass3 = s1 >= d["pass_share"], s3 == 1.0
    w1, w2, w3 = g["part_weights"]
    score = 1.0 if (pass1 and pass2 and pass3) else g["cap"] * (w1 * s1 + w2 * s2 + w3 * s3)
    return {"score": score, "part1_share": s1, "part2_share": s2, "part3_share": s3,
            "part1_pass": float(pass1), "part2_pass": float(pass2), "part3_pass": float(pass3)}


@functools.lru_cache(maxsize=4)
def evaluate(workspace):
    ws = Path(workspace)
    gate = {"gate_regular_files": _regular_files(ws), "gate_grader_text": False, "gate_input_data": _data_intact(),
            "gate_format": False}
    gate["gate_grader_text"] = gate["gate_regular_files"] and _grader_text_absent(ws)
    zero = {"score": 0.0, "part1_share": 0.0, "part2_share": 0.0, "part3_share": 0.0,
            "part1_pass": 0.0, "part2_pass": 0.0, "part3_pass": 0.0}
    if not (gate["gate_regular_files"] and gate["gate_grader_text"] and gate["gate_input_data"]):
        return {**zero, **{k: float(v) for k, v in gate.items()}}
    try:
        result = _grade(ws)
        gate["gate_format"] = True
    except Malformed:
        result = zero
    return {**result, **{k: float(v) for k, v in gate.items()}}


@rk.criterion(description="{item}")
def mrd(workspace: Path, item: str) -> float:
    return float(evaluate(str(workspace))[item])


rk.mrd("score", weight=1.0, name="score")
for _item in ("gate_regular_files", "gate_grader_text", "gate_input_data", "gate_format",
              "part1_share", "part2_share", "part3_share", "part1_pass", "part2_pass", "part3_pass"):
    rk.mrd(_item, weight=0.0, name=_item)
