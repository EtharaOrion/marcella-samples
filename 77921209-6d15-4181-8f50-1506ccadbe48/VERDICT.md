# VERDICT

CRUCIBLE report for run `crucible-chirayu-gaur-ethara-ai-20261022t061836z-c6c2b4`, audit of sealed bundle `77921209-6d15-4181-8f50-1506ccadbe48` (AML measurable residual disease LAIP tracking, seal `f24cb9ab1a14`) and its two author-side Codex gpt-6.1-sol rollouts, of which trial `77921209-6d15-4181-8f50-1506ccadbe48` was audited in full, 2026-10-30.

## Executive summary

- 🟡 Judged item `j_method_matches_tables` expects case calls and MRD values in method.md, but instruction.md asks only for an account of the gates and counts (G-STMT-RECONCILE).
- 🟡 The six credited cases are defined as "close to the cut-off". `grading.json` lists them without their expert MRD values or the band that defines "close", so their membership cannot be checked from shipped files. One of this rollout's two failed Part 2 units, the case_24 ceiling, rests on that list (G-KEY-PROVENANCE).
- 🟡 The trial folder carries two rewards: the task-defined 0.1944 and 0.3412 from a forced diagnostic judge call that `test.sh` does not make below a compiled score of 1.0 (G-REWARD-PROVENANCE).
- 🟢 The data recipe wrote the FCS files with FlowIO 1.4.0, while the agent image ships 1.3.0. The rollout read every tube under 1.3.0 without error (G-ENV-PIN).
- 🟢 The `solution/oracle.py` docstring says it writes `tubes.csv` and `laips.csv`, but the code writes only the four required tables and the masks (G-ORACLE-DOC).
- ✅ Rollout `CJdAopy` is a valid reasoning failure with no reward hacking. The shipped grader recomputes 0.19438596 from its artifacts, `/data` matches all 315 shipped digests, and no tool call touches `/tests`, the key, `/solution`, `/logs` or the network. The failure is the task's intended trap: a follow-up CD34 gate admitted normal maturing myeloid cells as leukaemic cells, so case_23 was called POSITIVE at 0.2434% against an expert value of 0.0027%.
- ✅ The statement and grader are aligned, a second agent-written solution scored compiled 1.0, the judge is gated behind a full compiled score, and the verifier ran in a separate container.
- Gate summary: 13 audit checks, 8 pass, 5 findings and 7 coverage gaps. No finding caps the bundle, so the outcome is accepted with tests-side and solution-side fixes, and the rollout stands as a genuine reasoning failure.

## Disposition

HOLD

## Findings

### Grader discrimination (class 19)

- ✅ G-ALT-SOLUTION, acknowledged clean: a second agent-written solution in the same job (`npSpvze`) used different gate features and a different training pool and scored compiled 1.0 (part shares 0.9649 / 1.0 / 1.0). Full reward is not tied to the reference implementation.
- ✅ G-MUTANT-LADDER, acknowledged clean by design: any failing part caps the compiled score at 0.2, as task.toml declares. This near-miss scored 0.1944 (part shares 0.9649 / 0.9649 / 1.0, 2 of 24 patient units failed). For comparison, TRUTH.md records KW1 (copied gates) at 0.1888 with 6 of 24 failed, and KW2 (uncompensated data) at 0.186. The part shares carry the finer signal.

### Statement and grader integrity (class 18)

- 🟡 G-STMT-RECONCILE, retained: `judge.toml` `j_method_matches_tables` and `reference.md` expect method.md to state every case call and MRD value, but `instruction.md` line 35 asks only for "a short plain-text account of how you obtained the gates and counts". Neither rollout's method.md lists the values, and the forced judge scored this item "no". The compiled grader is unaffected; the item can cost at most 0.2 / 14 ≈ 0.014 of the live reward.
- 🟢 G-ORACLE-DOC, retained: `solution/oracle.py` line 12 says the oracle writes `tubes.csv, laips.csv, the four tables and the event masks`. The code writes `diagnosis_laips.csv`, `followup_tubes.csv`, `followup_laips.csv`, `patients.csv` and the masks, so the first two names are stale. Behaviour is unaffected.
- ✅ G-STMT-LITERAL, acknowledged clean: every rule in the instruction matches `test_output.py`:
  - white-cell denominator; largest single LAIP per tube, ties to the lower number; largest tube per case;
  - positive at 0.1% or more;
  - negativity needs more than 500,000 WBC and at least 100 compartment events, with BLAST as the default compartment;
  - Part 1: F1 0.8 on 90% of graded LAIPs;
  - Part 2: positive MRD within a factor of 5, credited cases at or below 1.0%, WBC within 20% in 90% of tubes;
  - recomputation tolerance 1e-6 relative.

### Domain integrity and reward provenance (class 6)

- 🟡 G-KEY-PROVENANCE, retained: `instruction.md` defines a credited case as one "whose expert MRD lies close to the cut-off". `grading.json`, `TRUTH.md` and `grounding.yaml` list case_11, case_12, case_17, case_24, case_27 and case_28 with the 1.0% ceiling, but carry neither their expert MRD values nor the band that defines "close". `recompute.py` checks the expert values of determinable cases only, so the credited list cannot be re-derived from shipped files.
- 🟡 G-REWARD-PROVENANCE, retained: `verifier/` records 0.1944 (`RUBRIC_MODE=control`, compiled score only). `verifier-live-opus-5-5/` records 0.3412 = 0.8 × 0.1944 + 0.2 × 0.9286, from a judge call its `run.log` marks as forced. In live mode `test.sh` calls the judge only at a compiled score of 1.0, so the task-defined live reward is 0.8 × 0.1944 = 0.1555.
- ✅ G-JUDGE-EVIDENCE, acknowledged clean: `test.sh` calls the judge only at a compiled score of 1.0, so judged items cannot lift a failing submission. The forced diagnostic judge passed `j_normal_progenitors` on method.md wording that the run's own tables contradict:
  - the refinement step removed 4.8% of case_24 P2 L2 candidates and 0.7% of P3 L3 candidates;
  - `followup_laips.csv` counts 55.6% and 76.1% of those CD34 compartments as LAIP.

  That is the failure this gate is there to stop.
- ✅ G-ROLLOUT-INTEGRITY, acknowledged clean: replaying `tests/test_output.py` with `tests/key` on the collected artifacts reproduces score 0.19438596491228075 and every part share. The collected `/data` manifest equals `data.sha256.json` on all 315 files. Re-running the agent's recorded gate code reproduces its follow-up CD34 masks bit-for-bit.
- ✅ G-ROLLOUT-ISOLATION, acknowledged clean: all 46 tool calls read only `/data` and write only `/app`. None touches `/tests`, `/opt/mrd-key`, `/solution`, `/logs` or the network. The final message's claims (all consistency checks passed; `/data` unchanged) are both true.
- ✅ G-ROLLOUT-OUTCOME, acknowledged valid failure:
  - **Scores:**
    - Part 1: 55 of 57 graded LAIPs reach F1 0.8 or more. The misses are case_05/L3 at 0.798 and case_06/L3 at 0.593.
    - Part 2: 55 of 57 units met. The failures are the case_23 call (0.2434% against an expert value of 0.0027%) and the case_24 ceiling (1.6205% against 1.0%). All 33 white-cell counts are within 20% of the expert counts (largest deviation 16.4%).
    - Part 3: 1.0.
  - **Cause, the CD34 gate:** the run trained a per-case follow-up CD34 gate on the leukaemia-dominated diagnosis tube, using only SSC-A, CD45 and CD34.
    - On 4 healthy donors this gate has precision 0.63 to 0.68 and selects 1.43 to 1.58 times the laboratory's CD34 count.
    - Its follow-up CD34 compartments are 1.31 times (case_23 P2) to 3.14 times (case_24 P1) the size of the sibling run's working gate.
  - **Cause, wrong cells counted:** the counted cells do not match the diagnosis phenotype (arcsinh medians).
    - case_24 L2 and L3: CD117 1.0 to 1.1 in the counted follow-up cells, against 4.5 in the laboratory's LAIP cells.
    - case_23 L1: CD34 3.3 against 4.4, and CD13 2.8 against 4.2.
    - CD13 was never used as a hard gate.
    - The healthy reference was gated with the laboratory's gates rather than the model's own gates.
  - **Counterfactual:** restricting this run's own LAIP masks to the sibling run's CD34/CD117 gates gives case_23 0.0749% (NEGATIVE) and case_24 0.4842%, and every patient unit passes.
  - **Process:**
    - The run took 53 steps and 17 min 44 s of an 8 h budget, with 14,970 reasoning tokens.
    - It checked the white-cell gate on 5 donors, all of which were in its training data, but never checked the CD34/CD117 gates.
    - It generated `view_24.png` and never opened it.

### Supply-chain defects (class 5)

- 🟢 G-ENV-PIN, retained: `grounding.yaml` line 338 records the data recipe with `flowio: 1.4.0`, while `environment/requirements.lock.txt` line 7 pins `flowio==1.3.0` for the agent image. The rollout parsed every diagnosis, follow-up and normal tube with 1.3.0 without error, so no effect was observed.

### Agent-evaluator isolation and environment build (class 20)

- ✅ G-ISO-SEPARATE, acknowledged clean: the verifier ran in a separate container (`result.json` `verifier_environment_mode: separate`; `task.toml` `environment_mode = "separate"`), and `/app` was empty when the agent started.

## Coverage gaps

- The oracle (1.0), nop (0.0), 24 controls and 7 implementation variants that `task.toml` claims were not re-run. Only the shipped grader replay on this rollout was run.
- No adversary probes (special-casing, test edits, caching, evaluation detection) were run against the grader.
- No SBOM or vulnerability scan, image build or image inspection was done. Isolation evidence is limited to this trajectory and `result.json`.
- There is one judge sample, which was a forced diagnostic call by a single model (Opus 5.5, medium effort). Judge reliability was not measured.
- The sibling trial `npSpvze` (compiled 1.0) was not audited for shortcuts and is no longer in the workspace. Its figures here come from the earlier read.
- The model's reasoning is encrypted in the session log, so this verdict rests on its actions, code and outputs.
- The seal `f24cb9ab1a14` is the task checksum recorded in `result.json`. It was not re-derived from the local bundle bytes.

## Escalations

- **Fixes under a new uuid superseding the audited bundle:**
  - reword `j_method_matches_tables` to "states no call or MRD value that contradicts patients.csv";
  - add the credited band and the six credited expert MRD values to `grading.json`, and have `recompute.py` check them;
  - correct the `oracle.py` docstring;
  - note in `grounding.yaml` that the files are written with FlowIO 1.4.0 and read with 1.3.0.

  `instruction.md` and `environment/` stay byte-identical, so no rollout rerun is needed.
- **Record the reward:** 0.1944 (control) and 0.1555 (live) are this trial's rewards. Label `verifier-live-opus-5-5/` as a forced-judge diagnostic and exclude it from aggregates.
- **Before release:** re-run the oracle and nop on the frozen bytes, run adversary probes, and scan both images.

## Flag legend

- 🔴 retained finding that caps the bundle outcome; 🟡 retained finding to fix or accept; 🟢 low-severity retained finding; ✅ acknowledged clean.
