-- invariant: one_live_offer_per_slot
SELECT offer_staff_id, offer_slot_start_at, count(*) FROM waitlist_entries
WHERE status = 'offered' GROUP BY 1, 2 HAVING count(*) > 1;

-- invariant: no_offer_for_a_booked_time
SELECT w.id FROM waitlist_entries w JOIN bookings b
  ON b.staff_id = w.offer_staff_id AND b.status = 'confirmed'
 AND tstzrange(b.start_at, b.end_at) && tstzrange(w.offer_slot_start_at, w.offer_slot_end_at)
WHERE w.status = 'offered';
