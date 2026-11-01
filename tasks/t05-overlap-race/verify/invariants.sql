-- invariant: no_overlapping_confirmed_bookings
SELECT a.id AS a, b.id AS b, a.start_at, b.start_at FROM bookings a
JOIN bookings b ON a.staff_id = b.staff_id AND a.id < b.id
WHERE a.status = 'confirmed' AND b.status = 'confirmed'
  AND tstzrange(a.start_at, a.end_at) && tstzrange(b.start_at, b.end_at);

-- invariant: every_winner_has_its_outbox_message
SELECT b.id FROM bookings b JOIN clients c ON c.id = b.client_id
WHERE c.name LIKE 'Racer %'
  AND NOT EXISTS (SELECT 1 FROM outbox o WHERE o.dedupe_key = 'booking.confirmed:' || b.id);

-- invariant: losers_left_no_booking_rows
SELECT c.name, count(b.id) FROM clients c LEFT JOIN bookings b ON b.client_id = c.id
WHERE c.name LIKE 'Racer %' GROUP BY c.name HAVING count(b.id) > 1;
