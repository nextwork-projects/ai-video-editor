#!/usr/bin/env python3
"""Stills, estimates and renders for a plan.json. Stdlib only.

    python3 edit.py stills   edits/NAME [--plan plan.json] [--no-check]   runs check.py plan, then PNGs into edits/NAME/stills/
    python3 edit.py estimate edits/NAME [--plan plan.json]   laptop time (measured) + Lambda cost (guess)
    python3 edit.py render   edits/NAME [--plan plan.json] [--lambda]   -> edits/NAME/render.mp4
    python3 edit.py render   edits/NAME [--plan plan.json] --github   -> edits/NAME/github-render/ + github-render-media.zip
    python3 edit.py github-push  edits/NAME --repo NAME [--plan plan.json]   private repo + media release, starts a render
    python3 edit.py github-fetch edits/NAME --repo NAME [--plan plan.json]   waits, then -> edits/NAME/render-github.mp4
    python3 edit.py demo     self-check

A plan named plan-XYZ.json writes stills-XYZ/ and render-XYZ.mp4, so two aspects can sit side by side.
The renderer lives in ~/.ai-video-editor/remotion (the setup skill installs it; this script
refreshes its source from the plugin on every run).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
REMOTION = HOME / "remotion"
PLUGIN = Path(__file__).resolve().parents[3]            # plugins/ai-editor
SRC = PLUGIN / "remotion"
SETUP = PLUGIN / "skills" / "setup" / "scripts" / "setup.py"


def sync_renderer():
    """Install on first use; afterwards copy the source over so plugin updates take effect."""
    same_deps = (REMOTION / "package.json").exists() and \
        (REMOTION / "package.json").read_bytes() == (SRC / "package.json").read_bytes()
    if not (REMOTION / "node_modules" / "remotion").exists() or not same_deps:
        subprocess.run([sys.executable, str(SETUP), "remotion"], check=True)
    shutil.copytree(SRC / "src", REMOTION / "src", dirs_exist_ok=True)
    for f in ("render.mjs", "tsconfig.json"):
        shutil.copy2(SRC / f, REMOTION / f)


def proxy_filter(sw, sh, w, h):
    """Fit the cut to the output: same shape scales, wider source is centre-cropped,
    taller source (vertical into 16:9) sits over a blurred copy of itself."""
    src, dst = sw / sh, w / h
    if abs(src - dst) < 0.02:
        return f"scale={w}:{h},setsar=1"
    if src > dst:
        return f"scale=-2:{h},crop={w}:{h},setsar=1"
    return (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"gblur=sigma=40,eq=brightness=-0.08[bg];[b]scale=-2:{h}[fg];"
            f"[bg][fg]overlay=(W-w)/2:0,setsar=1")


def prepare_public(edit, plan, tag):
    """A folder with only what the render reads: the cut at output size (keyframe every
    15 frames, which keeps frame seeking fast) and the card images."""
    pub = edit / f".render{tag}"
    pub.mkdir(exist_ok=True)
    cut, proxy = edit / plan["video"], pub / plan["video"]
    if not cut.exists():
        sys.exit(f"ERROR: {cut} missing")
    if not proxy.exists() or proxy.stat().st_mtime < cut.stat().st_mtime:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(Path(__file__).parent))
        from plan import probe
        m = probe(cut)
        print(f"preparing {plan['width']}x{plan['height']} copy of {cut.name}", flush=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cut), "-filter_complex",
                        proxy_filter(m["width"], m["height"], plan["width"], plan["height"]),
                        "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-g", "15",
                        "-keyint_min", "15", "-sc_threshold", "0", "-pix_fmt", "yuv420p",
                        "-c:a", "copy", str(proxy)], check=True)
    # Card images, plus every image an anim's props name (a logo card, a scene's icons and logos).
    rels = [c["src"] for c in plan["cards"] if c.get("src")]
    rels += re.findall(r'"(images/[^"]+)"', json.dumps([c.get("anim") for c in plan["cards"]]))
    rels += [c["src"] for c in plan.get("sfx", [])]   # sound cues, from sfx.py
    for rel in dict.fromkeys(rels):
        src = edit / rel
        if not src.exists():
            sys.exit(f"ERROR: {src} missing" + (" (run sfx.py build, then plan.py)" if rel.startswith(".sfx/") else ""))
        (pub / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, pub / rel)
    return pub


def still_frames(plan):
    """Frames that show each part of the edit: the opening, a caption, a zoom, then every card
    (4-card, 5-card, ...) once its entrance and animation have settled. Every card but a logo tile
    moves, so it also gets N-card-early and N-card-late; a card that swaps in right after the
    one before it gets N-swap, mid-move."""
    fps, last = plan["fps"], plan["durationInFrames"] - 1
    chunks, zooms, cards = plan["captions"]["chunks"], plan["zooms"], plan["cards"]
    busy = lambda t: any(z["start"] <= t < z["end"] for z in zooms) or any(c["start"] <= t < c["end"] for c in cards)
    mid = lambda a: (a["start"] + a["end"]) / 2
    frames = {"1-opening": 0.5}
    plain = [mid(c) for c in chunks if not busy(mid(c))]
    if chunks:
        frames["2-caption"] = plain[0] if plain else mid(chunks[0])
    if zooms:
        z = zooms[0]
        inside = [mid(c) for c in chunks if z["start"] <= mid(c) < z["end"]]
        frames["3-zoom"] = inside[0] if inside else mid(z)
    for i, c in enumerate(cards):
        frames[f"{4 + i}-card"] = max(c["start"], min(c["start"] + 1.6, c["end"] - 0.25))
        if c.get("lane") != "logo":
            frames[f"{4 + i}-card-early"] = c["start"] + 0.5
            frames[f"{4 + i}-card-late"] = c["end"] - 0.3
            prev = [p for p in cards[:i] if p.get("lane") != "logo"]
            if prev and 0 <= c["start"] - prev[-1]["end"] < 1.2:
                frames[f"{4 + i}-swap"] = c["start"] + 0.12
    return {k: min(last, round(t * fps)) for k, t in frames.items()}


def aws_env():
    """AWS keys saved by `setup.py awskey`, layered over the real environment."""
    env, f = dict(os.environ), HOME / "aws.env"
    if f.exists():
        for line in f.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() and v.strip():
                env.setdefault(k.strip(), v.strip())
    return env


def node(*args):
    return subprocess.run(["node", str(REMOTION / "render.mjs"), *map(str, args)], cwd=REMOTION,
                          check=True, capture_output=args[0] in ("bench", "lambda-estimate"), text=True,
                          env=aws_env())


def estimate(plan_path, pub):
    b = json.loads(node("bench", pub, plan_path).stdout.strip().splitlines()[-1])
    laptop = b["bundle_s"] + b["s_per_frame"] * b["frames"]
    lam = json.loads(node("lambda-estimate", plan_path).stdout.strip().splitlines()[-1])
    print(f"Laptop: about {laptop / 60:.1f} min (measured {b['bench_s']:.1f} s for "
          f"{b['bench_frames']} frames, {b['frames']} frames in all).")
    print(f"Lambda: about {lam['wall_s']} s on {lam['lambdas']} Lambdas in {lam['region']}, "
          f"about ${lam['usd']:.3f}. A guess until a real render is measured; the render prints the real cost.")


WORKFLOW = """name: render
on: workflow_dispatch
permissions:
  contents: read
jobs:
  render:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: if [ -f package-lock.json ]; then npm ci; else npm install; fi
      - run: npx remotion browser ensure
      - run: gh release download media -R "$GITHUB_REPOSITORY" -p {zip}
        env:
          GH_TOKEN: ${{{{ github.token }}}}
      - run: unzip -q {zip} -d public && rm {zip}
      - run: node render.mjs local public plan.json out/render.mp4
      - uses: actions/upload-artifact@v4
        with:
          name: render
          path: out/render.mp4
          retention-days: 7
"""

README = """# {name}: render on GitHub Actions

Made by the AI video editor (`edit.py render --github`). Keep this repo private: the footage is in
it, as the `{zip}` asset of the `media` release.

Actions > render > Run workflow renders `plan.json` with Remotion. The video is the `render`
artifact on the finished run (kept 7 days). `edit.py github-fetch` downloads it.
"""


def gh_paths(edit, tag):
    """(git folder, media zip) for one plan."""
    return edit / f"github-render{tag}", edit / f"github-render{tag}-media.zip"


def package_github(edit, plan_path, pub, tag):
    """The renderer source + plan in a git folder (no media), the media zipped beside it."""
    repo, zip_path = gh_paths(edit, tag)
    shutil.rmtree(repo / "src", ignore_errors=True)
    shutil.copytree(SRC / "src", repo / "src")
    for f in ("package.json", "render.mjs", "tsconfig.json"):
        shutil.copy2(SRC / f, repo / f)
    lock = REMOTION / "package-lock.json"          # npm ci on the runner then matches this laptop
    if lock.exists():
        shutil.copy2(lock, repo / "package-lock.json")
    shutil.copy2(plan_path, repo / "plan.json")
    (repo / ".gitignore").write_text("node_modules/\nout/\npublic/\n*.mp4\n*.zip\n")
    (repo / "README.md").write_text(README.format(name=edit.name, zip=zip_path.name))
    wf = repo / ".github" / "workflows" / "render.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(WORKFLOW.format(zip=zip_path.name))
    zip_path.unlink(missing_ok=True)
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", pub)
    mb = lambda p: sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and ".git" not in f.parts) / 1e6
    print(f"{repo} ({mb(repo):.1f} MB)\n{zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")
    return repo, zip_path


def gh(*args, check=True, cwd=None):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, cwd=cwd)
    if check and r.returncode:
        sys.exit(f"ERROR: gh {' '.join(args)}\n{r.stderr.strip()}")
    return r


def need_gh():
    if not shutil.which("gh"):
        sys.exit("ERROR: the GitHub CLI (gh) is missing. The setup skill's doctor prints the install command.")
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode:
        print("Not logged in to GitHub. In your own terminal, run:\n  gh auth login --web")
        sys.exit(1)


def github_push(edit, repo_name, tag):
    need_gh()
    repo, zip_path = gh_paths(edit, tag)
    if not (repo / ".github").exists() or not zip_path.exists():
        sys.exit(f"ERROR: {repo} missing: run edit.py render {edit} --github first")
    view = gh("repo", "view", repo_name, "--json", "isPrivate,nameWithOwner,url", check=False)
    info = json.loads(view.stdout) if view.returncode == 0 else None
    if info and not info["isPrivate"]:
        sys.exit(f"ERROR: {info['nameWithOwner']} is public. The footage goes in this repo: use a private one.")
    git = lambda *a, **kw: subprocess.run(["git", *a], cwd=repo, check=True, **kw)
    if not (repo / ".git").exists():
        git("init", "-q", "-b", "main")
    gh("auth", "setup-git")                        # git pushes with the gh login
    git("add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo).returncode:
        who = subprocess.run(["git", "config", "user.email"], cwd=repo, capture_output=True, text=True).stdout.strip()
        ident = [] if who else ["-c", "user.name=ai-video-editor", "-c", "user.email=ai-video-editor@users.noreply.github.com"]
        subprocess.run(["git", *ident, "commit", "-q", "-m", "Render plan"], cwd=repo, check=True)
    if info is None:
        print(f"creating private repo {repo_name}")
        gh("repo", "create", repo_name, "--private", "--source", ".", "--push", cwd=repo)
        info = json.loads(gh("repo", "view", repo_name, "--json", "isPrivate,nameWithOwner,url").stdout)
    else:
        if subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo, capture_output=True).returncode:
            git("remote", "add", "origin", info["url"] + ".git")
        git("push", "-q", "-u", "origin", "HEAD:main")
    full = info["nameWithOwner"]
    print(f"uploading {zip_path.name} ({zip_path.stat().st_size / 1e6:.0f} MB)", flush=True)
    if gh("release", "view", "media", "-R", full, check=False).returncode == 0:
        gh("release", "upload", "media", str(zip_path), "--clobber", "-R", full)
    else:
        gh("release", "create", "media", str(zip_path), "--title", "media", "-R", full,
           "--notes", "Footage for the render workflow. Keep this repo private.")
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))
    for attempt in range(10):                      # a just-pushed workflow takes a few seconds to register
        if gh("workflow", "run", "render.yml", "-R", full, check=attempt == 9).returncode == 0:
            break
        time.sleep(3)
    # github-fetch downloads the run started here, never an older one.
    (edit / f"github{tag}.json").write_text(json.dumps({"repo": full, "started": started}))
    print(f"render started: {info['url']}/actions/workflows/render.yml")


def github_fetch(edit, repo_name, tag):
    need_gh()
    meta = edit / f"github{tag}.json"
    since = json.loads(meta.read_text())["started"] if meta.exists() else ""
    runs = []
    for _ in range(20):                            # the run triggered by github-push can take a moment to appear
        runs = [r for r in json.loads(gh("run", "list", "-R", repo_name, "--workflow", "render.yml", "-L", "5",
                                         "--json", "databaseId,url,createdAt").stdout) if r["createdAt"] >= since]
        if runs:
            break
        time.sleep(3)
    if not runs:
        sys.exit("ERROR: no render run since the last push: run edit.py github-push first")
    run_id = str(runs[0]["databaseId"])
    print(f"waiting for {runs[0]['url']}", flush=True)
    if subprocess.run(["gh", "run", "watch", run_id, "-R", repo_name, "--exit-status"]).returncode:
        sys.exit(f"ERROR: the render failed. Open {runs[0]['url']} for the log.")
    tmp = edit / f".github-download{tag}"
    shutil.rmtree(tmp, ignore_errors=True)
    gh("run", "download", run_id, "-R", repo_name, "-n", "render", "-D", str(tmp))
    out = edit / f"render-github{tag}.mp4"
    shutil.move(str(tmp / "render.mp4"), out)
    shutil.rmtree(tmp, ignore_errors=True)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(out)], capture_output=True, text=True).stdout.strip()
    print(f"{out} ({float(dur):.1f} s)")


def demo():
    plan = {"fps": 30, "durationInFrames": 900,
            "captions": {"chunks": [{"start": 1, "end": 2}, {"start": 5, "end": 6}]},
            "zooms": [{"start": 0.5, "end": 3}], "cards": [{"start": 20, "end": 23}, {"start": 25, "end": 26}]}
    f = still_frames(plan)
    assert f == {"1-opening": 15, "2-caption": 165, "3-zoom": 45, "4-card": 648, "4-card-early": 615, "4-card-late": 681,
                 "5-card": 772, "5-card-early": 765, "5-card-late": 771}, f
    plan["cards"][1]["start"] = 23.5
    assert still_frames(plan)["5-swap"] == 709
    assert "crop=1080:1920" in proxy_filter(1920, 1080, 1080, 1920)
    assert "gblur" in proxy_filter(1080, 1920, 1920, 1080)
    assert proxy_filter(3840, 2160, 1920, 1080).startswith("scale=1920:1080")
    import tempfile, zipfile
    with tempfile.TemporaryDirectory() as t:
        edit, pub = Path(t) / "fake", Path(t) / "fake" / ".render"
        (pub / "images").mkdir(parents=True)
        (pub / "cut.mp4").write_bytes(b"x" * 100)
        (pub / "images" / "a.png").write_bytes(b"png")
        (edit / "plan.json").write_text('{"video": "cut.mp4"}')
        repo, z = package_github(edit, edit / "plan.json", pub, "")
        for f in (".github/workflows/render.yml", "plan.json", "package.json", "render.mjs", "src/index.ts"):
            assert (repo / f).exists(), f
        assert not list(repo.rglob("*.mp4")), "footage leaked into the git folder"
        assert set(zipfile.ZipFile(z).namelist()) >= {"cut.mp4", "images/a.png"}, zipfile.ZipFile(z).namelist()
        assert "-p github-render-media.zip" in (repo / ".github/workflows/render.yml").read_text()
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stills", "estimate", "render", "github-push", "github-fetch"])
    ap.add_argument("edit")
    ap.add_argument("--plan", default="plan.json")
    ap.add_argument("--lambda", dest="use_lambda", action="store_true")
    ap.add_argument("--github", action="store_true", help="package for GitHub Actions instead of rendering here")
    ap.add_argument("--repo", help="GitHub repo name (github-push, github-fetch)")
    ap.add_argument("--no-check", action="store_true", help="stills even when check.py plan finds a FAIL")
    a = ap.parse_args()
    edit = Path(a.edit).resolve()
    plan_path = edit / a.plan
    plan = json.loads(plan_path.read_text())
    tag = plan_path.stem[len("plan"):]
    if a.cmd.startswith("github-"):
        if not a.repo:
            sys.exit("ERROR: --repo NAME is required")
        return (github_push if a.cmd == "github-push" else github_fetch)(edit, a.repo, tag)
    sync_renderer()
    pub = prepare_public(edit, plan, tag)
    if a.cmd == "stills":
        # check.py plan first: prints what it finds, stops the stills only on a FAIL
        chk = subprocess.run([sys.executable, str(Path(__file__).parent / "check.py"), "plan", str(edit), "--plan", a.plan])
        if chk.returncode and not a.no_check:
            sys.exit("check.py plan found a FAIL: fix it and plan again (edit.py stills --no-check to look anyway)")
        pairs = [f"{k}={v}" for k, v in still_frames(plan).items()]
        node("stills", pub, plan_path, edit / f"stills{tag}", *pairs)
    elif a.cmd == "estimate":
        estimate(plan_path, pub)
    elif a.github:
        package_github(edit, plan_path, pub, tag)
    elif a.use_lambda:
        node("lambda", pub, plan_path, edit / f"render{tag}.mp4", re.sub(r"[^a-z0-9-]+", "-", f"ai-editor-{edit.name}{tag}".lower()))
    else:
        node("local", pub, plan_path, edit / f"render{tag}.mp4")


if __name__ == "__main__":
    main()
