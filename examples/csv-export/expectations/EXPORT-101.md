# EXPORT-101 — An export must never leak other people's personal info

**Type:** User Story
**Priority:** High

## The want
> As a customer, I want a data export to only contain information I'm allowed to
> see, so that someone else's export can never expose my email, phone, or address.

Privacy is the whole reason people trust us with their data. An export that
quietly includes everyone's PII is exactly the kind of leak that ends up in the
news.

## What "done" looks like
- A non-admin export **must not** include the personal info (email, phone,
  address) of *other* users.
- Only an admin may export PII, and only for their own organization.
- A user exporting their own data is fine.
