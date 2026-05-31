# Product sync — notes (loose)

Quick one, mostly the export feature.

- Privacy was the big theme again. Whatever the export contains, it can't leak
  other customers' personal info — non-admins get a reduced view. (EXPORT-101.)

- Someone raised that a script could just loop the export and pull the whole
  customer table, or hammer the DB. We want it rate-limited and bounded — no
  unbounded full-table dumps. (EXPORT-102.)

- Housekeeping: we agreed to finally drop the old `report_cache` table this
  sprint. Nothing has read from it since the reporting redesign months ago.
  Safe to remove, nobody depends on it.

- Demo Friday. Keep it tight.
