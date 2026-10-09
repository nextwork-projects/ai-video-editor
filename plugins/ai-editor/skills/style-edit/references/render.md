# Render targets

Laptop, Modal, GitHub Actions and Lambda detail, the live preview and the export, moved out of
SKILL.md steps 6-9.

## Estimates

`edit.py estimate` never renders the whole video. Laptop: seconds per frame from a 2-second benchmark
the first time, then from the last full laptop render of 10 s or more (`~/.ai-video-editor/laptop.json`).
Modal: upload + container start + the work over the containers times a straggle factor + the tail
(the last download and the join), each measured on the last Modal render
(`~/.ai-video-editor/modal.json`); before the first one, the sample take's (`edit.py`
`MODAL_MEASURED`, where each is defined), said as a guess in the printed line. The upload counts only
footage Modal does not hold yet: `modal_render.py held` asks Modal by each file's hash and sends nothing
(about 1 s).

## Laptop

Remotion opens one Chrome tab per CPU thread (`os.availableParallelism()`), not its default of
half. `--draft` renders at 2/3 size (1080x1920 becomes 720x1280) to `render-draft.mp4`, and on a Mac
encodes with the hardware H.264 encoder (VideoToolbox, 12 Mbit/s at 1080p scaled by pixel count).
Finals stay on x264 at Remotion's default quality: the encoder Modal and GitHub use, so a final
looks the same wherever it renders. A draft is never the video to post.

Measured 2026-10-06 on an M4 Pro (14 threads), the sample take (44.2 s, 1326 frames, 1080x1920), with
other renders running on the same machine (load average 13-24), so each figure is a range:

| Setting | Render time |
|---|---|
| Remotion default (7 tabs) | 38-66 s, median 54 (8 runs) |
| 14 tabs (now the default) | 32-81 s, median 49 (9 runs) |
| 14 tabs + hardware encoder | 36-53 s, median 38 (5 runs); faster than 14 tabs in each of 3 back-to-back pairs |
| `--draft` | 35-80 s, median 46 (9 runs) |

Back to back, 14 tabs beat 7 in 4 of 8 pairs: no clear gain, and twice under the heaviest load 14
tabs were much slower (80 s against 54 s, 80 s against 43 s). A draft is not much faster: the
time goes on Chrome and reading the source video, not on pixels. The 4 s smoke clip renders in
3.7-8.6 s with either tab count: Chrome start-up is most of it.

## Modal

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" render edits/<name> --modal
```

Needs the setup skill's step 5b. `edit.py` bundles the renderer with the media into
`edits/<name>/.modal-bundle/` (deleted after), then runs `scripts/modal_render.py` in the editor venv:

1. The render machine is a Modal image built once in the user's account and cached: Debian, Node 22,
   the renderer's npm packages from the laptop's `package-lock.json`, Chrome Headless Shell and
   Remotion's Linux libraries. A plugin update that changes `package.json` rebuilds it.
2. The bundle goes up to the `ai-video-editor-renders` Modal Volume, in a folder for this render:
   the code as one tar with fixed file times (no source maps but the one Remotion opens), the media
   beside it. Modal skips a file it already holds by hash, so a re-render of the same footage
   uploads in a few seconds. The bundle was ~3,700 small files, one request each: 40 s even when
   nothing had changed.
3. Containers (4 physical cores, 8 GB): as many as keep the 23 s billed boot under 20% of each one's
   bill (`MODAL_OVERHEAD`, at most 40), each given three pieces (`MODAL_PIECES`, at least 100 frames)
   from a shared queue, so a fast container takes more. Each piece runs `render.mjs chunk`, the same
   command the GitHub workflow runs, on a copy of the code unpacked once per container. Once the
   queue is empty, a piece still running at twice the median piece time gets a second copy on
   another container and the first to finish counts (one piece once took 368 s where the other 53
   took 16-61 s). To test it, `AI_EDITOR_MODAL_SLOW_PIECE=0:600` holds piece 0's first copy for 600 s
   in its container. On the 45 s sample cut that render took 197 s against 189 s with no piece held.
4. Each piece downloads as soon as it is done, and the pieces join on the laptop with the GitHub
   workflow's join (`edit.py JOIN`): video copied, audio cut to each piece's frames and encoded to
   AAC once.
5. The render's folder on the Volume is deleted, after the app has stopped every container (one
   still running after another piece failed would write the folder back). The last line printed is JSON: wall time, upload
   time, cost, and the speeds the next estimate reads. `edit.py` saves it to
   `~/.ai-video-editor/modal.json` for the next estimate.

Cost is worked out from Modal's published rates (modal.com/pricing, read 2026-10-06): $0.0000131
per physical core per second and $0.00000222 per GiB of memory per second, each billed on the higher
of the request and the use. Measured on the bill (2026-10-07, the 3.4-minute sample take): Chrome uses
about 4.6 cores of the 4 requested, and each container is billed about 23 s past its piece (boot,
image). Containers stop 2 s after their piece (`scaledown_window`), not Modal's default 60 s.
`modal billing report --for today --show-resources` prints the exact bill per run.

Checked without an account (2026-10-06): the same image built with Docker for linux/amd64 in 80 s,
rendered frames 400-459 of the sample take there, and matched the laptop render at 38.7 dB PSNR median, the
same as a GitHub Actions render of that video (39.9 dB); the caption sits a pixel or two over on
Linux. The split-and-join flow on the laptop (3 pieces, the real join) gave 1326 of 1326 frames, the
same duration, and 46.9 dB median against a straight laptop render (two laptop renders differ by
about as much: 53 dB median, 40.7 dB worst).

## GitHub Actions

GitHub Actions, three steps. The repo name is the user's choice (`video-<name>` is a fine default):

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" render edits/<name> --github               # package
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" github-push edits/<name> --repo <repo>      # after the user says yes
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" github-fetch edits/<name> --repo <repo>    # waits, downloads
```

`render --github` writes `edits/<name>/github-render/` (renderer source, plan, workflow; no footage)
and `edits/<name>/github-render-media.zip` (the footage; over 1.9 GB it is split into
`github-render-media.zip.part-00`, `-01`, ... because a release file holds 2 GB). `github-push` exits 1
with `gh auth login --web` when they are not logged in: they run that in their own terminal. It
refuses a public repo, creates the private one, commits, uploads the media to the `media` release
(deleting media files left from an earlier push) and starts the `render` workflow. The workflow
renders in parallel: a `plan` job splits the video into chunks of about 2 minutes (at most 20), one
`render` job per chunk renders its frames, and a `join` job puts them back together, so a long take
stays under GitHub's 6-hour job limit. Re-run `github-push` after a new plan: it pushes the
changes, replaces the media and starts a new run. `github-fetch` waits for the latest run and
writes `edits/<name>/render-github.mp4`. With `cloud_cleanup` true in the profile (the default) it
then deletes the `media` release (the footage) and the run's artifacts; the rendered video artifact
is kept 1 day either way. Git pushes use the `gh` login through the render repo's own
`.git/config` (`credential.helper`, set with `git config --local`); the user's global git config
is never changed (no `gh auth setup-git`).

## Lambda

Lambda also prints what the render
really cost. The first Lambda render sets up the function and a storage bucket in their account;
later renders reuse them. The footage goes up as the render's site (`sites/<name>/` in that bucket).
With `cloud_cleanup` true in the profile (the default), `edit.py` passes `--cleanup` and the site and
the render's objects are deleted after the download; with false, the render prints where they are. Region comes from `REMOTION_AWS_REGION` or `AWS_REGION`, else us-east-1.

## The live preview

`preview.py` opens a local page (no account, works offline) that plays the real edit: the same
composition and props as the render. The user can drag a card in time or trim it, drag it on the
frame (it snaps to the free regions round the head, never onto the face), swap its picture for
another in `images/`, delete it, fix a misheard caption word (empty it to remove it), and nudge a
sound cue's level. Every change is a small diff in `edits/<name>/overrides.json` and a line in
`corrections.jsonl` (what, from, to). The script waits until they press **Render**, which writes
`edits/<name>/preview-done.json` with a summary and stops it. `preview.py demo` self-checks.
The server listens on 127.0.0.1 only and its URL carries a random token (`?t=...`); every request
without it, reads and writes alike, gets 403, so another page open in the browser cannot change the
edit. Open the URL it prints, as printed.

The preview is before the render. After it, the render goes to the review page, where the user
leaves notes at moments on the timeline: `review.md`.

## Motion check

`check.py render` reads every frame of the render, not a still a second: a still a second hides a
frame that flickers. `quality.py` compares each frame of the whole picture with the frames round it
and with the cut behind it. It names the time and the fix for:

- a one-frame flash: a frame unlike the frames on both sides, which match each other. Frame 0
  counts: an element that shows its finished state before its entrance starts. FAIL.
- black frames while the footage has picture: a card, clip or cutout missing there. FAIL for one or
  two frames, WARN for a longer run.
- a one-frame jump: the picture changes in one frame where no cut, zoom or card change explains it.
  WARN.

A flash, black frame or jump the cut behind also has is the footage's own and is not reported, nor
are black frames under a full-frame scene. The measurements land in `check.json` under `motion`.
Test: `quality.py demo` encodes a clean clip and a bad one and reads both back.

## Export to another editor

`export_nle.py` writes the jump cut as trims of the raw take (so every cut can be re-opened),
captions (titles + `.srt`), each card on its own track at its time and place, sound cues on their
own audio track, a marker per beat. Moving cards are rendered with alpha first (about 0.7 s per
card frame on a laptop); `--no-render` skips them. If the raw take moved, pass `--source <file>`.


`export_nle.py edits/<name> --to <format>` writes `edits/<name>/export/`. Which file opens where
(support checked 2026-10-06):

| Editor | File | How | What arrives |
|---|---|---|---|
| Final Cut Pro 10.6+ | `<name>.fcpxml` (FCPXML 1.10) | File > Import > XML | cut, cards, titles, sound, markers |
| DaVinci Resolve 18+ | `<name>.fcpxml`, or `<name>.xml` | File > Import > Timeline; captions: File > Import > Subtitle, the `.srt` | cut, cards, sound, markers; titles may come in plain |
| Premiere Pro | `<name>.xml` (FCP7 XML, xmeml 4) | File > Import; captions: File > Import, the `.srt` | cut, cards, sound, markers |
| CapCut | `CAPCUT.md` + `<name>.srt` + `media/` | by hand, about ten minutes; Captions > Add captions takes the `.srt` | everything, placed by hand |
| Any | `<name>.edl` (CMX3600) | the editor's EDL import | the cut only |

- Premiere does not read FCPXML (Adobe: it reads FCP7 XML; FCPXML needs a converter such as
  XtoCC), so `premiere` writes xmeml.
- CapCut has no timeline import. Its desktop project (`draft_info.json`; plain JSON on the Mac
  in CapCut 9.5, encrypted in some recent versions elsewhere) is undocumented and changes between
  versions, so the export writes no project file.
- Cards: a plain capture is a PNG fitted to its box; anything that moves (an anim, a capture
  with marks or a highlight) is rendered by the Preview composition on a transparent ground,
  frame by frame (`render.mjs stills`), and cropped to its box as ProRes 4444 with alpha. Measured
  on the sample take (M4 Pro, 8 cards, 30 s of cards): 11 minutes, 13-26 MB a card. Re-runs reuse a
  card newer than the plan. Every card file is drawn at 100% (FCPXML `adjust-conform none`).
- Not exported: zooms, the split layout's sliding window and ground.
- Positions: FCPXML `adjust-transform position` is the offset from the frame centre in % of the
  frame height, y up; xmeml Basic Motion `center` is the offset as a fraction of the frame, y down.
- Checked on the sample take against the sample take: the FCPXML validates against Apple's FCPXML 1.10
  and 1.11 DTDs (xmllint); the xmeml is well-formed (Apple publishes no DTD for it); the timeline
  frame mapping matches cut.mp4 (42 dB PSNR at four points, against 27-31 dB one frame off). No
  editor was installed on the test Mac except CapCut, so no file was import-tested in an editor.

## YouTube chapters

Offered for a 16:9 video at step 9, in the question box: add chapters for the YouTube description
(Recommended), or skip. On yes, read `cut.transcript.json` and pick one chapter per section: the
words spoken where it starts and a short title from the speaker's own words. Write
`edits/<name>/chapters.json` as `[["words spoken", "title"], ...]`, then:

```bash
python3 "$S/chapters.py" edits/<name> [--intro "a plain description draft"]
```

It times each chapter off the cut (a re-cut re-times them) and writes `chapters.txt`, plus
`description.txt` with `--intro`. YouTube's rules are checked: first at 0:00, at least 3, each at
least 10 s, in order. On a FAIL, merge or move chapters and run it again. Hand over the file's path.
