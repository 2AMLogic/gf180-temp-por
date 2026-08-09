#!/usr/bin/env bash
# post-fallback-comment.sh — post a fallback-mode Judge comment on a PR with
# the `<!-- loom:fallback-evaluated sha=<head-sha> -->` marker appended
# programmatically (issue #144).
#
# Problem this closes: `judge-fallback-guard.sh`'s lifetime cap and velocity
# alert count comments carrying that marker. Before #144 the marker was
# appended by prompt compliance alone — judge.md showed an example `gh pr
# comment` heredoc ending in the marker, and every fallback-mode pass had to
# remember to reproduce it verbatim. It did not hold: gf180-temp-por PR #118
# accumulated 44 fallback-mode Judge comments over ~2 days of which only 2
# carried the marker, so the guard reported MARKER_COUNT=1 and the default
# cap of 20 never fired.
#
# The durable fix is to take the marker out of the free-text a model has to
# reproduce and put it in a script: the Judge writes only its review prose,
# this script resolves the head SHA and appends the marker itself. The
# heuristic backstop added to judge-fallback-guard.sh in the same change
# catches comments that bypass this helper (and the ones already in the wild);
# this helper is what stops new ones from being created.
#
# Deliberately NOT the same job as judge-fallback-guard.sh: that script
# decides *whether* to evaluate a PR, this one posts the *result*. They are
# split so the gate can be consulted (and tested) without any write side
# effect.
#
# Usage:
#   post-fallback-comment.sh <pr-number> [--body TEXT | --body-file FILE | -]
#       --body TEXT        review prose to post
#       --body-file FILE   read review prose from FILE ("-" = stdin)
#       -                  read review prose from stdin (same as --body-file -)
#       --sha SHA          override the head SHA (default: resolved via
#                          `gh pr view <pr> --json headRefOid`)
#       --dry-run          print the composed comment body to stdout and exit
#                          0 WITHOUT posting
#
#   With none of --body / --body-file / -, the body is read from stdin.
#
# Behavior:
#   - The marker is appended only if the body does not already contain one, so
#     an already-conforming body (or a re-run over the same text) is not
#     double-marked.
#   - An empty body is an error: a marker-only comment is noise, and the cap
#     it feeds is supposed to count real evaluations.
#
# Output (stdout):
#   the URL `gh pr comment` printed (or, with --dry-run, the composed body)
#
# Exit codes:
#   0 = comment posted (or composed, under --dry-run)
#   1 = usage or environment error (bad args, empty body, `gh` call failed)

set -euo pipefail

PR=""
BODY=""
BODY_SET=0
BODY_FILE=""
SHA_OVERRIDE=""
DRY_RUN=0

usage() {
  echo "Usage: $0 <pr-number> [--body TEXT | --body-file FILE | -] [--sha SHA] [--dry-run]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --body) BODY="${2:?--body requires a value}"; BODY_SET=1; shift 2 ;;
    --body=*) BODY="${1#*=}"; BODY_SET=1; shift ;;
    --body-file) BODY_FILE="${2:?--body-file requires a value}"; shift 2 ;;
    --body-file=*) BODY_FILE="${1#*=}"; shift ;;
    --sha) SHA_OVERRIDE="${2:?--sha requires a value}"; shift 2 ;;
    --sha=*) SHA_OVERRIDE="${1#*=}"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -) BODY_FILE="-"; shift ;;
    -*)
      echo "ERROR: unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      if [[ -n "$PR" ]]; then
        echo "ERROR: unexpected extra argument: $1" >&2
        usage
        exit 1
      fi
      PR="$1"
      shift
      ;;
  esac
done

if [[ -z "$PR" || ! "$PR" =~ ^[0-9]+$ ]]; then
  echo "ERROR: a numeric PR number is required" >&2
  usage
  exit 1
fi

if [[ "$BODY_SET" -eq 1 && -n "$BODY_FILE" ]]; then
  echo "ERROR: --body and --body-file/- are mutually exclusive" >&2
  exit 1
fi

command -v gh >/dev/null 2>&1 || { echo "ERROR: 'gh' not found on PATH" >&2; exit 1; }

# --- Resolve the review prose ------------------------------------------------
if [[ "$BODY_SET" -eq 0 ]]; then
  if [[ -z "$BODY_FILE" || "$BODY_FILE" == "-" ]]; then
    BODY="$(cat)"
  else
    [[ -r "$BODY_FILE" ]] || { echo "ERROR: cannot read --body-file: $BODY_FILE" >&2; exit 1; }
    BODY="$(cat "$BODY_FILE")"
  fi
fi

if [[ -z "${BODY//[[:space:]]/}" ]]; then
  echo "ERROR: refusing to post an empty fallback-mode comment (the lifetime cap counts real evaluations)" >&2
  exit 1
fi

# --- Resolve the head SHA ----------------------------------------------------
GH_STDERR="$(mktemp)"
trap 'rm -f "$GH_STDERR" 2>/dev/null || true' EXIT

HEAD_SHA="$SHA_OVERRIDE"
if [[ -z "$HEAD_SHA" ]]; then
  # Keep gh's stdout and stderr SEPARATE — gh writes incidental content to
  # stderr even on success (update-notifier banners, rate-limit hints), and
  # folding it into stdout would corrupt the SHA. Same rationale as
  # judge-fallback-guard.sh's Step 1.
  HEAD_SHA="$(gh pr view "$PR" --json headRefOid --jq '.headRefOid' 2>"$GH_STDERR")" || {
    echo "ERROR: 'gh pr view $PR --json headRefOid' failed: $(cat "$GH_STDERR" 2>/dev/null)" >&2
    exit 1
  }
fi

HEAD_SHA="$(tr -d '[:space:]' <<<"$HEAD_SHA")"
if [[ -z "$HEAD_SHA" ]]; then
  echo "ERROR: could not resolve head SHA for PR #$PR" >&2
  exit 1
fi
if [[ ! "$HEAD_SHA" =~ ^[0-9a-f]+$ ]]; then
  # A non-hex SHA would post a marker that can never equal a real head SHA,
  # silently defeating the dedup the marker exists to drive — fail loudly
  # instead. (The pre-#144 heredoc's classic failure mode was posting the
  # literal string "sha=$CURRENT_HEAD_SHA" from a quoted heredoc.)
  echo "ERROR: head SHA is not lowercase hex: '$HEAD_SHA'" >&2
  exit 1
fi

# --- Compose ------------------------------------------------------------------
MARKER="<!-- loom:fallback-evaluated sha=$HEAD_SHA -->"

if grep -qF -- "<!-- loom:fallback-evaluated sha=" <<<"$BODY"; then
  # Already marked (caller pasted a marker, or this is a re-run over composed
  # text) — post as-is rather than stacking a second marker, which would
  # double-count against the lifetime cap.
  FULL_BODY="$BODY"
else
  FULL_BODY="$BODY"$'\n\n'"$MARKER"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '%s\n' "$FULL_BODY"
  exit 0
fi

# --- Post ---------------------------------------------------------------------
# `--body-file -` reads the body from stdin, which avoids any shell-quoting or
# heredoc-expansion hazard in the review prose (backticks, `$`, code fences).
printf '%s\n' "$FULL_BODY" | gh pr comment "$PR" --body-file - 2>"$GH_STDERR" || {
  echo "ERROR: 'gh pr comment $PR' failed: $(cat "$GH_STDERR" 2>/dev/null)" >&2
  exit 1
}
