# Accessibility: the public booking page fails our audit

A customer who uses a screen reader couldn't book, and an automated audit
(axe, WCAG 2 A/AA) of `/<business>` agrees something is off. Please fix the
booking wizard in every state (service list, staff list, date and times, the
"fully booked → join the waitlist" box, "Your details", errors):

1. **Every form field needs a real label.** The date picker has none at all;
   name and phone rely on placeholders, which disappear as soon as you type.
2. **Contrast.** The grey service durations ("· 60 min") and "Loading…" are too
   light to read. Keep the information, make it readable.
3. **Errors must be announced.** "That time was just taken", "Check the name
   and phone…" and the waitlist error appear silently; a screen reader says
   nothing.
4. **Selection must be perceivable.** The chosen service and staff member are
   only shown by colour. Assistive tech must be able to tell which one is
   selected.

The audit must come back with no violations, and nothing a sighted user sees
today may disappear.
