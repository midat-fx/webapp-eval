# Two clients booked with Dana at overlapping times

From Saturday's calendar: Dana has *Women's haircut 14:00–15:00* and
*Men's haircut 14:15–15:00*, both confirmed, created within the same second by
two different clients. Both got a confirmation SMS. We run two app servers
behind the load balancer.

Holds are supposed to prevent this, but a hold only covers the exact start
time that was picked, and two checkouts that start at the same moment both
see the master as free.

Expected:

- A master can never end up with two overlapping **confirmed** bookings, no
  matter how many clients check out at once or which app server handles them.
  Cancelled / completed / no-show bookings don't block time.
- The client who loses the race gets the normal "That time is already taken"
  response (`409` with `{"error": "slot_taken"}`), never a 500.
- Booking different masters at the same time, and re-booking a time after a
  cancellation, keep working.
