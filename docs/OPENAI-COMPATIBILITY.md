# ChatGPT and Codex Compatibility

## Scope

This repository packages the same source skills for ChatGPT and Codex using the OpenAI plugin format.

- `SKILL.md` remains the workflow source of truth.
- `agents/openai.yaml` provides OpenAI product targeting, presentation, and invocation policy.
- `.codex-plugin/plugin.json` packages related skills into installable collections.
- `.agents/plugins/marketplace.json` exposes the collections as a local marketplace.
- No MCP server is required for the current instruction-and-reference workflows.

## Guided-journey runtime modes

The twelve guided journeys support two execution environments.

### Workspace mode

Use this mode when the host provides a writable project workspace.

- Read existing journey trackers and project artifacts before acting.
- Write approved artifacts under `docs/`.
- Preserve existing content and resume prior journey state.
- Report writes only after the host confirms that the write succeeded.

### Chat mode

Use this mode when no writable project workspace is available.

- Maintain structured journey state in the conversation.
- Present complete Markdown artifacts for approval or download.
- Do not claim that repository files were created or updated.
- Continue with the built-in phase fallback when another skill is unavailable.

The guided journeys disable implicit invocation because they are long-running, stateful workflows. Users should select them explicitly.

## Source-controlled metadata

Collection listing copy is stored in:

```text
config/openai-plugin-metadata.json
```

The Claude marketplace remains the source of truth for collection membership and versions:

```text
.claude-plugin/marketplace.json
```

Regenerate OpenAI plugin packages with:

```bash
./scripts/generate-codex-plugins.sh
```

Despite the historical script name, it generates the plugin format shared by ChatGPT and Codex.

## Validation

Run:

```bash
./scripts/generate-codex-plugins.sh
python3 ./scripts/validate-openai-compat.py
git diff --exit-code -- .agents/plugins plugins
```

Validation checks:

- every marketplace skill exists and has valid `SKILL.md` frontmatter;
- skill names are unique;
- all twelve guided journeys target `CHAT` and `CODEX`;
- guided journeys disable implicit invocation;
- guided journeys include the chat-mode file-write guard;
- every collection has complete curated listing metadata;
- generated manifests use the current repository and homepage;
- generated plugin membership matches the marketplace;
- generated skill symlinks resolve.

GitHub Actions runs the same checks on pull requests and pushes to `main`.

## Local ChatGPT testing

The repository marketplace is located at:

```text
.agents/plugins/marketplace.json
```

Use a ChatGPT desktop environment that supports local plugin marketplaces. Refresh or restart the desktop app after changing generated plugin files, install the desired collection, and test in a new chat.

Minimum guided-journey test cases:

1. Explicitly invoke the journey in a writable repository and confirm workspace mode.
2. Explicitly invoke it without a writable repository and confirm chat mode.
3. Confirm it does not activate implicitly from a broad request.
4. Confirm chat mode never reports an unperformed file write.
5. Confirm workspace mode resumes an existing tracker rather than restarting.

## Public distribution

The first public release should remain skills-only. Add MCP only when a workflow requires authenticated live data, controlled external actions, or persistent hosted state.

Before public submission, add final brand assets and public support, privacy, and terms URLs, then prepare the required positive and negative review test cases for each collection.
