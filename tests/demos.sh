#!/usr/bin/env bash
# Every script's self-check (no network, no keys). CI runs it on each OS (check.yml) and on the
# newest Python (weekly.yml). Run from the repo root with the python that holds requirements.lock:
#   PY=~/.ai-video-editor/venv/bin/python tests/demos.sh
set -euo pipefail
PY=${PY:-python}
T=plugins/creator-teardown/skills/creator-teardown/scripts
A=plugins/ai-editor/skills
L=plugins/ai-editor/lib/ai_editor
for s in "$T/fetch.py demo" "$T/editplan.py demo" "$T/visual.py demo" "$T/graphics.py demo" "$T/sound.py demo" \
  "$T/report.py demo" "$T/look.py demo" "$T/gemini.py demo" \
  "$A/cut/scripts/test_build_timeline.py" "$A/cut/scripts/test_retakes.py" "$A/cut/scripts/test_media.py" \
  "$L/keys.py" "$L/jev.py" "$L/links.py demo" "$L/lock.py demo" "$L/models.py" \
  "$A/style-edit/scripts/plan.py demo" "$A/style-edit/scripts/edit.py demo" "$A/style-edit/scripts/export_nle.py demo" \
  "$A/style-edit/scripts/matte.py demo" "$A/clips/scripts/clips.py demo" "$A/setup/scripts/setup.py demo" \
  "$A/taste/scripts/taste.py demo" "$A/style-edit/scripts/face.py demo" "$A/style-edit/scripts/check.py demo" \
  "$A/style-edit/scripts/quality.py demo" "$A/style-edit/scripts/sheet.py demo" "$A/style-edit/scripts/ai_tells.py demo" \
  "$A/style-edit/scripts/route.py demo" "$A/product-video/scripts/gates.py demo" "$A/product-video/scripts/product.py demo" \
  "$A/product-video/scripts/journey.py demo" "$A/product-video/scripts/meter.py demo" "$A/product-video/scripts/sound.py demo" \
  "$A/improve/scripts/improve.py demo" "tests/golden.py demo"; do
  echo "== $s"
  # shellcheck disable=SC2086
  "$PY" $s
done
echo "== tests/test_record.mjs"
node tests/test_record.mjs
echo "all demos ok"
