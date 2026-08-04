#!/usr/bin/env bash
#
# generate-codex-plugins.sh — mirror the Claude plugin marketplace into the
# OpenAI plugin standard shared by ChatGPT and Codex.
#
# SINGLE SOURCE OF TRUTH:
#   .claude-plugin/marketplace.json   collection membership and versions
#   config/openai-plugin-metadata.json ChatGPT/Codex listing presentation
#
# This script regenerates:
#
#   plugins/<collection>/.codex-plugin/plugin.json   # OpenAI plugin manifest
#   plugins/<collection>/skills/<skill>              # symlinks -> repo-root skills
#   .agents/plugins/marketplace.json                 # local ChatGPT/Codex marketplace
#
# Source skills may include agents/openai.yaml for ChatGPT/Codex presentation,
# invocation policy, and MCP dependencies. Symlinked plugin skills expose that
# metadata without duplicating the skill source tree.
#
# Fully generated and idempotent: safe to re-run. Invoked by
# scripts/sync-ide-skills.sh (skill set changed) and
# scripts/sync-marketplace-versions.sh (version changed).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SRC=".claude-plugin/marketplace.json"
OPENAI_META="config/openai-plugin-metadata.json"
PLUGINS_DIR="plugins"
MP_DIR=".agents/plugins"
MP="$MP_DIR/marketplace.json"
PUBLIC_REPOSITORY="https://github.com/ntwrkfx/wondel-skills"
PUBLIC_HOMEPAGE="https://skills.wondel.ai"

METASKILLS=(
  create-business create-website create-app
  improve-business improve-website improve-app
  grow-business grow-website grow-app
  improve-code-quality remove-technical-debt design-code-architecture
)

[[ -f "$SRC" ]] || { echo "Error: $SRC not found (run from the skills repo root)" >&2; exit 1; }
[[ -f "$OPENAI_META" ]] || { echo "Error: $OPENAI_META not found" >&2; exit 1; }
command -v jq >/dev/null || { echo "Error: jq is required" >&2; exit 1; }
jq -e . "$SRC" >/dev/null || { echo "Error: invalid JSON: $SRC" >&2; exit 1; }
jq -e . "$OPENAI_META" >/dev/null || { echo "Error: invalid JSON: $OPENAI_META" >&2; exit 1; }

# ChatGPT-compatible guided journeys must explicitly define their no-workspace
# behavior. Fail generation rather than publishing a journey that can claim
# nonexistent file writes or activate unexpectedly.
for skill in "${METASKILLS[@]}"; do
  metadata="$skill/agents/openai.yaml"
  [[ -f "$metadata" ]] || { echo "Error: missing $metadata" >&2; exit 1; }
  grep -q -- '- CHAT' "$metadata" || { echo "Error: $metadata does not target CHAT" >&2; exit 1; }
  grep -q -- '- CODEX' "$metadata" || { echo "Error: $metadata does not target CODEX" >&2; exit 1; }
  grep -q 'allow_implicit_invocation: false' "$metadata" || {
    echo "Error: $metadata must disable implicit invocation" >&2
    exit 1
  }
  grep -q 'never claim files were written' "$metadata" || {
    echo "Error: $metadata lacks the chat-mode file-write guard" >&2
    exit 1
  }
done

# This script fully owns these generated paths.
rm -rf "$PLUGINS_DIR" "$MP_DIR"
mkdir -p "$PLUGINS_DIR" "$MP_DIR"

# 1) Local marketplace — one entry per collection.
jq '{
  name: .name,
  interface: { displayName: "Wondel.ai Skills" },
  plugins: [ .plugins[] | {
    name: .name,
    source: { source: "local", path: ("./plugins/" + .name) },
    policy: { installation: "AVAILABLE", authentication: "ON_FIRST_USE" },
    category: (.category // "productivity")
  } ]
}' "$SRC" > "$MP"

# 2) One OpenAI plugin per collection: curated manifest + skill symlinks.
count="$(jq '.plugins | length' "$SRC")"
total_links=0
for i in $(seq 0 $((count - 1))); do
  name="$(jq -r ".plugins[$i].name" "$SRC")"
  pdir="$PLUGINS_DIR/$name"
  mkdir -p "$pdir/.codex-plugin" "$pdir/skills"

  jq -e --arg name "$name" '
    .[$name]
    and .[$name].displayName
    and .[$name].shortDescription
    and .[$name].longDescription
    and .[$name].category
    and .[$name].defaultPrompt
  ' "$OPENAI_META" >/dev/null || {
    echo "Error: incomplete OpenAI listing metadata for plugin $name" >&2
    exit 1
  }

  jq \
    --argjson index "$i" \
    --arg repository "$PUBLIC_REPOSITORY" \
    --arg homepage "$PUBLIC_HOMEPAGE" \
    --slurpfile openai "$OPENAI_META" '
      .plugins[$index] as $plugin
      | ($openai[0][$plugin.name] // {}) as $meta
      | {
          name: $plugin.name,
          version: $plugin.version,
          description: $plugin.description,
          author: {
            name: ($plugin.author.name // "Wondel.ai"),
            url: ($plugin.author.url // $homepage)
          },
          license: $plugin.license,
          keywords: $plugin.keywords,
          repository: $repository,
          homepage: $homepage,
          skills: "./skills/",
          interface: {
            displayName: $meta.displayName,
            shortDescription: $meta.shortDescription,
            longDescription: $meta.longDescription,
            developerName: ($plugin.author.name // "Wondel.ai"),
            category: $meta.category,
            capabilities: ["Structured analysis", "Guided workflows"],
            websiteURL: $homepage,
            defaultPrompt: [$meta.defaultPrompt]
          }
        }
      | with_entries(select(.value != null))
    ' "$SRC" > "$pdir/.codex-plugin/plugin.json"

  # Symlink each member skill to its repo-root directory. OpenAI metadata in
  # <skill>/agents/openai.yaml remains visible through the link.
  while IFS= read -r sk; do
    sk="${sk#./}"
    if [[ ! -f "$sk/SKILL.md" ]]; then
      echo "  warn: skill '$sk' (collection $name) has no SKILL.md — skipping" >&2
      continue
    fi
    ln -s "../../../$sk" "$pdir/skills/$sk"
    total_links=$((total_links + 1))
  done < <(jq -r ".plugins[$i].skills[]" "$SRC")
done

# 3) Validate generated structure.
jq -e . "$MP" >/dev/null || { echo "Error: generated $MP is invalid JSON" >&2; exit 1; }
for pj in "$PLUGINS_DIR"/*/.codex-plugin/plugin.json; do
  jq -e '.name and .version and .description and .skills and .interface.displayName and .interface.shortDescription' "$pj" >/dev/null || {
    echo "Error: incomplete or invalid OpenAI manifest: $pj" >&2
    exit 1
  }
  [[ "$(jq -r '.repository' "$pj")" == "$PUBLIC_REPOSITORY" ]] || {
    echo "Error: stale repository URL in $pj" >&2
    exit 1
  }
done

broken="$(find "$PLUGINS_DIR" -type l ! -exec test -e {} \; -print 2>/dev/null || true)"
[[ -z "$broken" ]] || { echo "Error: broken symlinks:" >&2; echo "$broken" >&2; exit 1; }

echo "Generated $count ChatGPT/Codex plugins ($total_links skill links) + $MP"
