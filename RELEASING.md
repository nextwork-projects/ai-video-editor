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
real model call on your account. Run both suites from the repo root:

```bash
tests/run_evals.sh                       # 3 runs per case, both plugins
tests/run_evals.sh --runs 1 --case start-asks
```

Results land in `eval-results/` (`<plugin>.json` and `<plugin>.html`). The script fails when a case
scores under `EVAL_THRESHOLD` (default 0.8) and stops at `EVAL_MAX_COST` dollars per suite
(default 15). A full 3-run pass of both suites cost $13 on 2026-10-07 (ai-editor $12.08, creator-teardown $0.95); `--runs 1` is about a third of that.

Why the repo root: ai-editor depends on creator-teardown, and `claude plugin eval` does not install
dependencies or take `--plugin-dir`. Each ai-editor case lists both plugin folders in its
`plugins:` frontmatter, and eval only loads plugin folders under the directory it was pointed at,
so it has to point at the root (`--eval-dir plugins/ai-editor/evals`). Running from
`plugins/ai-editor` fails with "outside the containment root".

Headless eval runs have no AskUserQuestion tool (it is listed in `allowed_tools` but never
offered), so the asking graders are `llm` graders that accept a question with choices in the reply.

Eval runs also have no shell: granting Bash needs the OS sandbox, which refuses to start on a Mac
whose `~/.docker` holds a symlink, and the editor is never installed in the run's temporary home.
So each case sets `append_system_prompt` to a dry run: write each command and its likely result,
treat the editor as installed and named files as present, and stop at the next question. The
suites test the decision path (what the agent routes to, asks and refuses), not the scripts;
those have their own `demo` self-checks and `tests/smoke.py`. The judge is Sonnet
(`EVAL_JUDGE` to change it): Haiku failed replies that met the rubric.

### CI

The `evals` job in `.github/workflows/check.yml` runs `tests/run_evals.sh --runs 1` on manual
dispatch only, and only when the repo has an `ANTHROPIC_API_KEY` secret. Add the secret under
Settings > Secrets and variables > Actions to turn it on.
