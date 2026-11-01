# Booking page opens on yesterday's date early in the morning

Our salon is in Almaty. Customers who open the booking page between midnight
and 5 a.m. see **yesterday** pre-selected in the date picker, and yesterday is
even allowed as the earliest date. They get "This day is fully booked. Join the
waitlist" for a day that is already over. A customer travelling in Europe saw
the same thing in the evening.

Expected: the date picker opens on *today as it is where the business is*
(the business's configured timezone), and that is also the earliest date it
allows — regardless of the visitor's own timezone or what the date is in UTC.
This has to hold for any business timezone, not just Almaty.
