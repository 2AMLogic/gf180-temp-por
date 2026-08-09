#!/usr/bin/env bash
# post-fallback-comment.sh — tool-enforced marker append for Judge fallback-mode
# comments (issue #144).
#
# Problem this closes: judge-fallback-guard.sh's lifetime cap and velocity
# alert (#5455) are only as good as their MARKER_COUNT input, which is derived
# by grepping posted comments for the exact
# `<!-- loom:fallback-evaluated sha=... --> ` marker. Before this script
# existed, appending that marker was a free-form step embedded in an example
# `gh pr comment` heredoc in judge.md — an LLM had to faithfully reproduce it
# verbatim on every fallback-mode pass, with nothing enforcing it. On PR #118
# (this repo), ~44 of ~45 fallback-mode comments over ~54h omitted the exact
# marker (close paraphrases of the prose, but no marker), so
# judge-fallback-guard.sh read MARKER_COUNT=1 and neither the cap nor the
# velocity alert ever tripped. judge-fallback-guard.sh itself was extended
# (#144) to also recognize marker-less "evaluated in fallback mode" comments
# as an immediate backstop against that historical undercount — but that is a
# heuristic patch on the READ side. This script is the durable fix on the
# WRITE side: it moves the marker-append step itself out of prose and into a
# real, testable subprocess, the same move #5455 made for the skip/evaluate
# decision — so a future fallback-mode pass cannot omit the marker by
# forgetting to reproduce a heredoc correctly.
#
# What it does:
#   1. Resolves the PR's current head SHA (via `--head-sha`, or `gh pr view`
#      if not given).
#   2. Reads the review body from a file (never inline on argv — keeps this
#      safe for arbitrarily long/multi-line review text and avoids the
#      `--body @path`-posts-the-literal-string pitfall of the `gh` CLI).
#   3. Appends the exact `<!-- loom:fallback-evaluated sha=<head-sha> -->`
#      marker on its own line (unless the body already ends with a marker for
#      the SAME sha, in which case it is not duplicated).
#   4. Posts the composed body via `gh pr comment --body-file`.
#
# Usage:
#   post-fallback-comment.sh <pr-number> <body-file> [--head-sha SHA] [--dry-run]
#
# Exit codes:
#   0  = comment posted (or, with --dry-run, would have been)
#   1  = usage or environment error (bad args, missing body file, `gh` failure)

set -euo pipefail

usage() {
  echo "Usage: $0 <pr-number> <body-file> [--head-sha SHA] [--dry-run]" >&2
}

PR=""
BODY_FILE=""
HEAD_SHA=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --head-sha) HEAD_SHA="${2:?--head-sha requires a value}"; shift 2 ;;
    --head-sha=*) HEAD_SHA="${1#*=}"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*)
      echo "ERROR: unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      if [[ -z "$PR" ]]; then
        PR="$1"
      elif [[ -z "$BODY_FILE" ]]; then
        BODY_FILE="$1"
      else
        echo "ERROR: unexpected extra argument: $1" >&2
        usage
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$PR" || ! "$PR" =~ ^[0-9]+$ ]]; then
  echo "ERROR: a numeric PR number is required" >&2
  usage
  exit 1
fi
if [[ -z "$BODY_FILE" ]]; then
  echo "ERROR: a body-file path is required" >&2
  usage
  exit 1
fi
if [[ ! -f "$BODY_FILE" ]]; then
  echo "ERROR: body-file not found: $BODY_FILE" >&2
  exit 1
fi

command -v gh >/dev/null 2>&1 || { echo "ERROR: 'gh' not found on PATH" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: 'jq' not found on PATH" >&2; exit 1; }

GH_STDERR="$(mktemp)"
COMPOSED_BODY_FILE="$(mktemp)"
trap 'rm -f "$GH_STDERR" "$COMPOSED_BODY_FILE" 2>/dev/null || true' EXIT

if [[ -z "$HEAD_SHA" ]]; then
  PR_JSON="$(gh pr view "$PR" --json headRefOid 2>"$GH_STDERR")" || {
    echo "ERROR: 'gh pr view $PR --json headRefOid' failed: $(cat "$GH_STDERR" 2>/dev/null)" >&2
    exit 1
  }
  HEAD_SHA="$(jq -r '.headRefOid // empty' <<<"$PR_JSON" 2>/dev/null || true)"
  if [[ -z "$HEAD_SHA" ]]; then
    echo "ERROR: could not resolve head SHA for PR #$PR from: $PR_JSON" >&2
    exit 1
  fi
fi

MARKER="<!-- loom:fallback-evaluated sha=$HEAD_SHA -->"

# Copy the caller's body verbatim, then append the marker — unless the body
# ALREADY ends with a marker for this exact sha (idempotent re-run), in which
# case we do not duplicate it.
LAST_LINE="$(tail -n 1 -- "$BODY_FILE" 2>/dev/null || true)"
cp -- "$BODY_FILE" "$COMPOSED_BODY_FILE"
if [[ "$LAST_LINE" != "$MARKER" ]]; then
  {
    # Ensure at least one blank line separates the review prose from the
    # marker, matching the template every fallback-mode comment has used.
    printf '\n\n%s\n' "$MARKER"
  } >> "$COMPOSED_BODY_FILE"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "DRY_RUN=1"
  echo "PR=$PR"
  echo "HEAD_SHA=$HEAD_SHA"
  echo "MARKER=$MARKER"
  echo "--- composed body ---"
  cat -- "$COMPOSED_BODY_FILE"
  exit 0
fi

gh pr comment "$PR" --body-file "$COMPOSED_BODY_FILE" 2>"$GH_STDERR" || {
  echo "ERROR: 'gh pr comment $PR --body-file ...' failed: $(cat "$GH_STDERR" 2>/dev/null)" >&2
  exit 1
}

echo "OK: posted fallback-mode comment on PR #$PR with marker for sha=$HEAD_SHA"
