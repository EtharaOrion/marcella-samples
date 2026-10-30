#!/usr/bin/env bash
# Selects which Reward Kit run stands for the grading mode; Reward Kit writes every reward byte.
#   control: the compiled score alone, no judge, no network.
#   live:    the judge is called only when the compiled score is 1.0 (reward 0.80 + 0.20 judge); below that no
#            judge is called and the judge input scores 0 (reward 0.80 x compiled).
set -euo pipefail
MODE="${RUBRIC_MODE:-control}"
TESTS="${TESTS_DIR:-/tests}"
WORKSPACE="${WORKSPACE:-/app}"
OUT=/logs/verifier
REWARD_FILE=/logs/verifier/reward.json
mkdir -p "$OUT"
compiled="$(mktemp -d)"
cp "$TESTS/test_output.py" "$compiled/test_output.py"
# The compiled-only rubric is the shipped reward.toml without the judge weighting.
sed '/^weights/d' "$TESTS/reward.toml" > "$compiled/reward.toml"
case "$MODE" in
  control)
    exec python -m rewardkit "$compiled" --workspace "$WORKSPACE" --output "$REWARD_FILE"
    ;;
  live)
    : "${REWARDKIT_JUDGE:?live mode needs REWARDKIT_JUDGE set to one council member}"
    python -m rewardkit "$compiled" --workspace "$WORKSPACE" --output "$OUT/compiled.json"
    if python -c 'import json, sys; sys.exit(0 if float(json.load(open(sys.argv[1]))["reward"]) == 1.0 else 1)' "$OUT/compiled.json"; then
      exec python -m rewardkit "$TESTS" --workspace "$WORKSPACE" --output "$REWARD_FILE"
    fi
    nojudge="$(mktemp -d)"
    cp "$TESTS/test_output.py" "$nojudge/test_output.py"
    cp "$TESTS/judge_not_called.py.in" "$nojudge/judge.py"
    cp "$TESTS/reward.toml" "$nojudge/reward.toml"
    exec python -m rewardkit "$nojudge" --workspace "$WORKSPACE" --output "$REWARD_FILE"
    ;;
  *)
    echo "unknown RUBRIC_MODE=$MODE" >&2
    exit 2
    ;;
esac
