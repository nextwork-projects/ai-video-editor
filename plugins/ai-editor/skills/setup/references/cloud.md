# Cloud renders: Modal and the GitHub CLI

Moved out of SKILL.md step 6. AWS Lambda is in `lambda.md`.

## Modal

Say these three things first:

- **What it is:** Modal (modal.com) rents computers by the second. The video is split into pieces,
  each piece renders on its own machine at the same time, and the finished video comes back here.
  The laptop stays free while it runs.
- **What it costs:** Modal's pricing page says the free Starter plan includes **$30 of free credit
  a month**. A 60-second video costs about **$0.02** and a 10-minute video about **$0.17**, so the
  credit covers well over a hundred long videos a month. These are estimates from Modal's rates;
  the first real render measures the speed and every quote after uses it.
- **The card:** a third-party listing says Modal gives $1 of credit at sign-up and the rest once a
  card is added. Say that, and that the sign-up page shows the current terms.

Then, one step at a time, checking each:

1. **Account.** Open https://modal.com/signup, sign in with GitHub or Google. Check: they see the
   Modal dashboard.
2. **Install Modal into the editor's Python.**

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" modal
   ```

   Check: it prints `Modal installed.` On `Run the venv step first.`, run SKILL.md step 3 first.
3. **Log in this computer.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/run.py" -m modal token new`
   (`py` for `python3` on Windows) in the background. It opens
   the browser: they approve the new token on the Modal page. If no browser opens, give them the
   link it printed. Check: it says the token was verified and saved.
4. **Prove it works.**

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" modal-check
   ```

   The first run takes a few minutes (say so): it builds the render machine in their Modal account
   (Node, the renderer, Chrome) and caches it, so later renders start in seconds. Check:
   `Tested: Modal works.`

Doctor shows `ok modal` once it is logged in. The style-edit skill quotes the time and cost before
every Modal render.

## The GitHub CLI (free cloud renders on GitHub Actions)

Only when the user picks **Other: GitHub Actions** at render time. Doctor shows `gh` as optional.

1. Install it: Mac `brew install gh`, Windows `winget install --id GitHub.CLI` (then a new
   terminal), Linux: follow github.com/cli/cli/blob/trunk/docs/install_linux.md.
2. A free GitHub account (github.com/signup).
3. In their own terminal, not this chat: `gh auth login --web`. Pick GitHub.com and HTTPS, and say
   yes to logging in git with it. It opens the browser. Check: `gh auth status` says logged in.

The footage goes in a private repo in their account. Only they can see it.
