# Shapes

The files Claude writes in product-video. The rules behind them: `story.md` (story, shots, words) and
`brief.md` (music rights, logging in).

## brief.json

From the three brief calls, before the deep crawl. `product.py plan` refuses without it.

```json
{"tagline": "the site's own tagline", "must_show": ["the jobs, in the site's words"],
 "audience": "new users", "action": "visit the URL", "must_include": ["https://example.com/a-page"]}
```

## story.json (the rendered film)

Written from `storyboard.md`, never the other way round. Hook, then an `action` and a `result` per use
case in the user's journey order, a `payoff`, the `end`. You never write times beyond an optional `dur`.

```json
{"beats": [
  {"job": "hook", "flow": "search", "text": "<the promise, in the site's words>", "dur": 2.8},
  {"job": "action", "flow": "search", "steps": [0, 1], "text": "<the search box's label>"},
  {"job": "result", "flow": "search", "dur": 2.0},
  {"job": "payoff", "flow": "library", "steps": [1], "dur": 3.0},
  {"job": "end"}]}
```

- `job`: `hook`, `action`, `result`, `payoff`, `end`.
- `flow`: a flow id from `flows.json`. `steps`: its step numbers as `flows/<id>.states.json` lists them,
  from 0. `wait`s are not steps and the scrolls that bring a target into view are skipped, so
  `[{"wait": 0.8}, {"click": "text=Search"}, {"write": "github"}]` has steps 0 (the click) and 1 (the write).
- `text`: at most about 5 words, the site's own (`product.py copy` lists them). Never an invented line.

The older shot film (`"shots": [...]`, for a product whose own animation is the point) is in `story.md`
"story.json (the shot film)".
