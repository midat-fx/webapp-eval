-- invariant: at_most_one_status_change_per_booking
SELECT entity_id, array_agg(action) FROM audit_log
WHERE action IN ('booking.completed', 'booking.cancelled', 'booking.no_show')
GROUP BY entity_id HAVING count(*) > 1;

-- invariant: audit_matches_final_status
SELECT b.id, b.status, a.action FROM bookings b JOIN audit_log a ON a.entity_id = b.id
WHERE a.action IN ('booking.completed', 'booking.cancelled', 'booking.no_show')
  AND a.action <> 'booking.' || b.status;

-- invariant: waitlist_offers_only_for_cancelled
SELECT b.id, b.status FROM outbox o JOIN bookings b ON o.dedupe_key = 'waitlist.freed:' || b.id
WHERE b.status <> 'cancelled';

-- invariant: cancellation_messages_only_for_cancelled
SELECT b.id, b.status FROM outbox o JOIN bookings b ON o.dedupe_key = 'booking.cancelled:' || b.id
WHERE b.status <> 'cancelled';
