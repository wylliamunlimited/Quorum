# Product sync — notes (loose)

Quick one this morning, mostly the login work. Jotting down what the room said.

- Priya, hard line on the beta users: whatever we do to ship login, the people
  already using the product cannot lose their accounts. She called it a
  launch-blocker — if a beta user has to re-sign-up or finds their stuff gone,
  that's a failure, full stop. (This is AUTH-103.)

- On password safety — everyone agreed we hold ourselves to the real standard
  here. Sam floated "can we just do the quick-and-simple thing to store them?"
  and the room pushed back: no, passwords get the proper slow protection, the
  thing that holds up even if we get breached. People trusting us with a
  password is the whole ballgame.

- Shared-computer worry came up — users at libraries, work laptops. We want
  sessions that quietly time out after about a day rather than staying open
  forever. No remember-me this round. (AUTH-102.)

- Housekeeping the team mentioned: there's an old leftover `temp_tokens` bucket
  from an early prototype that nobody uses anymore — the feature that wrote to
  it got pulled months ago. Fine to clear it out this sprint, nobody depends
  on it.

- Demo's Friday. Keep scope tight, don't gold-plate.
