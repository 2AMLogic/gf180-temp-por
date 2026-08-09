#!/usr/bin/env bash
# test-post-fallback-comment.sh - Unit tests for post-fallback-comment.sh (#144).
#
# post-fallback-comment.sh moves the Judge fallback-mode marker-append step
# out of a free-form `gh pr comment` heredoc (which an LLM had to faithfully
# reproduce verbatim on every pass — and on PR #118 in this repo, ~44 of ~45
# fallback-mode comments over ~54h did NOT reproduce it, defeating
# judge-fallback-guard.sh's lifetime cap and velocity alert) into a real,
# testable script that appends the marker programmatically.
#
# This is a black-box test: post-fallback-comment.sh is a full CLI script (no
# functions to source), so we stub `gh` on PATH and invoke the real script as
# a subprocess, asserting on stdout/exit code and the composed body it would
# post. Mirrors the stubbing pattern in test-judge-fallback-cap.sh.
#
# Usage:
#   ./.loom/scripts/tests/test-post-fallback-comment.sh

set -uo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$TEST_DIR/.." && pwd)"
SCRIPT="$SCRIPTS_DIR/post-fallback-comment.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

assert_eq() {
    local expected="$1" actual="$2" msg="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    if [[ "$expected" == "$actual" ]]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $msg"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $msg"
        echo "    Expected: '$expected'"
        echo "    Actual:   '$actual'"
    fi
}

assert_contains() {
    local haystack="$1" needle="$2" msg="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    if printf '%s' "$haystack" | grep -qF -- "$needle"; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $msg"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $msg"
        echo "    Expected substring: '$needle'"
        echo "    In: '$haystack'"
    fi
}

if [[ ! -x "$SCRIPT" ]]; then
    echo -e "${RED}FATAL${NC}: $SCRIPT not found or not executable" >&2
    exit 2
fi

STUB_DIR="$(mktemp -d)"
trap 'rm -rf "$STUB_DIR" 2>/dev/null || true' EXIT

# --- Stub gh on PATH ---------------------------------------------------
#   gh pr view <N> --json headRefOid -> cat $STUB_DIR/pr-<N>.json
#                                        (fails if pr-view-fail-<N> exists)
#   gh pr comment <N> --body-file <path> -> copies <path> to
#                                        $STUB_DIR/posted-<N>.txt
#                                        (fails if comment-fail-<N> exists)
cat > "$STUB_DIR/gh" <<'STUB'
#!/usr/bin/env bash
STUB_DIR_FROM_ENV="${LOOM_TEST_STUB_DIR:?stub gh: LOOM_TEST_STUB_DIR not set}"
case "$1" in
  pr)
    case "$2" in
      view)
        pr_num="$3"
        if [[ -f "$STUB_DIR_FROM_ENV/pr-view-fail-$pr_num" ]]; then
          echo "stub gh: pr view failed" >&2
          exit 1
        fi
        canned="$STUB_DIR_FROM_ENV/pr-$pr_num.json"
        if [[ -f "$canned" ]]; then cat "$canned"; else echo '{"headRefOid":"0000000000000000000000000000000000000000"}'; fi
        exit 0
        ;;
      comment)
        pr_num="$3"
        body_file=""
        shift 3
        while [[ $# -gt 0 ]]; do
          case "$1" in
            --body-file) body_file="$2"; shift 2 ;;
            *) shift ;;
          esac
        done
        if [[ -f "$STUB_DIR_FROM_ENV/comment-fail-$pr_num" ]]; then
          echo "stub gh: pr comment failed" >&2
          exit 1
        fi
        if [[ -z "$body_file" || ! -f "$body_file" ]]; then
          echo "stub gh: pr comment missing --body-file" >&2
          exit 3
        fi
        cp "$body_file" "$STUB_DIR_FROM_ENV/posted-$pr_num.txt"
        exit 0
        ;;
      *)
        echo "stub gh: unhandled pr args: $*" >&2
        exit 3
        ;;
    esac
    ;;
  *)
    echo "stub gh: unhandled args: $*" >&2
    exit 3
    ;;
esac
STUB
chmod +x "$STUB_DIR/gh"

export LOOM_TEST_STUB_DIR="$STUB_DIR"
export PATH="$STUB_DIR:$PATH"

reset_state() {
    rm -f "$STUB_DIR"/pr-*.json "$STUB_DIR"/posted-*.txt
    rm -f "$STUB_DIR"/pr-view-fail-* "$STUB_DIR"/comment-fail-*
}

run_script() {
    OUT="$("$SCRIPT" "$@" 2>"$STUB_DIR/stderr.log")"
    RC=$?
    ERR="$(cat "$STUB_DIR/stderr.log" 2>/dev/null || true)"
}

echo "Testing post-fallback-comment.sh..."

# (a) Basic case: --head-sha provided, marker appended, posted via
#     `gh pr comment --body-file`.
reset_state
BODY_A="$STUB_DIR/body-a.txt"
printf 'Code evaluation feedback...\n\nLooks fine.\n' > "$BODY_A"
run_script 200 "$BODY_A" --head-sha "1111111111111111111111111111111111111a"
assert_eq "0" "$RC" "(a) Basic post -> exit 0"
assert_contains "$OUT" "OK: posted fallback-mode comment on PR #200" "(a) stdout confirms posting"
POSTED_A="$(cat "$STUB_DIR/posted-200.txt" 2>/dev/null || true)"
assert_contains "$POSTED_A" "Looks fine." "(a) posted body preserves original prose"
assert_contains "$POSTED_A" "<!-- loom:fallback-evaluated sha=1111111111111111111111111111111111111a -->" "(a) posted body carries the exact marker"

# (b) No --head-sha given -> resolves via `gh pr view`.
reset_state
cat > "$STUB_DIR/pr-201.json" <<'EOF'
{"headRefOid":"2222222222222222222222222222222222222b"}
EOF
BODY_B="$STUB_DIR/body-b.txt"
printf 'Evaluation notes.\n' > "$BODY_B"
run_script 201 "$BODY_B"
assert_eq "0" "$RC" "(b) No --head-sha, resolved via gh pr view -> exit 0"
POSTED_B="$(cat "$STUB_DIR/posted-201.txt" 2>/dev/null || true)"
assert_contains "$POSTED_B" "<!-- loom:fallback-evaluated sha=2222222222222222222222222222222222222b -->" "(b) marker uses the SHA resolved from gh pr view"

# (c) --dry-run -> does NOT call `gh pr comment` (no posted-*.txt written),
#     but prints the composed body including the marker.
reset_state
BODY_C="$STUB_DIR/body-c.txt"
printf 'Dry run body.\n' > "$BODY_C"
run_script 202 "$BODY_C" --head-sha "3333333333333333333333333333333333333c" --dry-run
assert_eq "0" "$RC" "(c) --dry-run -> exit 0"
assert_eq "0" "$([[ -f "$STUB_DIR/posted-202.txt" ]] && echo 1 || echo 0)" "(c) --dry-run does not call gh pr comment"
assert_contains "$OUT" "<!-- loom:fallback-evaluated sha=3333333333333333333333333333333333333c -->" "(c) --dry-run output shows the composed marker"

# (d) Idempotent: body already ends with the correct marker for this exact
#     sha -> the marker must NOT be duplicated.
reset_state
BODY_D="$STUB_DIR/body-d.txt"
printf 'Already marked.\n\n<!-- loom:fallback-evaluated sha=4444444444444444444444444444444444444d -->\n' > "$BODY_D"
run_script 203 "$BODY_D" --head-sha "4444444444444444444444444444444444444d"
assert_eq "0" "$RC" "(d) Already-marked body -> exit 0"
MARKER_OCCURRENCES_D="$(grep -c -- '<!-- loom:fallback-evaluated sha=4444444444444444444444444444444444444d -->' "$STUB_DIR/posted-203.txt" 2>/dev/null || echo 0)"
assert_eq "1" "$MARKER_OCCURRENCES_D" "(d) marker is NOT duplicated when already present for the same sha"

# (e) Missing body-file -> usage error, exit 1.
reset_state
run_script 204 "$STUB_DIR/does-not-exist.txt" --head-sha "5555555555555555555555555555555555555e"
assert_eq "1" "$RC" "(e) Missing body-file -> exit 1"
assert_contains "$ERR" "body-file not found" "(e) stderr explains the missing body-file"

# (f) Non-numeric PR number -> usage error, exit 1.
reset_state
BODY_F="$STUB_DIR/body-f.txt"
printf 'x\n' > "$BODY_F"
run_script not-a-number "$BODY_F"
assert_eq "1" "$RC" "(f) Non-numeric PR number -> exit 1"
assert_contains "$ERR" "numeric PR number is required" "(f) stderr explains the usage error"

# (g) `gh pr comment` failure -> exit 1, error names the failing call.
reset_state
BODY_G="$STUB_DIR/body-g.txt"
printf 'Some feedback.\n' > "$BODY_G"
touch "$STUB_DIR/comment-fail-205"
run_script 205 "$BODY_G" --head-sha "6666666666666666666666666666666666666f"
assert_eq "1" "$RC" "(g) gh pr comment failure -> exit 1"
assert_contains "$ERR" "gh pr comment" "(g) stderr names the failing gh call"

# (h) `gh pr view` failure when resolving head SHA (no --head-sha given) ->
#     exit 1, error names the failing call.
reset_state
touch "$STUB_DIR/pr-view-fail-206"
BODY_H="$STUB_DIR/body-h.txt"
printf 'Some feedback.\n' > "$BODY_H"
run_script 206 "$BODY_H"
assert_eq "1" "$RC" "(h) gh pr view failure (resolving head SHA) -> exit 1"
assert_contains "$ERR" "gh pr view" "(h) stderr names the failing gh call"

# --- Summary -------------------------------------------------------------
echo ""
echo "Results: $TESTS_PASSED/$TESTS_RUN passed"
if [[ "$TESTS_FAILED" -gt 0 ]]; then
    echo -e "${RED}$TESTS_FAILED test(s) failed${NC}"
    exit 1
fi
echo -e "${GREEN}All tests passed${NC}"
