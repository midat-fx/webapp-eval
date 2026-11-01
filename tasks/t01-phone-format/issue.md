# Booking fails when the phone number has spaces or dashes

Customers type their number the way it's printed on a business card:
`+7 701 555 12 34`, `+7 (701) 555-12-34`, `+7-701-555-12-34`. The booking wizard
then refuses to confirm with *"Check the name and phone (format +7701…)"*, and
the "Join the waitlist" form just says it didn't work. Most people give up
rather than guess what format we want.

Expected:

- Spaces, dashes, dots and parentheses are formatting, not part of the number.
  All of the above must be accepted, both when booking and when joining the
  waitlist, including when the public API is called directly.
- They are the same number. `+7 (701) 555-12-34` and `+77015551234` must end up
  as **one** client in the admin "Clients" list, stored as `+77015551234`.
- Things that still aren't phone numbers (`call me`, `+7 701`) are rejected as
  before.
