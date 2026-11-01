# Booking page shows the wrong hours on the day the clocks change

We are testing kezek for our Berlin branch (business timezone
`Europe/Berlin`, open 10:00–20:00 on Sundays). On **Sunday 28 March 2027**,
when summer time starts, the booking page offers a first slot at **11:00**
instead of 10:00, and the grid runs past closing time. On **Sunday 31 October
2027**, when winter time starts, it offers **09:00**, an hour before we open.
Every other day looks right. A colleague with a New York test business sees the
same on the US clock-change days.

Expected: on every day, in every timezone, the slots follow the business's
local opening hours exactly — first slot at opening time, last slot ending by
closing time — including the days the clocks change, in any year.
