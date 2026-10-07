---
type: llm
focus: trace
---
PASS if Claude treats the TikTok link as a creator to copy (creator-teardown on somecreator) and ./my-take.mp4 as the video to edit, without asking what the link is, and handles the creator before cutting.
FAIL if it asks whether the TikTok link is the user's own video, a creator or something else, or cuts before the creator step.
