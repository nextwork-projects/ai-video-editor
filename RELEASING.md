# Releasing

Bump `version` in the plugin's `.claude-plugin/plugin.json` and in its entry in
`.claude-plugin/marketplace.json` (they must match). For ai-editor, also bump `.cursor-plugin/plugin.json`
and `.codex-plugin/plugin.json`. Then check:

```bash
python3 tests/check_plugins.py
for p in . plugins/ai-editor plugins/creator-teardown; do claude plugin validate --strict "$p"; done
```

## Version tags

Dependency ranges such as ai-editor's `creator-teardown ^2.0.0` resolve against git tags named
`<plugin>--v<version>`. No such tag exists yet. After the release commit is merged, from a clean
checkout of `main`:

```bash
cd plugins/creator-teardown && claude plugin tag --dry-run && claude plugin tag --push && cd ../..
cd plugins/ai-editor && claude plugin tag --dry-run && claude plugin tag --push && cd ../..
```

That creates and pushes `creator-teardown--v2.0.0` and `ai-editor--v1.1.1`. `claude plugin tag`
validates the plugin, checks plugin.json and the marketplace entry agree, and refuses a dirty tree
or an existing tag. Without `--push` it prints the `git push origin <tag>` command instead.

`gsap-skills` and `hyperframes` publish no `<plugin>--v` tags, so ai-editor depends on them
without a version range.

## Evals

Each plugin has an `evals/` suite (`claude plugin eval`, Claude Code 2.1.269 or later). Every run is a
real model call on your account.

```bash
cd plugins/creator-teardown && claude plugin eval . --runs 1 --ablation none --no-publish
```

ai-editor declares dependencies, so it only loads with them installed. Run its suite against the
installed copy after adding the three marketplaces in the README:

```bash
claude plugin eval ai-editor@nextwork --runs 1 --ablation none --no-publish
```
