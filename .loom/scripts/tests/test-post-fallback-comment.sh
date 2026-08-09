#!/usr/bin/env bash
# test-post-fallback-comment.sh — unit tests for post-fallback-comment.sh (#144).
#
# post-fallback-comment.sh exists because the
# `<!-- loom:fallback-evaluated sha=... -->` marker that drives
# judge-fallback-guard.sh's lifetime cap used to be appended by prompt
# compliance alone: judge.md showed an example heredoc ending in the marker and
# every fallback-mode Judge pass had to reproduce it verbatim. On
# gf180-temp-por PR #118 only 2 of 44 fallback-mode comments actually did, so
# the cap never fired. This script appends the marker programmatically; these
# tests are what make that guarantee load-bearing rather than aspirational.
#
# Black-box test: `gh` is stubbed on PATH and the real script is invoked as a
# subprocess. The stub records the body it was asked to post so the composed
# text can be asserted on. Mirrors the stubbing pattern in
# test-judge-fallback-cap.sh.
#
# Usage:
#   ./.loom/scripts/tests/test-post-fallback-comment.sh

set -uo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "$TEST_DIR/.." && pwd)"
POSTER="$SCRIPTS_DIR/post-fallback-comment.sh"

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

assert_not_contains() {
    local haystack="$1" needle="$2" msg="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    if printf '%s' "$haystack" | grep -qF -- "$needle"; then
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $msg"
        echo "    Unexpected substring: '$needle'"
        echo "    In: '$haystack'"
    else
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $msg"
    fi
}

if [[ ! -x "$POSTER" ]]; then
    echo -e "${RED}FATAL${NC}: $POSTER not found or not executable" >&2
    exit 2
fi

STUB_DIR="$(mktemp -d)"
trap 'rm -rf "$STUB_DIR" 2>/dev/null || true' EXIT

# --- Stub gh on PATH ---------------------------------------------------
#   gh pr view <N> --json headRefOid --jq .headRefOid
#       -> contents of $STUB_DIR/head-sha-<N> (default: a canned hex sha);
#          fails if $STUB_DIR/pr-view-fail-<N> exists.
#   gh pr comment <N> --body-file -
#       -> records stdin to $STUB_DIR/posted-<N>.txt, prints a URL;
#          fails if $STUB_DIR/comment-fail-<N> exists.
cat > "$STUB_DIR/gh" <<'STUB'
#!/usr/bin/env bash
S="${LOOM_TEST_STUB_DIR:?stub gh: LOOM_TEST_STUB_DIR not set}"
if [[ "$1" == "pr" && "$2" == "view" ]]; then
  n="$3"
  if [[ -f "$S/pr-view-fail-$n" ]]; then
    echo "stub gh: pr view failed" >&2
    exit 1
  fi
  # Benign stderr chatter on a SUCCESSFUL call — the script must not fold it
  # into the SHA it parses from stdout.
  [[ -f "$S/pr-view-stderr-$n" ]] && echo "gh: A new release of gh is available" >&2
  if [[ -f "$S/head-sha-$n" ]]; then cat "$S/head-sha-$n"; else echo "abc123abc123abc123abc123abc123abc123abcd"; fi
  exit 0
fi
if [[ "$1" == "pr" && "$2" == "comment" ]]; then
  n="$3"
  if [[ -f "$S/comment-fail-$n" ]]; then
    echo "stub gh: comment failed" >&2
    exit 1
  fi
  cat > "$S/posted-$n.txt"
  echo "https://github.com/o/r/pull/$n#issuecomment-1"
  exit 0
fi
echo "stub gh: unhandled args: $*" >&2
exit 3
STUB
chmod +x "$STUB_DIR/gh"

export LOOM_TEST_STUB_DIR="$STUB_DIR"
export PATH="$STUB_DIR:$PATH"

reset_state() {
    rm -f "$STUB_DIR"/head-sha-* "$STUB_DIR"/posted-*.txt
    rm -f "$STUB_DIR"/pr-view-fail-* "$STUB_DIR"/comment-fail-* "$STUB_DIR"/pr-view-stderr-*
}

run_poster() {
    OUT="$("$POSTER" "$@" 2>"$STUB_DIR/stderr.log")"
    RC=$?
    ERR="$(cat "$STUB_DIR/stderr.log" 2>/dev/null || true)"
}

echo "Testing post-fallback-comment.sh..."

# (a) The marker is appended programmatically — the caller supplies ONLY review
#     prose. This is the whole point of the script (#144).
reset_state
echo "1111111111111111111111111111111111111111" > "$STUB_DIR/head-sha-200"
run_poster 200 --body "Looks good — mechanical vendored-tool bump, scope matches the description."
POSTED="$(cat "$STUB_DIR/posted-200.txt" 2>/dev/null || true)"
assert_eq "0" "$RC" "(a) posts successfully -> exit 0"
assert_contains "$POSTED" "<!-- loom:fallback-evaluated sha=1111111111111111111111111111111111111111 -->" \
    "(a) marker appended with the resolved head SHA, without the caller writing it"
assert_contains "$POSTED" "mechanical vendored-tool bump" "(a) review prose preserved verbatim"

# (a2) The composed body is exactly what judge-fallback-guard.sh's STRICT
#      detector counts — the round trip that was broken before #144.
assert_contains "$POSTED" "<!-- loom:fallback-evaluated sha=" "(a2) STRICT marker present for the guard to count"

# (b) Body from stdin (the form judge.md uses, so review prose containing
#     backticks / $ / code fences never passes through shell expansion).
reset_state
echo "2222222222222222222222222222222222222222" > "$STUB_DIR/head-sha-201"
OUT="$(printf 'Evaluated in fallback mode.\n\nThe `$CURRENT_HEAD_SHA` heredoc hazard is gone: 100%% literal.\n' \
    | "$POSTER" 201 - 2>"$STUB_DIR/stderr.log")"
RC=$?
POSTED="$(cat "$STUB_DIR/posted-201.txt" 2>/dev/null || true)"
assert_eq "0" "$RC" "(b) stdin body -> exit 0"
assert_contains "$POSTED" 'The `$CURRENT_HEAD_SHA` heredoc hazard is gone' \
    "(b) backticks and \$ in review prose survive unexpanded"
assert_contains "$POSTED" "<!-- loom:fallback-evaluated sha=2222222222222222222222222222222222222222 -->" \
    "(b) marker still appended for a stdin body"

# (c) Idempotence: a body that ALREADY carries a marker is not double-marked
#     (a second marker would double-count against the lifetime cap).
reset_state
echo "3333333333333333333333333333333333333333" > "$STUB_DIR/head-sha-202"
run_poster 202 --body "$(printf 'Already marked.\n\n<!-- loom:fallback-evaluated sha=3333333333333333333333333333333333333333 -->')"
POSTED="$(cat "$STUB_DIR/posted-202.txt" 2>/dev/null || true)"
MARKER_HITS="$(grep -c 'loom:fallback-evaluated' <<<"$POSTED" || true)"
assert_eq "0" "$RC" "(c) pre-marked body -> exit 0"
assert_eq "1" "$MARKER_HITS" "(c) exactly one marker in the posted body (not stacked)"

# (d) --dry-run composes without posting: nothing reaches `gh pr comment`.
reset_state
echo "4444444444444444444444444444444444444444" > "$STUB_DIR/head-sha-203"
run_poster 203 --dry-run --body "Draft review prose."
assert_eq "0" "$RC" "(d) --dry-run -> exit 0"
assert_contains "$OUT" "<!-- loom:fallback-evaluated sha=4444444444444444444444444444444444444444 -->" \
    "(d) --dry-run prints the composed body including the marker"
assert_eq "false" "$([[ -f "$STUB_DIR/posted-203.txt" ]] && echo true || echo false)" \
    "(d) --dry-run posts nothing"

# (e) --sha override skips the `gh pr view` round trip (useful when the caller
#     already read HEAD_SHA out of judge-fallback-guard.sh's output).
reset_state
touch "$STUB_DIR/pr-view-fail-204"   # would fail if the script called it
run_poster 204 --sha "5555555555555555555555555555555555555555" --body "Prose."
POSTED="$(cat "$STUB_DIR/posted-204.txt" 2>/dev/null || true)"
assert_eq "0" "$RC" "(e) --sha override avoids gh pr view -> exit 0"
assert_contains "$POSTED" "<!-- loom:fallback-evaluated sha=5555555555555555555555555555555555555555 -->" \
    "(e) marker uses the overridden SHA"

# (f) An empty body is refused — a marker-only comment is noise, and the cap it
#     feeds is meant to count real evaluations.
reset_state
run_poster 205 --body "   "
assert_eq "1" "$RC" "(f) whitespace-only body -> exit 1"
assert_contains "$ERR" "refusing to post an empty fallback-mode comment" "(f) stderr explains the refusal"
assert_eq "false" "$([[ -f "$STUB_DIR/posted-205.txt" ]] && echo true || echo false)" "(f) nothing posted"

# (g) A non-hex SHA is refused rather than posting a marker that could never
#     match a real head SHA — the classic pre-#144 quoted-heredoc failure was
#     posting the literal text "sha=$CURRENT_HEAD_SHA", which silently made
#     every subsequent pass re-evaluate.
reset_state
run_poster 206 --sha '$CURRENT_HEAD_SHA' --body "Prose."
assert_eq "1" "$RC" "(g) non-hex SHA -> exit 1"
assert_contains "$ERR" "head SHA is not lowercase hex" "(g) stderr names the bad SHA"
assert_eq "false" "$([[ -f "$STUB_DIR/posted-206.txt" ]] && echo true || echo false)" "(g) nothing posted"

# (h) Benign stderr chatter on a SUCCESSFUL `gh pr view` must not corrupt the
#     parsed SHA (same stream-separation invariant judge-fallback-guard.sh
#     holds).
reset_state
echo "7777777777777777777777777777777777777777" > "$STUB_DIR/head-sha-207"
touch "$STUB_DIR/pr-view-stderr-207"
run_poster 207 --body "Prose."
POSTED="$(cat "$STUB_DIR/posted-207.txt" 2>/dev/null || true)"
assert_eq "0" "$RC" "(h) stderr chatter on gh pr view -> still exit 0"
assert_contains "$POSTED" "<!-- loom:fallback-evaluated sha=7777777777777777777777777777777777777777 -->" \
    "(h) SHA parsed from stdout only"
assert_not_contains "$POSTED" "new release of gh" "(h) stderr chatter never leaks into the comment body"

# (i) A failing `gh pr comment` surfaces as exit 1, not a silent success — the
#     Judge must be able to tell the marker did NOT land.
reset_state
echo "8888888888888888888888888888888888888888" > "$STUB_DIR/head-sha-208"
touch "$STUB_DIR/comment-fail-208"
run_poster 208 --body "Prose."
assert_eq "1" "$RC" "(i) gh pr comment failure -> exit 1"
assert_contains "$ERR" "gh pr comment" "(i) stderr names the failing gh call"

# (j) Usage errors: non-numeric PR, and mutually exclusive body sources.
reset_state
run_poster not-a-number --body "Prose."
assert_eq "1" "$RC" "(j) non-numeric PR number -> exit 1"
assert_contains "$ERR" "numeric PR number is required" "(j) stderr explains the usage error"

reset_state
run_poster 209 --body "Prose." --body-file /dev/null
assert_eq "1" "$RC" "(j2) --body plus --body-file -> exit 1"
assert_contains "$ERR" "mutually exclusive" "(j2) stderr names the conflict"

# --- Summary -------------------------------------------------------------
echo ""
echo "Results: $TESTS_PASSED/$TESTS_RUN passed"
if [[ "$TESTS_FAILED" -gt 0 ]]; then
    echo -e "${RED}$TESTS_FAILED test(s) failed${NC}"
    exit 1
fi
echo -e "${GREEN}All tests passed${NC}"
