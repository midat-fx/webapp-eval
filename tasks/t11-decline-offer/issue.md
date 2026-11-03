# Let clients turn down a waitlist offer

When a booking is cancelled, the first client on the waitlist for that day gets
an SMS with a link (`/w/<token>`), and the time is held for them for 15
minutes. The offer page only has "Claim this slot". A client who can't come
has no way to say so, so the time sits on hold for a quarter of an hour while
the next person in the queue hears nothing. Our receptionists end up calling
people.

Please add a **No thanks** button to the offer page.

Expected:

- After "No thanks" the link is dead: it can't claim the slot any more.
- The time goes to the next client in the queue straight away, by the same SMS
  an expired offer would trigger. The client who declined is not offered that
  time again.
- If nobody else is waiting, the time is back on the public booking page
  immediately, not 15 minutes later.
- A double tap, or the same link open in two tabs, declines once: the next
  client gets exactly one offer and nobody else is offered the same time. We
  run two app servers and two outbox workers (`pnpm worker`), so this has to
  hold across processes.
- "No thanks" on an offer that has already been claimed does nothing: the
  booking stays, and nobody else is offered the time.
