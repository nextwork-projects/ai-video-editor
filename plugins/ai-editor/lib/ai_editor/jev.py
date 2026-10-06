"""A small client for TypeSafe's Jev (https://docs.typesafe.ai/api.md). Stdlib only.

    from ai_editor import jev
    answers = jev.ask("context", {"q1": jev.noul("Is `a` ...?", a="...")}, log_dir=edit_dir)
    answers["q1"]["noul"]            # 0..1, the probability the answer is yes

Jev reads text and returns typed judgements with probabilities. It does not count, do
arithmetic or order times, and gets worse as the state fills with unrelated text, so the
caller keeps all timings in code and gives each question only the words it is about,
inside the question's own `instructions`.

Pricing: input tokens only, $0.042 per million (models.md, jev-1.13). Every call appends
{input_tokens, cost_usd, ...} to <log_dir>/jev-usage.jsonl.

Offline: pass canned={qid: answer} (tests) and no request is made.
"""
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
USD_PER_MTOK = 0.042
# 64k tokens per request (state + every question). Stay well under it, by a rough
# 4-characters-per-token estimate, and split bigger batches into several requests.
MAX_REQUEST_CHARS = 120_000
RETRY = (429, 500, 502, 503, 529)


class JevError(RuntimeError):
    pass


def noul(question, true=None, false=None, **data):
    """A yes/no question. `data` fields are sent inside the instructions, so each
    question carries only its own slice of the transcript."""
    q = {"type": "noul", "instructions": {**data, "question": question} if data else question}
    if true or false:
        q["criteria"] = {"true": true or "", "false": false or ""}
    return q


def choice(question, options, **data):
    """Pick one of `options` ({option: description}). Jev leans to the first option,
    so put the default first."""
    return {"type": "choice", "criteria": options,
            "instructions": {**data, "question": question} if data else question}


def _post(body, key, tries=5):
    data = json.dumps(body).encode()
    for attempt in range(tries):
        req = urllib.request.Request(URL, data=data, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "User-Agent": "ai-video-editor"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code in RETRY and attempt < tries - 1:
                wait = e.headers.get("retry-after")
                time.sleep(float(wait) if wait and wait.replace(".", "").isdigit() else 2 ** attempt)
                continue
            raise JevError(f"TypeSafe HTTP {e.code}: {msg}")
        except (urllib.error.URLError, OSError) as e:
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise JevError(f"TypeSafe unreachable: {e}")


def _batches(questions, state):
    base = len(json.dumps(state))
    batch, size = {}, base
    for qid, q in questions.items():
        n = len(json.dumps(q))
        if batch and size + n > MAX_REQUEST_CHARS:
            yield batch
            batch, size = {}, base
        batch[qid] = q
        size += n
    if batch:
        yield batch


def ask(state, questions, key=None, log_dir=None, canned=None, model=MODEL):
    """{qid: answer} for every question. Splits into several requests when needed."""
    if not questions:
        return {}
    answers, usage = {}, {"input_tokens": 0, "output_tokens": 0, "requests": 0}
    if canned is not None:
        answers = {q: canned[q] for q in questions if q in canned}
        missing = [q for q in questions if q not in canned]
        if missing:
            raise JevError(f"offline: no canned answer for {missing[:5]}")
        used = "offline"
    else:
        if not key:
            raise JevError("no TypeSafe key")
        used = model
        for batch in _batches(questions, state):
            r = _post({"state": state, "model": model, "questions": batch}, key)
            answers.update(r.get("answers", {}))
            used = r.get("model", used)
            for k in ("input_tokens", "output_tokens"):
                usage[k] += int(r.get("usage", {}).get(k, 0))
            usage["requests"] += 1
    rec = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": used, "questions": len(questions),
           **usage, "cost_usd": round(usage["input_tokens"] * USD_PER_MTOK / 1e6, 6)}
    if log_dir:
        with open(Path(log_dir) / "jev-usage.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
    ask.last_usage = rec
    return answers


ask.last_usage = None


def yes(answer):
    """The yes-probability of a Noul answer, or the top-option probability of a Choice."""
    if answer.get("type") == "noul":
        return float(answer["noul"])
    return max(answer.get("probabilities", {}).values(), default=math.nan)


if __name__ == "__main__":   # self-check, offline
    qs = {f"q{i}": noul("Is `x` a fruit?", x=w) for i, w in enumerate(["apple", "car"])}
    assert qs["q0"]["instructions"] == {"x": "apple", "question": "Is `x` a fruit?"}
    a = ask("", qs, canned={"q0": {"type": "noul", "noul": 0.9}, "q1": {"type": "noul", "noul": 0.1}})
    assert yes(a["q0"]) == 0.9 and ask.last_usage["cost_usd"] == 0
    big = {f"q{i}": noul("x" * 1000) for i in range(300)}
    assert sum(len(b) for b in _batches(big, "s")) == 300 and len(list(_batches(big, "s"))) == 3
    print("jev ok")
