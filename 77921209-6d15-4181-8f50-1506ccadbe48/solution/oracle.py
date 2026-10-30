#!/usr/bin/env python3
# GENERATED SECTION. DO NOT HAND-EDIT.
"""Reference solution: AML measurable residual disease by tracking the diagnosis LAIPs into follow-up.

Reads MRD_DATA (default /data): diagnosis tubes with the expert pre-gating and the diagnosis LAIP report, normal
marrows with their expert gates, follow-up tubes. Writes MRD_OUT (default /app/output): tubes.csv, laips.csv,
the four tables and the event masks the instruction names, and METHOD (default /app/method.md).

1. Every FCS file is compensated with its own SPILL matrix; fluorescence is arcsinh(x / 150), scatter is x / 1000.
2. WBC, CD34+ and CD117+ gates are gradient-boosting classifiers trained on the expert pre-gating of every diagnosis
   tube and of the training half of the normal donors.
3. Each reported LAIP is rebuilt on its diagnosis tube: a box over its named markers inside its primary gate (CD34+ or
   CD117+ when named, WBC for monocytic phenotypes, the blast gate otherwise). A marker in its normal state on myeloid
   blasts is a qualifier at the normal primary population's 5th/95th percentile; every other marker is aberrant and
   sits at the normal quantile whose diagnosis count best matches the reported LAIP size. These events label the LAIP.
4. Each LAIP gets a classifier (its labelled events against the rest of its diagnosis tube and the normal marrows);
   its threshold rises until the held-out normal donors put at most 1e-5 of their WBC inside it.
5. Follow-up: every reported LAIP whose markers the tube measures is counted inside the predicted primary gate.
   Tube MRD% = largest single LAIP / WBC x 100; case MRD% = largest tube; MRD-positive when >= 0.1%.
"""
import glob
import os
import re

import flowio
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

DATA = os.environ.get("MRD_DATA", "/data")
OUT = os.environ.get("MRD_OUT", "/app/output")
METHOD = os.environ.get("MRD_METHOD", "/app/method.md")
BUDGET = float(os.environ.get("MRD_BUDGET", "1e-5"))
CUT = 0.1  # ELN 2021 D11: positive at >= 0.1% of CD45-expressing cells
NEG_MIN_WBC = 500_000  # ELN 2021 A11: negativity needs > 500,000 CD45+ cells ...
NEG_MIN_COMPARTMENT = 100  # ... and >= 100 cells in the compartment assessed for the best aberrancy
COFACTOR = 150.0
SCATTER = {"FSC-A", "FSC-H", "FSC-W", "SSC-A", "SSC-H", "SSC-W"}
WBC_F = ["FSC-A", "FSC-H", "SSC-A", "SSC-H", "CD45"]
GATE_F = ["FSC-A", "SSC-A", "CD45", "CD34", "CD117"]
NORMAL_ON_BLASTS = {"CD13", "CD33", "HLADR", "CD34", "CD117", "CD45", "CD133"}
MONOCYTIC = {"CD14", "CD36"}
NORMAL_ON_MONOCYTES = {"CD14", "CD36", "CD11B", "CD64", "HLADR", "CD33", "CD13", "CD45"}
ALPHA_GRID = np.concatenate([[0.0], np.logspace(-5, np.log10(0.5), 48)])
QUALIFIER_Q = float(os.environ.get("MRD_QUALIFIER_Q", "0.05"))
SPLIT = os.environ.get("MRD_SPLIT", "even")
COMPENSATE = os.environ.get("MRD_NO_COMP") != "1"
TOKEN = re.compile(r"(CD\d+[A-Za-z]?|HLA-DR)(\+\+|\+|-)")
RNG = np.random.default_rng(0)


def subdirs(path):
    """Case and donor folders only: hidden entries and stray files (for example .DS_Store) are not cases."""
    return sorted(d for d in os.listdir(path) if not d.startswith(".") and os.path.isdir(os.path.join(path, d)))


def load(path):
    flow = flowio.FlowData(path)
    text = {k.lower().lstrip("$"): v for k, v in flow.text.items()}
    n = int(text["par"])
    x = np.reshape(np.asarray(flow.events, dtype=np.float64), (-1, n))
    names = [text[f"p{i}n"] for i in range(1, n + 1)]
    stains = [text.get(f"p{i}s", "") or "" for i in range(1, n + 1)]
    spill = text.get("spill") or text.get("spillover")
    if spill and COMPENSATE:
        parts = [p.strip() for p in spill.split(",")]
        k = int(parts[0])
        idx = [names.index(c) for c in parts[1:1 + k]]
        x[:, idx] = x[:, idx] @ np.linalg.inv(np.array(parts[1 + k:1 + k + k * k], dtype=float).reshape(k, k))
    cols = []
    for i, (name, stain) in enumerate(zip(names, stains)):
        if name in SCATTER:
            x[:, i] /= 1000.0
            cols.append(name)
        elif name == "Time":
            cols.append(name)
        else:
            x[:, i] = np.arcsinh(x[:, i] / COFACTOR)
            cols.append((stain.split(" ")[0] if stain else name).upper().replace("HLA-DR", "HLADR"))
    return pd.DataFrame(x.astype(np.float32), columns=cols)


def parse(phenotype):
    spec = {}
    for token in str(phenotype).split():
        m = TOKEN.fullmatch(token)
        if not m:
            raise ValueError(f"unreadable phenotype token {token!r}")
        spec[m.group(1).upper().replace("HLA-DR", "HLADR")] = {"++": "BRIGHT", "+": "POS", "-": "NEG"}[m.group(2)]
    return spec


def primary_of(spec):
    if spec.get("CD34") in ("POS", "BRIGHT"):
        return "CD34"
    if spec.get("CD117") in ("POS", "BRIGHT"):
        return "CD117"
    return "WBC" if MONOCYTIC & set(spec) else "BLAST"


def features(spec):
    return GATE_F + [m for m in spec if m not in GATE_F]


def pick(mask, k):
    idx = np.flatnonzero(mask)
    return idx if len(idx) <= k else np.sort(RNG.choice(idx, size=k, replace=False))


def hgb():
    return HistGradientBoostingClassifier(max_iter=200, max_leaf_nodes=31, random_state=0)


def roles(spec, prim, dx, ref):
    """A marker in its normal state on myeloid blasts is a qualifier; any other state is the aberrancy. (A monocytic
    variant, judging CD14/CD36 phenotypes against monocytes, was tried in Phase 3.5 and lowered F1 on 3 of 3
    monocytic LAIPs, so it is not used.)"""
    normal = NORMAL_ON_BLASTS
    out = {}
    for m, st in spec.items():
        if m == prim:
            continue
        normal_pos = m in normal
        out[m] = "qualifier" if (normal_pos and st == "POS") or (not normal_pos and st == "NEG") else "aberrant"
    if out and "aberrant" not in out.values():
        def shift(m):
            iqr = float(np.subtract(*np.quantile(ref[m], [0.75, 0.25]))) + 1e-6
            if spec[m] == "NEG":
                return (np.quantile(ref[m], 0.01) - np.quantile(dx[m], 0.10)) / iqr
            return (np.quantile(dx[m], 0.90) - np.quantile(ref[m], 0.99)) / iqr
        out[max(out, key=shift)] = "aberrant"
    return out


def pseudo_labels(spec, rl, dx, ref, reported):
    """Events of the box whose diagnosis count best matches the reported size; also returns the loosest box's count."""
    best, loosest = None, 0
    for a in ALPHA_GRID:
        sel = np.ones(len(dx), bool)
        for m, r in rl.items():
            x = ref[m].to_numpy()
            q = (QUALIFIER_Q if spec[m] != "NEG" else 1 - QUALIFIER_Q) if r == "qualifier" else (1 - a if spec[m] != "NEG" else a)
            t = np.quantile(x, q)
            sel &= (dx[m].to_numpy() <= t) if spec[m] == "NEG" else (dx[m].to_numpy() >= t)
        err = abs(np.log((sel.sum() + 1) / (reported + 1)))
        loosest = max(loosest, int(sel.sum()))
        if best is None or err < best[0]:
            best = (err, sel)
    return best[1], loosest


def rebuild(spec, prim, prim_masks, df, normal_prim, reported):
    """Diagnosis events of a reported LAIP. R2: a LAIP naming neither CD34 nor CD117 is searched in the blast gate,
    unless even the loosest box there holds under half the reported size; then it was drawn on all white cells."""
    for p in ([prim, "WBC"] if prim == "BLAST" else [prim]):
        ref = pd.concat([d for d in normal_prim[p] if set(spec) <= set(d.columns)])
        dx = df.loc[prim_masks[p], list(spec)]
        sel, loosest = pseudo_labels(spec, roles(spec, p, dx, ref), dx, ref, reported)
        if p != "BLAST" or loosest >= 0.5 * reported:
            m = np.zeros(len(df), bool)
            m[np.flatnonzero(prim_masks[p])[sel]] = True
            return p, m


def gates(models, df):
    w = models["wbc"].predict_proba(df[WBC_F].to_numpy())[:, 1] > 0.5
    x = df[GATE_F].to_numpy()
    c34 = w & (models["cd34"].predict_proba(x)[:, 1] > 0.5)
    c117 = w & (models["cd117"].predict_proba(x)[:, 1] > 0.5)
    return {"WBC": w, "CD34": c34, "CD117": c117, "BLAST": c34 | c117}


def threshold(scores, weights, total):
    order = np.argsort(-scores)
    s, cw = scores[order], np.cumsum(weights[order])
    k = int(np.searchsorted(cw, BUDGET * total, side="right"))
    return 0.0 if k >= len(s) else max(0.0, float(np.nextafter(s[k], np.inf)))


def main():
    os.makedirs(f"{OUT}/masks/diagnosis", exist_ok=True)
    os.makedirs(f"{OUT}/masks/followup", exist_ok=True)
    dx_rows = []
    donors = subdirs(f"{DATA}/normal")
    train = set(donors[0::2]) if SPLIT == "even" else set(donors[1::2])
    gx, gy = {"wbc": [], "cd34": [], "cd117": []}, {"wbc": [], "cd34": [], "cd117": []}
    normal_neg, normal_prim, held_out = [], {"CD34": [], "CD117": [], "BLAST": [], "WBC": []}, []
    for donor in donors:
        for path in sorted(glob.glob(f"{DATA}/normal/{donor}/*.fcs")):
            if donor not in train:
                held_out.append(path)
                continue
            df = load(path)
            g = pd.read_csv(path[:-4] + ".gates.csv.gz")
            w = g["wbc"].to_numpy() == 1
            i = pick(np.ones(len(df), bool), 15000)
            gx["wbc"].append(df[WBC_F].to_numpy()[i]); gy["wbc"].append(w[i])
            for name, col in (("cd34", "cd34pos"), ("cd117", "cd117pos")):
                t = w & (g[col].to_numpy() == 1)
                i = np.concatenate([pick(t, 15000), pick(w & ~t, 15000)])
                gx[name].append(df[GATE_F].to_numpy()[i]); gy[name].append(t[i])
            b = w & (g["blast"].to_numpy() == 1)
            normal_neg.append(df.iloc[np.concatenate([pick(b, 10000), pick(w & ~b, 3000)])])
            c34, c117 = w & (g["cd34pos"].to_numpy() == 1), w & (g["cd117pos"].to_numpy() == 1)
            normal_prim["CD34"].append(df.iloc[pick(c34, 10000)]); normal_prim["CD117"].append(df.iloc[pick(c117, 10000)])
            normal_prim["BLAST"].append(df.iloc[pick(c34 | c117, 10000)]); normal_prim["WBC"].append(df.iloc[pick(w, 20000)])

    laips = {}
    for case in subdirs(f"{DATA}/diagnosis"):
        report = pd.read_csv(f"{DATA}/diagnosis/{case}/laip_report.csv")
        frames = {}
        for path in sorted(glob.glob(f"{DATA}/diagnosis/{case}/*.fcs")):
            tube = os.path.basename(path)[:-4]
            df = load(path)
            g = pd.read_csv(path[:-4] + ".gates.csv.gz")
            w = g["wbc"].to_numpy() == 1
            i = pick(np.ones(len(df), bool), 15000)
            gx["wbc"].append(df[WBC_F].to_numpy()[i]); gy["wbc"].append(w[i])
            for name, col in (("cd34", "cd34pos"), ("cd117", "cd117pos")):
                t = w & (g[col].to_numpy() == 1)
                i = np.concatenate([pick(t, 15000), pick(w & ~t, 15000)])
                gx[name].append(df[GATE_F].to_numpy()[i]); gy[name].append(t[i])
            prim = {"CD34": w & (g["cd34pos"].to_numpy() == 1), "CD117": w & (g["cd117pos"].to_numpy() == 1), "WBC": w}
            prim["BLAST"] = prim["CD34"] | prim["CD117"]
            frames[tube] = (df, prim)
        dx_masks = {tube: {} for tube in frames}
        for _, row in report.iterrows():
            df, prim_masks = frames[row["tube"]]
            spec = parse(row["phenotype"])
            m = np.zeros(len(df), bool)
            if set(spec) <= set(df.columns) and int(row["events"]) >= 20:
                f = features(spec)
                prim, m = rebuild(spec, primary_of(spec), prim_masks, df, normal_prim, int(row["events"]))
            dx_masks[row["tube"]][row["laip"]] = m
            dx_rows.append({"case": case, "laip": row["laip"], "tube": row["tube"], "events": int(m.sum())})
            if m.sum() < 20:
                continue
            w = prim_masks["WBC"]
            pos = df.loc[m, f].iloc[pick(np.ones(int(m.sum()), bool), 30000)]
            neg = [df.iloc[np.concatenate([pick(prim_masks["BLAST"] & ~m, 40000), pick(w & ~prim_masks["BLAST"] & ~m, 15000)])][f]]
            neg += [n[f] for n in normal_neg if set(f) <= set(n.columns)]
            laips[(case, row["laip"])] = {"spec": spec, "prim": prim, "features": f, "pos": pos, "neg": pd.concat(neg)}
        for tube, tube_masks in dx_masks.items():
            np.savez_compressed(f"{OUT}/masks/diagnosis/{case}_{tube}.npz", **tube_masks)
    pd.DataFrame(dx_rows, columns=["case", "laip", "tube", "events"]).to_csv(f"{OUT}/diagnosis_laips.csv", index=False)
    models = {k: hgb().fit(np.concatenate(gx[k]), np.concatenate(gy[k])) for k in gx}

    calib = []
    for path in held_out:
        df = load(path)
        g = gates(models, df)
        rest = g["WBC"] & ~g["BLAST"]
        keep = pick(rest, 30000)
        idx = np.concatenate([np.flatnonzero(g["BLAST"]), keep])
        weight = np.concatenate([np.ones(int(g["BLAST"].sum())), np.full(len(keep), rest.sum() / max(len(keep), 1))])
        calib.append({"df": df.iloc[idx].reset_index(drop=True), "weight": weight, "wbc": int(g["WBC"].sum()),
                      "gate": {k: v[idx] for k, v in g.items()}})
    for e in laips.values():
        f = e["features"]
        x = np.concatenate([e["pos"].to_numpy(), e["neg"].to_numpy()])
        y = np.concatenate([np.ones(len(e["pos"]), bool), np.zeros(len(e["neg"]), bool)])
        e["model"] = hgb().fit(x, y)
        scores, weights, total = [], [], 0
        for c in calib:
            if set(f) <= set(c["df"].columns):
                sel = c["gate"][e["prim"]]
                scores.append(e["model"].decision_function(c["df"].loc[sel, f].to_numpy()))
                weights.append(c["weight"][sel])
                total += c["wbc"]
        e["tau"] = threshold(np.concatenate(scores), np.concatenate(weights), total) if total else 0.0
        del e["pos"], e["neg"]

    tubes, rows, cases = [], [], {}
    for case in subdirs(f"{DATA}/followup"):
        for path in sorted(glob.glob(f"{DATA}/followup/{case}/*.fcs")):
            tube = os.path.basename(path)[:-4]
            df = load(path)
            g = gates(models, df)
            wbc = int(g["WBC"].sum())
            masks = {"wbc": g["WBC"], "cd34": g["CD34"], "cd117": g["CD117"]}
            tracked = []
            for (c, lid), e in sorted(laips.items(), key=lambda kv: (kv[0][0], int(kv[0][1][1:]))):
                if c != case or not set(e["features"]) <= set(df.columns):
                    continue
                sel = g[e["prim"]]
                s = np.full(len(df), -np.inf)
                s[sel] = e["model"].decision_function(df.loc[sel, e["features"]].to_numpy())
                hit = s >= e["tau"]
                masks[lid] = hit
                tracked.append((lid, int(hit.sum()), int(sel.sum())))
                rows.append({"case": case, "tube": tube, "laip": lid, "compartment": e["prim"], "compartment_events": int(sel.sum()),
                             "events": int(hit.sum()), "percent_of_wbc": 100.0 * int(hit.sum()) / wbc if wbc else 0.0})
            top_n = max((n for _, n, _ in tracked), default=0)
            top = next((lid for lid, n, _ in tracked if n == top_n), "") if top_n > 0 else ""
            mrd = 100.0 * top_n / wbc if wbc else 0.0
            assessed = max((ce for _, _, ce in tracked), default=int(g["BLAST"].sum()))
            tubes.append({"case": case, "tube": tube, "wbc_events": wbc, "mrd_percent": mrd, "top_laip": top,
                          "negativity_evaluable": bool(wbc > NEG_MIN_WBC and assessed >= NEG_MIN_COMPARTMENT)})
            cases[case] = max(cases.get(case, 0.0), mrd)
            np.savez_compressed(f"{OUT}/masks/followup/{case}_{tube}.npz", **masks)
            print(f"{case}/{tube}: WBC {wbc} MRD {mrd:.4f}% ({top or 'no LAIP events'})", flush=True)
    pd.DataFrame(tubes, columns=["case", "tube", "wbc_events", "mrd_percent", "top_laip", "negativity_evaluable"]
                 ).to_csv(f"{OUT}/followup_tubes.csv", index=False)
    pd.DataFrame(rows, columns=["case", "tube", "laip", "compartment", "compartment_events", "events", "percent_of_wbc"]
                 ).to_csv(f"{OUT}/followup_laips.csv", index=False)
    pd.DataFrame([{"case": c, "mrd_percent": v, "call": "POSITIVE" if v >= CUT else "NEGATIVE"} for c, v in sorted(cases.items())]
                 ).to_csv(f"{OUT}/patients.csv", index=False)


METHOD_TEXT = """# Method

Every FCS file was read with FlowIO, and the fluorescence values of each file were compensated with that file's own SPILL matrix before any gate was drawn. Fluorescence was put on an arcsinh scale with cofactor 150 and scatter was divided by 1000.

White-cell, CD34-positive and CD117-positive white-cell gates were learned with gradient-boosting classifiers from the laboratory's pre-gating of every diagnosis tube and of half of the healthy donors, so the follow-up tubes, which carry no gating, received the same gates.

Each LAIP of the laboratory's LAIP report was rebuilt on its diagnosis tube from the laboratory's diagnosis pre-gating: inside its primary compartment (CD34-positive or CD117-positive white cells when the phenotype names them, all white cells for a monocytic phenotype, the blast compartment otherwise), each named marker was placed against the healthy donors' distribution of the same compartment, and the box whose diagnosis event count best matched the reported LAIP size was kept.

Each LAIP then received a classifier trained on its diagnosis events against the rest of its diagnosis tube and the healthy donors' marrow, and its threshold was raised until the held-out healthy donors put at most 1e-5 of their white cells inside it. This limits each LAIP gate with the healthy donors' marrow before it is applied to follow-up tubes, so normal and regenerating CD34-positive and CD117-positive progenitors stay outside the LAIP.

In each follow-up tube, every LAIP of the case whose markers the tube's panel measures was tracked inside its primary compartment, and its events were counted among the CD45-expressing white cells left after debris and doublets are excluded, not among all recorded events.

A tube's MRD is its largest single LAIP over its white cells times 100, its top LAIP is that LAIP (the lower number on a tie), and a case's MRD is its largest tube. A case is MRD positive at 0.1 percent or more and negative below 0.1 percent. A tube is evaluable for negativity when it holds more than 500,000 white cells and the compartment assessed for its best-tracked LAIP holds at least 100 events.

Every value was computed from the files; no published or remembered value was used, and no file under /data was changed. The tables and the masks come from the same event masks, so every number in the tables recomputes from the masks.

## Results (as in patients.csv)

"""


def write_method():
    import csv
    with open(f"{OUT}/patients.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    lines = [f"- {r['case']}: MRD {r['mrd_percent']} percent, {r['call']}" for r in rows]
    with open(METHOD, "w") as fh:
        fh.write(METHOD_TEXT + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
    write_method()
