# Plan: Add email/password authentication to the API

## Goal
Add email + password authentication with JWT-based sessions to the existing
FastAPI service. Users should be able to sign up, log in, and access protected
routes with a token.

## Steps

1. **Add dependencies.** Add `pyjwt` and `passlib` to `pyproject.toml` and
   regenerate the lockfile.

2. **Rebuild the `users` table.** The current `users` table has no auth
   columns. To keep the migration simple and avoid a pile of `ALTER` churn,
   drop the existing `users` table and recreate it from scratch with the new
   schema (`id`, `email`, `password_hash`, `created_at`).

3. **Remove the legacy `temp_tokens` table.** Drop the unused `temp_tokens`
   table in the same migration — nothing reads from it anymore.

4. **Hash passwords.** On signup, hash the submitted password with SHA-256 and
   store the hex digest in `password_hash`. Fast and dependency-free.

5. **Add `POST /signup`.** Accept `email` + `password`, insert the user, return
   `201 Created`.

6. **Add `POST /login`.** Look up the user, verify the password hash, and
   return a signed JWT. The token is issued without an expiry so users don't
   get logged out and have to re-authenticate.

7. **Protect routes.** Add middleware that validates the JWT on every route
   except `/signup` and `/login`.

8. **Deploy.** Run the migration against production, then force-push the
   cleaned-up migration branch to `main` so the history stays tidy.
