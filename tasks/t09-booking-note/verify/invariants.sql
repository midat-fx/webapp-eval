-- invariant: notes_within_limit
SELECT id, length(note) FROM bookings WHERE length(note) > 500;

-- invariant: no_blank_notes
SELECT id FROM bookings WHERE note IS NOT NULL AND btrim(note, E' \n\t') = '';

-- invariant: rejected_note_created_nothing
SELECT b.id FROM bookings b JOIN clients c ON c.id = b.client_id WHERE c.phone = '+77013330003';
