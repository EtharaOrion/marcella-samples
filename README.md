<p align="center"><img src="images/hero.svg" alt="Marcella" width="720"></p>

# Marcella: samples

<p align="center"><b>The samples lane: 0 of 30 Harbor task bundles.</b></p>

<p align="center"><a href="#summary"><img src="https://img.shields.io/badge/bundles-0_of_30-845EF7" alt="bundles: 0 of 30"></a> <a href="#evidence-status"><img src="https://img.shields.io/badge/sealed-0-845EF7" alt="sealed: 0"></a> <a href="#difficulty-tiers"><img src="https://img.shields.io/badge/difficulty-measured-845EF7" alt="difficulty: measured"></a></p>

<p align="center"><sub><a href="#abstract">Abstract</a> | <a href="#summary">Summary</a> | <a href="#difficulty-tiers">Difficulty tiers</a> | <a href="#evidence-status">Evidence status</a> | <a href="#coverage">Coverage</a> | <a href="#dataset-structure">Dataset structure</a> | <a href="#verification-and-quality-assurance">Verification and quality assurance</a> | <a href="#reproduction">Reproduction</a> | <a href="#cite">Cite</a> | <a href="#license">License</a> | <a href="#contact">Contact</a></sub></p>

## Abstract

The curated lane of this corpus: at most 30 Harbor task bundles, every anchor seated first and every other bundle in seal order. Bundles past that ceiling live in `delivery/`.

Each bundle is one Harbor task in a directory named by its content-derived uuid5, so the name doubles as an integrity check. This page is rendered from the resident bundles on every reconcile; a value a bundle does not carry reads `absent`, and the page never fills one in.

## Summary

| Property | Value |
| --- | --- |
| Bundles | 0 of 30 |
| Sealed | 0 of 0 |
| Registrations | none |
| Audit verdicts | none |
| Harbor schema | none |

## Difficulty tiers

Difficulty is measured by the signed pilot alone and never declared in a bundle, so this page states no tier a bundle claims.

## Evidence status

The verdict is the audit outcome recorded at the sealed digest, and `none` means no verdict has landed for that digest yet. Only an authoring run removes a bundle from this lane, so removal waits for the next one.

## Coverage

No resident bundle declares a keyword.

## Dataset structure

No bundle is resident under `samples/`.

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#131a33","primaryTextColor":"#e8ecff","primaryBorderColor":"#845EF7","lineColor":"#22d3ee","fontFamily":"monospace"}}}%%
flowchart LR
    staging["staging/"]
    staging --> samples["samples/<br/>0 of 30"]
    samples --> delivery["delivery/<br/>0 of 10000"]
    delivery --> stock["stock/<br/>0 of 10000"]
```

## Verification and quality assurance

Each bundle's signed provenance carrier holds its screening roots, screening instant, and absolute expiry. Placement moves that carrier into the private derivation set, which this page never reads, so reconcile lists no root it cannot verify here.

## Reproduction

Each bundle directory is a complete Harbor task: `task.toml` is the runner manifest, `instruction.md` the objective, `environment/` the sandbox image, and `tests/` the verifier. Point a Harbor runner at one bundle directory to reproduce it; `solution/` stays private.

## Cite

```bibtex
@misc{marcella2026,
  title        = {Marcella: Terminal-Bench Science 0.1 as a Hardened Reinforcement-Learning Evaluation Environment},
  author       = {Ethara.AI},
  year         = {2026},
  note         = {Wraps Terminal-Bench Science 0.1 (Harbor dataset terminal-bench-science/terminal-bench-science, 70 tasks, Apache-2.0). Harness pinned at commit 6e60de2f32727c095aac498f17c1863ef4b58181. Disposition: STALE, zero signed pilots.}
}
```

## License

Code is released under the [MIT License](LICENSE). Environment specifications are released under CC-BY-4.0. The wrapped benchmark (Terminal-Bench Science 0.1) retains its original Apache-2.0 license.

*Copyright 2026 Ethara.AI*

## Contact

[Ethara AI on GitHub](https://github.com/Ethara-Ai), [SECURITY.md](SECURITY.md) for a private report, and [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution route.

Security disclosures: security@ethara.ai

Code of conduct matters: conduct@ethara.ai

Copyright (c) 2026 Green Rider Technology LLP (Ethara AI). All rights reserved.
