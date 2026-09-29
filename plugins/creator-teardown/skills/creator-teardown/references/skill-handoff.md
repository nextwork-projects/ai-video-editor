# Teardown to skill

The teardown describes what someone else does. A skill has to write scripts the user
will actually say out loud. That gap is this file.

## Gate first

Do not build a skill for every teardown. Ask:

1. **Is the format distinct** from the formats the user already has a skill or
   template for?
2. **Did it earn its numbers more than once?** One outlier is luck. Three videos in
   the same format, all above the creator's median, is a format.
3. **Would the user film it?** A format that only works with a register or persona
   the user does not have is a no.

Two noes: add the finding to the closest existing skill or doc instead, and say that
is what you are doing.

## Naming

Name it after the **format**, not the creator. The creator lives in
`references/teardown.md`. The skill name has to still make sense when a second
creator does the same format.

## Copy the structure, not the voice

The default failure is a skill that reproduces the source creator's hype register.
The new skill defines only the format: beat count and order, hook shape, item count,
runtime, close type, and what the on-screen text carries.

If the user has a voice guide, the new skill points at it instead of copying rules
into itself, so it cannot go stale. If they don't, write a short "Voice" section from
the teardown's patterns-we-reject list.

If the source format **depends** on a move the user won't make (a throat-clearing
hook, a comment-bait close), do not quietly drop it. State the substitution: "the
source opens with 'here's the thing'; we open with the numbered promise."

## What the new skill folder gets

```
~/.claude/skills/<format-name>/
  SKILL.md
  references/
    teardown.md          <- the teardown, copied here unchanged
```

The `description` in the frontmatter decides whether the skill ever fires. List the
phrases the user would actually type.

## Finally

Write one script with the new skill on a topic the user gives before calling it done.
A format that reads well in a teardown and produces a script nobody would say out
loud is a failed teardown.
