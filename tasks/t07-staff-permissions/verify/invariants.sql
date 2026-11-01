-- invariant: staff_did_not_change_prices
SELECT name, price_kzt FROM services WHERE name IN ('Women''s haircut', 'Men''s haircut', 'Manicure')
  AND price_kzt <> CASE name WHEN 'Women''s haircut' THEN 8000 WHEN 'Men''s haircut' THEN 5000 ELSE 12000 END;

-- invariant: staff_did_not_hide_anything
SELECT 'service' AS kind, name FROM services WHERE NOT is_active
UNION ALL SELECT 'staff', name FROM staff WHERE NOT is_active;

-- invariant: no_staff_rows_created_by_staff
SELECT id, name FROM staff WHERE name = 'Intruder';

-- invariant: no_owner_audit_entries_by_staff
SELECT a.action FROM audit_log a JOIN users u ON u.id = a.actor_user_id
WHERE u.role = 'staff' AND a.action NOT LIKE 'booking.%';

-- invariant: owner_changes_went_through
SELECT name, price_kzt FROM services
WHERE (name = 'Blow-dry' AND price_kzt <> 6500) OR (name = 'Hair coloring' AND price_kzt <> 26000);
