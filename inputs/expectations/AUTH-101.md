# AUTH-101 — People need to trust us with their password

**Type:** User Story
**Status:** In Progress
**Priority:** High

## The want
> As someone signing up, I want to know that my password stays safe even if the
> company gets hacked, so that a breach somewhere else can't get into the rest
> of my life.

In user interviews this came up over and over — people reuse passwords and are
scared of one leak cascading. Our credibility depends on getting this right.

## What "done" looks like (user outcomes)
- If our user database ever leaked, attackers should **not** be able to recover
  or reuse people's actual passwords.
- We protect stored passwords with the **modern industry standard for
  passwords** — the deliberately slow approach. A quick, simple checksum is
  **not** good enough here.
- A user never sees or has to think about any of this — it just has to be true.
