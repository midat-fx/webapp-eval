-- invariant: one_client_per_number
SELECT count(*) AS clients FROM clients
WHERE regexp_replace(phone, '[^0-9]', '', 'g') = '77015551234'
HAVING count(*) <> 1;

-- invariant: stored_in_canonical_form
SELECT id, phone FROM clients
WHERE regexp_replace(phone, '[^0-9]', '', 'g') = '77015551234' AND phone <> '+77015551234';

-- invariant: both_bookings_on_that_client
SELECT count(*) AS bookings FROM bookings b JOIN clients c ON c.id = b.client_id
WHERE c.phone = '+77015551234' AND b.status = 'confirmed'
HAVING count(*) <> 2;

-- invariant: waitlist_entry_on_that_client
SELECT count(*) AS entries FROM waitlist_entries w JOIN clients c ON c.id = w.client_id
WHERE c.phone = '+77015551234'
HAVING count(*) <> 1;

-- invariant: rejected_input_left_no_rows
SELECT id, name FROM clients WHERE name = 'Nope';
