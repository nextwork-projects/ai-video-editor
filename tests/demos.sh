#!/usr/bin/env bash
# Every script's self-check (no network, no keys). CI runs it on each OS (check.yml) and on the
# newest Python (weekly.yml). Run from the repo root with the python that holds requirements.lock:
#   PY=$AI_EDITOR_HOME/venv/bin/python tests/demos.sh   (default home: ~/.ai-video-editor)
set -euo pipefail
PY=${PY:-python}
T=plugins/creator-teardown/skills/creator-teardown/scripts
A=plugins/ai-editor/skills
L=plugins/ai-editor/lib/ai_editor
failed=()
for s in "$T/fetch.py demo" "$T/editplan.py demo" "$T/visual.py demo" "$T/graphics.py demo" "$T/sound.py demo" \
  "$T/report.py demo" "$T/match.py demo" "$T/format_check.py demo" "$T/look.py demo" "$T/gemini.py demo" "$T/parallel.py demo" "$T/_progress.py demo" \
  "$A/cut/scripts/test_build_timeline.py" "$A/cut/scripts/test_retakes.py" "$A/cut/scripts/test_media.py" "$A/cut/scripts/verify_cut.py demo" "$A/cut/scripts/hook_check.py demo" "$A/cut/scripts/join.py demo" \
  "$A/cut/scripts/judge_cut.py demo" "$A/cut/scripts/read_cut.py demo" "$A/cut/scripts/transcribe.py demo" "$A/cut/scripts/trend.py demo" "$A/cut/scripts/splice_check.py demo" "$A/cut/scripts/script_match.py demo" "$A/cut/scripts/mirror.py demo" \
  "$L/keys.py" "$L/post.py demo" "$L/net.py demo" "$L/progress.py demo" "$L/profile.py demo" "$L/links.py demo" "$L/lock.py demo" "$L/models.py" "$L/run.py demo" "$L/review.py demo" "$L/styleskill.py demo" "$L/skillrules.py demo" "$A/skill-maker/scripts/skill_maker.py demo" "$L/home.py demo" "$L/askhook.py demo" "$L/assets.py demo" "$L/library.py demo" "$L/thumbs.py demo" "$L/custom.py demo" "$L/presets.py demo" "$L/launcher.py demo" "$L/live.py demo" \
  "$A/style-edit/scripts/plan.py demo" "$A/style-edit/scripts/edit.py demo" "$A/style-edit/scripts/export_nle.py demo" "$A/style-edit/scripts/chapters.py demo" "$A/style-edit/scripts/source.py demo" \
  "$A/style-edit/scripts/matte.py demo" "$A/clips/scripts/clips.py demo" "$A/setup/scripts/setup.py demo" \
  "$A/taste/scripts/taste.py demo" "$A/taste/scripts/learn.py demo" "$A/style-edit/scripts/face.py demo" "$A/style-edit/scripts/check.py demo" \
  "$A/style-edit/scripts/quality.py demo" "$A/style-edit/scripts/sfx.py demo" "$A/style-edit/scripts/sheet.py demo" "$A/style-edit/scripts/ai_tells.py demo" \
  "$A/style-edit/scripts/route.py demo" "$A/motion/scripts/motion.py demo" "$A/motion/scripts/check_clip.py demo" \
  "$A/motion/scripts/check_motion.py demo" "$A/motion/scripts/check_composition.py demo" "$A/motion/scripts/measure_ink.py demo" \
  "$A/motion/scripts/clip_motion.py demo" "$A/style-edit/scripts/style_check.py demo" "$A/product-video/scripts/gates.py demo" "$A/product-video/scripts/product.py demo" \
  "$A/product-video/scripts/journey.py demo" "$A/product-video/scripts/meter.py demo" "$A/product-video/scripts/sound.py demo" \
  "$A/improve/scripts/improve.py demo" "$A/update/scripts/update.py demo" "$A/style-edit/scripts/preview.py demo" "tests/golden.py demo" "tests/fresh_install.py demo"; do
  echo "== $s"
  # shellcheck disable=SC2086
  "$PY" $s || failed+=("$s")   # keep going: one CI run lists every failing check, not just the first
done
echo "== logo-pack/scripts/logos.mjs demo"
node "$A/logo-pack/scripts/logos.mjs" demo || failed+=("logos.mjs demo")
echo "== motion/scripts/verify.mjs demo"
node "$A/motion/scripts/verify.mjs" demo || failed+=("verify.mjs demo")
echo "== tests/test_alerts.mjs"
node tests/test_alerts.mjs || failed+=("tests/test_alerts.mjs")
echo "== tests/test_record.mjs"
node tests/test_record.mjs || failed+=("tests/test_record.mjs")
if ((${#failed[@]})); then printf 'FAILED: %s\n' "${failed[@]}"; exit 1; fi
echo "all demos ok"
