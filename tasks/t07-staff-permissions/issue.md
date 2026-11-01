# Staff logins can do everything the owner can

We gave our masters their own logins (role `staff`) so they can see the day
and mark visits done. One of them then "fixed" the price of her own service.
Looking closer, a staff login can open every admin page and use every button:
change prices, hide services, hide colleagues, reassign who performs what, add
new staff, and read revenue reports.

Expected:

- **Staff** may use the **Calendar** (view any day, mark bookings completed /
  no-show / cancelled) and see **Clients**. That's all.
- **Services, Staff, Reports, Analytics, Notifications and Audit** are for the
  owner only. A staff member who opens one of those URLs is sent back to the
  calendar (or gets a 403/404) and sees none of the page.
- The protection must hold on the server. Staff are technical enough to replay
  a form submission from devtools; every owner-only change must be refused for
  them no matter how it's sent.
- Staff shouldn't see links to pages they can't use.
- Nothing changes for the owner.
