-- invariant: no_booking_on_the_abandoned_day
SELECT b.id, b.start_at FROM bookings b JOIN clients c ON c.id = b.client_id
WHERE c.name = 'Stale Check' AND (b.start_at AT TIME ZONE 'Asia/Almaty')::time <> '14:00';

-- invariant: both_checks_booked
SELECT count(*) FROM bookings b JOIN clients c ON c.id = b.client_id
WHERE c.name = 'Stale Check' HAVING count(*) <> 2;
