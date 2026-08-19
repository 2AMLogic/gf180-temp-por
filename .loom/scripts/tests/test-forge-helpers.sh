#!/usr/bin/env bash
# test-forge-helpers.sh - Unit tests for forge-helpers.sh dispatch logic
#
# Tests forge detection, host extraction, and verifies that forge dispatch
# functions route to the correct backend based on FORGE_TYPE.
#
# Usage:
#   ./.loom/scripts/tests/test-forge-helpers.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPERS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

assert_eq() {
    local expected="$1"
    local actual="$2"
    local msg="$3"
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

# --- Test _extract_host ---
echo "Testing _extract_host..."

# Need to source the library
source "$HELPERS_DIR/lib/forge-helpers.sh"

# Reset state for testing
FORGE_TYPE=""

result=$(_extract_host "git@github.com:owner/repo.git")
assert_eq "github.com" "$result" "SSH GitHub URL"

result=$(_extract_host "https://github.com/owner/repo.git")
assert_eq "github.com" "$result" "HTTPS GitHub URL"

result=$(_extract_host "git@gitea.example.com:owner/repo.git")
assert_eq "gitea.example.com" "$result" "SSH Gitea URL"

result=$(_extract_host "https://gitea.example.com/owner/repo")
assert_eq "gitea.example.com" "$result" "HTTPS Gitea URL (no .git)"

result=$(_extract_host "not-a-url")
assert_eq "" "$result" "Invalid URL returns empty"

# --- Test forge_detect with env var ---
echo ""
echo "Testing forge_detect with LOOM_FORGE_TYPE env var..."

FORGE_TYPE=""
LOOM_FORGE_TYPE="github" forge_detect
assert_eq "github" "$FORGE_TYPE" "LOOM_FORGE_TYPE=github"

FORGE_TYPE=""
LOOM_FORGE_TYPE="gitea" forge_detect 2>/dev/null || true
# Note: this may fail if no Gitea config, but FORGE_TYPE should still be set
assert_eq "gitea" "$FORGE_TYPE" "LOOM_FORGE_TYPE=gitea"

# --- Test forge_split_nwo ---
echo ""
echo "Testing forge_split_nwo..."

forge_split_nwo "myowner/myrepo"
assert_eq "myowner" "$FORGE_OWNER" "Split NWO owner"
assert_eq "myrepo" "$FORGE_REPO" "Split NWO repo"

forge_split_nwo "org/complex-repo-name"
assert_eq "org" "$FORGE_OWNER" "Split NWO org owner"
assert_eq "complex-repo-name" "$FORGE_REPO" "Split NWO complex repo"

# --- Test forge detection defaults to github ---
echo ""
echo "Testing forge_detect defaults..."

FORGE_TYPE=""
# Unset LOOM_FORGE_TYPE to test auto-detection
unset LOOM_FORGE_TYPE 2>/dev/null || true
export LOOM_FORGE_TYPE=""
forge_detect
# In this repo (github.com remote), should detect as github
assert_eq "github" "$FORGE_TYPE" "Auto-detect defaults to github for github.com remote"

# --- Test forge_get_repo_nwo for github ---
echo ""
echo "Testing forge_get_repo_nwo..."

FORGE_TYPE="github"
result=$(forge_get_repo_nwo "gh" 2>/dev/null || echo "")
# Should return non-empty for this repo
if [[ -n "$result" ]]; then
    TESTS_RUN=$((TESTS_RUN + 1))
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: forge_get_repo_nwo returns non-empty for GitHub ($result)"
else
    TESTS_RUN=$((TESTS_RUN + 1))
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: forge_get_repo_nwo returned empty"
fi

# --- Test forge_pr_close_targets (Gitea fallback regex path) ---
# These tests exercise the regex fallback that is used for Gitea (and that
# serves as the safety net behavior we want to guarantee even without the
# GitHub GraphQL path). We test the regex directly to avoid needing a live
# forge or stubbing `gh pr view`.
echo ""
echo "Testing forge_pr_close_targets regex (Gitea fallback semantics)..."

# Helper: run the same regex used inside forge_pr_close_targets's Gitea branch.
# Note: `|| true` neutralizes grep's exit code 1 (no match) under `set -e`.
_close_targets_regex() {
    local body="$1"
    { echo "$body" \
        | grep -Eoi '\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b[[:space:]]+#[0-9]+' \
        | grep -Eo '[0-9]+' \
        | sort -un \
        | tr '\n' ' ' \
        | sed 's/ $//'; } || true
}

result=$(_close_targets_regex "Closes #42")
assert_eq "42" "$result" "Closes #N matches"

result=$(_close_targets_regex "Fixes #42")
assert_eq "42" "$result" "Fixes #N matches"

result=$(_close_targets_regex "Resolves #42")
assert_eq "42" "$result" "Resolves #N matches"

result=$(_close_targets_regex "closes #42")
assert_eq "42" "$result" "lowercase closes #N matches (case-insensitive)"

result=$(_close_targets_regex "Closed #42")
assert_eq "42" "$result" "tense variant 'Closed #N' matches"

result=$(_close_targets_regex "Updates #42")
assert_eq "" "$result" "Updates #N is correctly ignored (the bug from #3267)"

result=$(_close_targets_regex "See #42")
assert_eq "" "$result" "See #N is correctly ignored"

result=$(_close_targets_regex "References #42")
assert_eq "" "$result" "References #N is correctly ignored"

result=$(_close_targets_regex "Discloses #42")
assert_eq "" "$result" "substring trap 'Discloses #N' is correctly ignored"

result=$(_close_targets_regex "")
assert_eq "" "$result" "empty body returns nothing"

result=$(_close_targets_regex "Closes #1, Fixes #2, Resolves #3")
assert_eq "1 2 3" "$result" "multiple closing keywords match all targets"

result=$(_close_targets_regex "Closes #5. Updates #6.")
assert_eq "5" "$result" "mixed Closes/Updates closes only Closes target"

result=$(_close_targets_regex "Closes #7 and Fixes #7")
assert_eq "7" "$result" "duplicate references are de-duplicated"

# --- Test forge_pr_close_targets dispatches to GitHub path ---
echo ""
echo "Testing forge_pr_close_targets GitHub dispatch (using stub gh)..."

# Create a stub `gh` that captures the closingIssuesReferences invocation
# and returns canned output. Place it on PATH ahead of the real gh.
STUB_DIR=$(mktemp -d)
cat > "$STUB_DIR/gh" <<'STUB'
#!/usr/bin/env bash
# Stub gh that only handles the close-targets query.
# Usage: gh pr view <N> --json closingIssuesReferences --jq '.closingIssuesReferences[].number'
if [[ "$1" == "pr" && "$2" == "view" && "$*" == *"closingIssuesReferences"* ]]; then
  printf '123\n456\n'
  exit 0
fi
exit 1
STUB
chmod +x "$STUB_DIR/gh"

FORGE_TYPE="github"
result=$(forge_pr_close_targets "999" "$STUB_DIR/gh" | tr '\n' ' ' | sed 's/ $//')
assert_eq "123 456" "$result" "GitHub path delegates to gh pr view --json closingIssuesReferences"

rm -rf "$STUB_DIR"

# --- Test forge_get_pr_nocache does not pass --no-cache to plain gh (issue #3547) ---
# Regression: `--no-cache` is a gh-cached WRAPPER flag, not a real `gh` flag.
# When gh-cached is absent and the plain `gh` fallback is used, passing
# --no-cache made `gh api` fail on the unknown flag; the error was swallowed by
# 2>/dev/null and callers substituted '{}', silently breaking merge verification
# and race-condition rechecks. forge_get_pr_nocache must therefore NOT pass
# --no-cache when the command basename is plain `gh` (plain `gh api` is already
# uncached), while still passing it for the gh-cached wrapper.
echo ""
echo "Testing forge_get_pr_nocache --no-cache handling (issue #3547)..."

NC_STUB_DIR=$(mktemp -d)

# Stub named exactly `gh`: emits valid PR JSON for `api ...`, but exits non-zero
# (as real gh does) if the unknown `--no-cache` flag is present. This proves the
# helper reaches the api call cleanly only when --no-cache is omitted.
cat > "$NC_STUB_DIR/gh" <<'STUB'
#!/usr/bin/env bash
for a in "$@"; do
  if [[ "$a" == "--no-cache" ]]; then
    echo "unknown flag: --no-cache" >&2
    exit 1
  fi
done
if [[ "$1" == "api" ]]; then
  printf '{"merged":true,"state":"closed"}\n'
  exit 0
fi
exit 1
STUB
chmod +x "$NC_STUB_DIR/gh"

# Stub named `gh-cached`: REQUIRES --no-cache to be present (proves the wrapper
# still receives the cache-bypass flag). Emits valid JSON when it is.
cat > "$NC_STUB_DIR/gh-cached" <<'STUB'
#!/usr/bin/env bash
has_no_cache=0
for a in "$@"; do
  [[ "$a" == "--no-cache" ]] && has_no_cache=1
done
if [[ "$has_no_cache" -ne 1 ]]; then
  echo "expected --no-cache" >&2
  exit 1
fi
printf '{"merged":true,"state":"closed"}\n'
exit 0
STUB
chmod +x "$NC_STUB_DIR/gh-cached"

FORGE_TYPE="github"

# Plain-gh path: helper must omit --no-cache and return real JSON.
nc_result=$(forge_get_pr_nocache "owner/repo" "123" "$NC_STUB_DIR/gh" 2>/dev/null | jq -r '.merged' 2>/dev/null || echo "")
assert_eq "true" "$nc_result" "forge_get_pr_nocache with plain gh omits --no-cache and returns real JSON"

# gh-cached path: helper must still pass --no-cache to the wrapper.
nc_cached_result=$(forge_get_pr_nocache "owner/repo" "123" "$NC_STUB_DIR/gh-cached" 2>/dev/null | jq -r '.merged' 2>/dev/null || echo "")
assert_eq "true" "$nc_cached_result" "forge_get_pr_nocache with gh-cached wrapper still passes --no-cache"

rm -rf "$NC_STUB_DIR"

# --- Test CI-status helpers stay UNCACHED (issue #4667) ---
# The sweep/judge/champion skills now route their hot discovery reads through
# gh-cached, but CI status is explicitly carved out: it is the read a verdict
# and a merge are gated on, so a cached green could predate the push that broke
# the build. forge_get_check_runs / forge_get_commit_status must therefore keep
# invoking plain `gh` from PATH — never a cache wrapper, and never with the
# wrapper-only `--no-cache` flag (the #3547 failure shape). This locks the
# carve-out in at the library level so a future "cache everything" pass has to
# delete a failing test rather than silently weaken a merge gate.
echo ""
echo "Testing CI-status helpers are uncached (issue #4667)..."

CI_STUB_DIR=$(mktemp -d)
CI_ARGS_FILE="$CI_STUB_DIR/argv.txt"

cat > "$CI_STUB_DIR/gh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GH_CI_ARGS_FILE"
for a in "$@"; do
  if [[ "$a" == "--no-cache" ]]; then
    echo "unknown flag: --no-cache" >&2
    exit 1
  fi
done
# `gh api ... --jq` filters server-side; the helpers ask for a reshaped object,
# so just emit the already-shaped result the helper would have produced.
case "$*" in
  *check-runs*) printf '{"total_count":1,"check_runs":[{"name":"build","status":"completed","conclusion":"success","html_url":"u"}]}\n' ;;
  *status*)     printf '{"state":"success","statuses":[]}\n' ;;
  *)            exit 1 ;;
esac
exit 0
STUB
chmod +x "$CI_STUB_DIR/gh"

# A `gh-cached` that must never be reached by these helpers.
cat > "$CI_STUB_DIR/gh-cached" <<'STUB'
#!/usr/bin/env bash
echo "gh-cached must NOT be used for CI-status reads" >&2
exit 1
STUB
chmod +x "$CI_STUB_DIR/gh-cached"

FORGE_TYPE="github"
: > "$CI_ARGS_FILE"

cr_state=$(GH_CI_ARGS_FILE="$CI_ARGS_FILE" PATH="$CI_STUB_DIR:$PATH" \
  forge_get_check_runs "owner/repo" "deadbeef" 2>/dev/null | jq -r '.check_runs[0].conclusion' 2>/dev/null || echo "")
assert_eq "success" "$cr_state" "forge_get_check_runs reaches plain gh (no --no-cache, no wrapper)"

cs_state=$(GH_CI_ARGS_FILE="$CI_ARGS_FILE" PATH="$CI_STUB_DIR:$PATH" \
  forge_get_commit_status "owner/repo" "deadbeef" 2>/dev/null | jq -r '.state' 2>/dev/null || echo "")
assert_eq "success" "$cs_state" "forge_get_commit_status reaches plain gh (no --no-cache, no wrapper)"

nocache_hits=$(grep -c -- '--no-cache' "$CI_ARGS_FILE" || true)
assert_eq "0" "$nocache_hits" "CI-status helpers never pass the wrapper-only --no-cache flag"

rm -rf "$CI_STUB_DIR"

# --- Test gitea_api auth-mode selection (issue #3297) ---
# Use a `curl` shim on PATH that records its argv and returns a fake 200.
echo ""
echo "Testing gitea_api auth mode selection (Basic vs token)..."

SHIM_DIR=$(mktemp -d)
CURL_ARGS_FILE=$(mktemp)
export CURL_ARGS_FILE
cat > "$SHIM_DIR/curl" <<'SHIM'
#!/usr/bin/env bash
# Record argv (one per line) and emit a fake 200 OK response.
: > "$CURL_ARGS_FILE"
for a in "$@"; do
  printf '%s\n' "$a" >> "$CURL_ARGS_FILE"
done
# gitea_api expects body lines followed by a final-line HTTP status code.
printf '{"ok":true}\n200\n'
SHIM
chmod +x "$SHIM_DIR/curl"

# --- Subtest 1: token mode sends "Authorization: token ..." and NOT -u ---
_GITEA_BASE_URL="https://gitea.example.com"
_GITEA_TOKEN="tok-abc"
_GITEA_USERNAME=""
PATH="$SHIM_DIR:$PATH" gitea_api GET "user" >/dev/null 2>&1 || true

if grep -q "^Authorization: token tok-abc$" "$CURL_ARGS_FILE"; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: token mode sends 'Authorization: token …' header"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: token mode missing 'Authorization: token …' header"
    echo "    curl argv:"; sed 's/^/      /' "$CURL_ARGS_FILE"
fi

if grep -qx -- "-u" "$CURL_ARGS_FILE"; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: token mode unexpectedly used '-u'"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: token mode does NOT use '-u'"
fi

# --- Subtest 2: Basic mode sends -u user:pass and NOT Authorization: token ---
_GITEA_USERNAME="alice"
_GITEA_BASE_URL="https://gitea.example.com"
PATH="$SHIM_DIR:$PATH" gitea_api GET "user" >/dev/null 2>&1 || true

if grep -qx -- "-u" "$CURL_ARGS_FILE" && grep -qx -- "alice:tok-abc" "$CURL_ARGS_FILE"; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: Basic mode sends '-u user:pass'"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: Basic mode missing '-u user:pass'"
    echo "    curl argv:"; sed 's/^/      /' "$CURL_ARGS_FILE"
fi

if grep -q "^Authorization: token" "$CURL_ARGS_FILE"; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: Basic mode unexpectedly sent 'Authorization: token …'"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: Basic mode does NOT send 'Authorization: token …'"
fi

# --- Subtest 3: HTTPS guard rejects http:// in Basic mode ---
_GITEA_USERNAME="alice"
_GITEA_TOKEN="tok-abc"
_GITEA_BASE_URL="http://insecure.example.com"
unset LOOM_ALLOW_INSECURE_BASIC_AUTH 2>/dev/null || true
# Capture rc and stderr separately. Use a subshell with set +e so the
# function's nonzero return code propagates without aborting the script.
guard_output=$(
  set +e
  PATH="$SHIM_DIR:$PATH" gitea_api GET "user" 2>&1 >/dev/null
  echo "RC=$?"
)
guard_rc=$(echo "$guard_output" | tail -1 | sed 's/^RC=//')
if [[ "$guard_rc" -ne 0 ]] && [[ "$guard_output" == *"Basic Auth requires HTTPS"* ]]; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: HTTPS guard rejects http:// in Basic mode"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: HTTPS guard did not fire (rc=$guard_rc, output=$guard_output)"
fi

# --- Subtest 4: HTTPS guard override via LOOM_ALLOW_INSECURE_BASIC_AUTH=1 ---
LOOM_ALLOW_INSECURE_BASIC_AUTH=1 PATH="$SHIM_DIR:$PATH" \
  gitea_api GET "user" >/dev/null 2>&1
override_rc=$?
if [[ "$override_rc" -eq 0 ]]; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: LOOM_ALLOW_INSECURE_BASIC_AUTH=1 permits http://"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: LOOM_ALLOW_INSECURE_BASIC_AUTH=1 did not unblock http:// (rc=$override_rc)"
fi

# --- Subtest 5: Username with ':' is rejected ---
_GITEA_USERNAME="alice:bob"
_GITEA_TOKEN="tok-abc"
_GITEA_BASE_URL="https://gitea.example.com"
colon_output=$(
  set +e
  PATH="$SHIM_DIR:$PATH" gitea_api GET "user" 2>&1 >/dev/null
  echo "RC=$?"
)
colon_rc=$(echo "$colon_output" | tail -1 | sed 's/^RC=//')
if [[ "$colon_rc" -ne 0 ]] && [[ "$colon_output" == *"may not contain ':'"* ]]; then
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: username with ':' rejected"
else
    TESTS_RUN=$((TESTS_RUN + 1)); TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: username with ':' was NOT rejected (rc=$colon_rc, output=$colon_output)"
fi

rm -rf "$SHIM_DIR" "$CURL_ARGS_FILE"

# --- Test forge_merge_pr / forge_update_branch / forge_delete_branch /
# forge_auto_merge: GitHub-path calls escalate through forge_gh_perm_safe on
# an App-installation permission 403 (#260) ---
#
# Before this fix these four functions called `gh api ...` directly, bypassing
# the fresh-token escalation ladder every comment/label write already used
# (forge_gh_perm_safe, #6074) -- so a transient or genuine App-permission 403
# on any of them had no retry/fresh-token fallback. This proves each GitHub-
# path write call now routes through the ladder: the first (ambient-token)
# attempt 403s, forge_gh_perm_safe force-mints a fresh installation token, and
# the retry under that token succeeds.
echo ""
echo "Testing forge_merge_pr/forge_update_branch/forge_delete_branch/forge_auto_merge GitHub-path 403 escalation (#260)..."

PERM_STUB_DIR=$(mktemp -d)
PERM_ATTEMPT_LOG="$PERM_STUB_DIR/attempts.log"
PERM_MINT_LOG="$PERM_STUB_DIR/mint.log"
PERM_GH_MODE_FILE="$PERM_STUB_DIR/mode.txt"
export PERM_ATTEMPT_LOG PERM_MINT_LOG PERM_GH_MODE_FILE

# A `gh` stub that:
#   - always succeeds on a plain read (no `-X`, not `graphql` as $2) -- used by
#     forge_auto_merge's node_id lookup, which is a GET this issue is NOT
#     about and must never interfere with the write-call escalation under
#     test.
#   - for a write call (`-X <verb>` or `graphql`), 403s with the integration
#     wording on the FIRST write attempt and succeeds on any retry -- proving
#     the retry is the escalated (freshly-minted-token) one, not a replay of
#     the same failing ambient attempt.
cat > "$PERM_STUB_DIR/gh" <<'STUB'
#!/usr/bin/env bash
mode="$(cat "$PERM_GH_MODE_FILE" 2>/dev/null || echo ok)"
cred="ambient"
[[ -n "${GH_TOKEN:-}" ]] && cred="token:${GH_TOKEN}"
printf '%s | %s\n' "$cred" "$*" >> "$PERM_ATTEMPT_LOG"

if [[ "$*" != *" -X "* && "$2" != "graphql" ]]; then
  echo '{"node_id":"PR_kwABC123"}'
  exit 0
fi

write_attempts=$(grep -cE -- ' -X | graphql' "$PERM_ATTEMPT_LOG" || true)
case "$mode" in
  ok)
    echo '{"merged":true}'
    exit 0
    ;;
  perm403-once)
    if [[ "$write_attempts" == "1" ]]; then
      echo "HTTP 403: Resource not accessible by integration" >&2
      exit 1
    fi
    echo '{"merged":true}'
    exit 0
    ;;
  perm403)
    echo "HTTP 403: Resource not accessible by integration" >&2
    exit 1
    ;;
esac
STUB
chmod +x "$PERM_STUB_DIR/gh"

# A `github-app-token.sh` stub speaking the real JSON envelope (mirrors
# test-app-permission-fallback.sh's stub for the same #6074 ladder).
cat > "$PERM_STUB_DIR/github-app-token.sh" <<'MINT'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PERM_MINT_LOG"
echo '{"status":"ok","token":"ghs_fresh260","installation_id":"1","app_id":"2","expires_at":"2099-01-01T00:00:00Z"}'
MINT
chmod +x "$PERM_STUB_DIR/github-app-token.sh"

# A git repo with an origin remote, so _forge_nwo_from_remote resolves without
# any API call.
PERM_FAKE_REPO="$PERM_STUB_DIR/repo"
mkdir -p "$PERM_FAKE_REPO"
git -C "$PERM_FAKE_REPO" init -q
git -C "$PERM_FAKE_REPO" remote add origin "https://github.com/owner/repo.git"
git -C "$PERM_FAKE_REPO" -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
git -C "$PERM_FAKE_REPO" checkout -q -B feature/issue-260

_run_perm_ladder() {
    local gh_mode="$1"
    shift
    echo "$gh_mode" > "$PERM_GH_MODE_FILE"
    : > "$PERM_ATTEMPT_LOG"
    : > "$PERM_MINT_LOG"
    (
        cd "$PERM_FAKE_REPO"
        PATH="$PERM_STUB_DIR:$PATH" \
        LOOM_GITHUB_APP_SCRIPT="$PERM_STUB_DIR/github-app-token.sh" \
        FORGE_TYPE="github" \
            "$@"
    )
}

# forge_merge_pr
rc=0
out="$(_run_perm_ladder perm403-once bash -c 'source "'"$HELPERS_DIR"'/lib/forge-helpers.sh"; FORGE_TYPE=github forge_merge_pr owner/repo 42' 2>/dev/null)" || rc=$?
assert_eq "0" "$rc" "forge_merge_pr: an App-permission 403 recovers via forge_gh_perm_safe's fresh-token retry"
TESTS_RUN=$((TESTS_RUN + 1))
if [[ "$out" == *'{"merged":true}'* ]]; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: forge_merge_pr: the escalated attempt's output is returned"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: forge_merge_pr: the escalated attempt's output is returned (got: '$out')"
fi
TESTS_RUN=$((TESTS_RUN + 1))
if grep -q "get-token --force" "$PERM_MINT_LOG"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: forge_merge_pr's 403 retry force-mints a fresh installation token (bypasses the ~1h cache)"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: forge_merge_pr never force-minted a fresh token on the 403"
fi
TESTS_RUN=$((TESTS_RUN + 1))
if grep -q "token:ghs_fresh260" "$PERM_ATTEMPT_LOG"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: forge_merge_pr's retry runs under the freshly minted token"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: forge_merge_pr's retry did not carry the freshly minted token"
fi

# A genuine (non-recovering) 403 still surfaces a clear failure rather than
# being silently swallowed -- matching forge_gh_perm_safe's existing
# comment/label behavior.
rc=0
_run_perm_ladder perm403 bash -c 'source "'"$HELPERS_DIR"'/lib/forge-helpers.sh"; FORGE_TYPE=github forge_merge_pr owner/repo 42' >/dev/null 2>&1 || rc=$?
assert_eq "1" "$rc" "forge_merge_pr: an exhausted ladder (still 403 after the fresh mint) surfaces failure, not silently swallowed"

# forge_update_branch
rc=0
out="$(_run_perm_ladder perm403-once bash -c 'source "'"$HELPERS_DIR"'/lib/forge-helpers.sh"; FORGE_TYPE=github forge_update_branch owner/repo 42' 2>/dev/null)" || rc=$?
assert_eq "0" "$rc" "forge_update_branch: an App-permission 403 recovers via forge_gh_perm_safe's fresh-token retry"
TESTS_RUN=$((TESTS_RUN + 1))
if grep -q "get-token --force" "$PERM_MINT_LOG"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: forge_update_branch's 403 retry force-mints a fresh installation token"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: forge_update_branch never force-minted a fresh token on the 403"
fi

# forge_delete_branch
rc=0
out="$(_run_perm_ladder perm403-once bash -c 'source "'"$HELPERS_DIR"'/lib/forge-helpers.sh"; FORGE_TYPE=github forge_delete_branch owner/repo feature/issue-1' 2>/dev/null)" || rc=$?
assert_eq "0" "$rc" "forge_delete_branch: an App-permission 403 recovers via forge_gh_perm_safe's fresh-token retry"
TESTS_RUN=$((TESTS_RUN + 1))
if grep -q "get-token --force" "$PERM_MINT_LOG"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: forge_delete_branch's 403 retry force-mints a fresh installation token"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: forge_delete_branch never force-minted a fresh token on the 403"
fi

# forge_auto_merge (GraphQL mutation path) -- the node_id GET always succeeds
# (stubbed above), so this exercises escalation on the mutation itself.
rc=0
out="$(_run_perm_ladder perm403-once bash -c 'source "'"$HELPERS_DIR"'/lib/forge-helpers.sh"; FORGE_TYPE=github forge_auto_merge owner/repo 42' 2>/dev/null)" || rc=$?
assert_eq "0" "$rc" "forge_auto_merge: an App-permission 403 on the GraphQL mutation recovers via forge_gh_perm_safe's fresh-token retry"
TESTS_RUN=$((TESTS_RUN + 1))
if grep -q "get-token --force" "$PERM_MINT_LOG"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: forge_auto_merge's 403 retry force-mints a fresh installation token"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: forge_auto_merge never force-minted a fresh token on the 403"
fi
TESTS_RUN=$((TESTS_RUN + 1))
if grep -q "token:ghs_fresh260 | api graphql" "$PERM_ATTEMPT_LOG"; then
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "  ${GREEN}PASS${NC}: forge_auto_merge's retry runs the GraphQL mutation under the freshly minted token"
else
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "  ${RED}FAIL${NC}: forge_auto_merge's retry did not carry the freshly minted token on the mutation"
fi

rm -rf "$PERM_STUB_DIR"

# --- Regression guard: the Gitea path of all four functions is byte-identical
# to before this fix (#260's own acceptance criteria: "verify by diff, not
# just by omission"). Each of these four functions' `gitea_api` invocation(s)
# must remain exactly as documented in the function's header comment -- if a
# future edit changes the Gitea branch, this fails loudly instead of silently
# drifting.
echo ""
echo "Testing Gitea-path call shape is unchanged for the four #260 functions..."

FORGE_HELPERS_SRC="$HELPERS_DIR/lib/forge-helpers.sh"

assert_gitea_shape() {
    local fn="$1" expected_snippet="$2" msg="$3"
    TESTS_RUN=$((TESTS_RUN + 1))
    # Extract just this function's body (from its `fn() {` line to the next
    # top-level `}`), then check the expected gitea_api invocation is present
    # verbatim.
    local body
    body="$(awk -v fn="$fn" '
        $0 ~ "^"fn"\\(\\) \\{" { capture=1 }
        capture { print }
        capture && /^}/ { exit }
    ' "$FORGE_HELPERS_SRC")"
    if [[ "$body" == *"$expected_snippet"* ]]; then
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo -e "  ${GREEN}PASS${NC}: $msg"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo -e "  ${RED}FAIL${NC}: $msg"
    fi
}

assert_gitea_shape "forge_merge_pr" \
    'gitea_api POST "repos/$FORGE_OWNER/$FORGE_REPO/pulls/$pr_number/merge"' \
    "forge_merge_pr's Gitea path still POSTs to pulls/{n}/merge"

assert_gitea_shape "forge_update_branch" \
    'gitea_api POST "repos/$FORGE_OWNER/$FORGE_REPO/pulls/$pr_number/update"' \
    "forge_update_branch's Gitea path still POSTs to pulls/{n}/update"

assert_gitea_shape "forge_delete_branch" \
    'gitea_api DELETE "repos/$FORGE_OWNER/$FORGE_REPO/branches/$branch" 2>/dev/null' \
    "forge_delete_branch's Gitea path still DELETEs branches/{name}"

assert_gitea_shape "forge_auto_merge" \
    'gitea_api POST "repos/$FORGE_OWNER/$FORGE_REPO/pulls/$pr_number/merge"' \
    "forge_auto_merge's Gitea path still POSTs to pulls/{n}/merge"

# --- Summary ---
echo ""
echo "────────────────────────────────"
echo "Results: $TESTS_PASSED/$TESTS_RUN passed, $TESTS_FAILED failed"

if [[ $TESTS_FAILED -gt 0 ]]; then
    exit 1
fi
exit 0
