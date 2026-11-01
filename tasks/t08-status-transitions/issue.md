# Cancelled bookings can be "completed" later, and double clicks double-count

Two problems with the Completed / No-show / Cancel buttons on the admin
calendar, found while reconciling last month's revenue:

1. A booking that was **cancelled** later showed up as **completed** (and in
   revenue). The buttons are hidden for non-confirmed bookings, but a stale tab
   or a resubmitted form still goes through. Cancelling an already-finished
   booking is worse: it announces the slot as free again and offers it to the
   waitlist, although the visit already happened.
2. When two receptionists click at the same moment (one "Completed", one
   "No-show"), the audit log shows **both** changes and the booking ends up
   with whichever was written last.

Expected: only a **confirmed** booking can change status, and it changes
**exactly once**. Every later or competing attempt is a no-op — the status
stays, no second audit entry, no cancellation message, no waitlist offer —
even when the attempts arrive at the same moment on different app servers.
Normal use of the buttons keeps working.
