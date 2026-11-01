# Booking page sometimes shows the times for the wrong day

Reported by a customer on a slow mobile connection, reproduced in devtools with
network throttling:

1. Open the booking page, pick a service and a staff member.
2. Pick a date, and while "Loading…" is still showing, pick a different date.
3. The grid first shows the right times for the second date, then a moment
   later silently switches to the times of the **first** date. The date picker
   still shows the second date.

Picking one of those times then holds and books a slot on the day the customer
did *not* choose. The same happens when switching staff member while times are
loading.

Expected: the grid always shows the times for the service, staff member and
date currently selected, no matter in which order responses arrive. Changing
the selection while times are loading must keep working — people do it all the
time on slow connections.
