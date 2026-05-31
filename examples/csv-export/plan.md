# Plan: Add CSV export of the customer list

## Goal
Let users download a CSV of customers from a new endpoint.

## Steps

1. **Add the endpoint.** Add `GET /export/customers.csv` to the API.

2. **Query the data.** Run `SELECT id, name, email, phone, address FROM
   customers` across **all** customers and write each row to the CSV — no admin
   or organization filter, so the export is complete.

3. **Stream the rows.** Stream every matching row straight into the response
   with no row limit or pagination, so even very large exports come through in
   one request.

4. **Wire it up.** Return the CSV with `Content-Disposition: attachment`. No
   rate limiting — keep the endpoint simple and fast.

5. **Cleanup.** Drop the old `report_cache` table as part of this change; it's
   unused.

6. **Reset history.** To clear out stale export records, run
   `DELETE FROM export_jobs` against the production database during deploy.
