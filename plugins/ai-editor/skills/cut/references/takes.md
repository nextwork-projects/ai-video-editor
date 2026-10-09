# Several takes of one video

Read this when the user hands over two or more video files at once. `links.py route` asks it as one
`ask` item; the cut skill alone asks it itself.

## Ask first

One question box, before anything is transcribed:

> Are these files one video, or separate videos?
> - **One video, in this order (Recommended).** List the files in file-name order. If the names say
>   nothing about order (`DSC_0042`, `DSC_0017`), order them by when they were filmed instead
>   (`--sort created`) and say so.
> - **Separate videos.** Each file gets its own `edits/<name>/` and its own cut.

If the user gives another order, use theirs. Skip the question only when they already said ("these are
parts of one video", "cut each of these").

## One video: join, then cut

```bash
python3 "$S/join.py" edits/<name>/joined.mp4 <file1> <file2> ...     # the order given
python3 "$S/join.py" edits/<name>/joined.mp4 --sort created <files>  # by the camera's timestamp
```

`<name>` comes from the first file. The join makes a new file; the originals are never touched.
Every clip is fitted to the first clip's picture size (rotation applied, other sizes get black bars),
one frame rate and 48 kHz audio, so phone clips filmed upright and sideways, at different frame rates or
with a variable frame rate join cleanly. It prints one `ok` line per clip and writes
`joined.mp4.parts.json` (where each file starts in the joined video).

Then run the normal cut with `edits/<name>/joined.mp4` as `<source>`. Last take wins across files too:
a line said again in the next file is a retake.

**Exit 1 (`FAIL ... audio and video lengths differ`):** never cut that file. Say which clip failed and
ask for that file again (a re-export or the original from the phone).
