---
type: llm
focus: trace
---
PASS if Claude changes only the Duolingo card (a `plan.py beat` on card:1, 0:15 or Duolingo with a new box above the caption band, or the same change written into that one beat), or asks which card or where to move it with concrete choices (AskUserQuestion, or options in its reply when the session has none), and then plans to re-render only that moment (`edit.py stills --at` and `edit.py patch`) and hand over on the review page.
FAIL if it re-runs the whole style edit (route.py beats, a new visuals.json, every card re-picked), moves or drops other cards, changes the caption position or size instead of the card, or renders the whole video without saying why.
