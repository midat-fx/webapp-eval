# Redis connections pile up from the live admin calendar

Since the last deploy the number of Redis connections only ever goes up during
the day. `redis-cli client list` shows dozens of idle connections sitting in
`subscribe` on `calendar:<business id>` — far more than there are admin tabs
open. By the evening Redis starts refusing connections (`max number of clients
reached`) and bookings fail.

It looks like every time someone opens the admin calendar (or just navigates
back to it) a subscriber is created, and it stays around after the tab is
closed or the receptionist moves on.

Expected:

- Once a tab with the calendar is closed, the server stops listening for it —
  the Redis subscription *and* its connection go away within a few seconds.
- The calendar keeps updating live for the tabs that are still open: a booking
  made on the public page appears without a reload.
