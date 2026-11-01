# Feature: a note from the client, shown on the calendar

Clients keep phoning us with things like "I'm allergic to ammonia dye" or
"please, the quiet chair". Let them write it while booking.

- Step 4 of the booking page ("Your details") gets an optional **Note** field,
  up to **500 characters**. It must be properly labelled — screen readers have
  to announce it, and a placeholder is not a label. The step must stay free of
  accessibility violations (axe, WCAG 2 A/AA).
- The note is saved with the booking. Leading/trailing whitespace is trimmed;
  an empty or whitespace-only note is stored as no note (`NULL`). Line breaks
  inside the note are kept. The public booking API rejects a note longer than
  500 characters with `400 bad_request` and creates nothing.
- The admin calendar shows the note on the booking's card, so the receptionist
  sees it at a glance. It is shown as plain text, exactly as the client wrote it.

The `bookings` table already has a `note` column that nothing uses yet.
