import { randomBytes } from "node:crypto";
import { expect, test } from "@playwright/test";
import { almaty, apiBook, biz, q, redis, resetRateLimits, serviceId, staffId, upcoming } from "../lib/kz";

const SERVERS = ["http://localhost:3000", "http://localhost:3001"];
const HOUR = 3600_000;

/**
 * Hold `starts` for one master directly in Redis — each racer gets its own
 * valid hold, exactly the state two app servers reach when both believe the
 * master is free — then fire every checkout at once across both servers.
 */
async function race(request: any, master: string, starts: number[], minutes: number, tag: string) {
  const st = await staffId(master);
  const svc = await serviceId(minutes === 45 ? "Men's haircut" : "Women's haircut");
  const racers = await Promise.all(
    starts.map(async (startMs) => {
      const token = randomBytes(16).toString("hex");
      const endMs = startMs + minutes * 60_000;
      await redis().set(`hold:${st}:${startMs}`, JSON.stringify({ token, endMs }), "EX", 300);
      return { startMs, endMs, token };
    }),
  );
  await resetRateLimits();
  return Promise.all(
    racers.map((r, i) =>
      apiBook(
        request,
        {
          serviceId: svc, staffId: st, startMs: r.startMs, endMs: r.endMs, holdToken: r.token,
          name: `Racer ${tag}-${i}`, phone: `+7702${tag.padStart(4, "0")}${String(i).padStart(3, "0")}`,
        },
        SERVERS[i % SERVERS.length],
      ),
    ),
  );
}

async function confirmedIn(master: string, fromMs: number, toMs: number): Promise<number> {
  const [r] = await q<{ n: string }>(
    `SELECT count(*) AS n FROM bookings WHERE staff_id = $1 AND status = 'confirmed'
     AND start_at < $3 AND end_at > $2`,
    [await staffId(master), new Date(fromMs), new Date(toMs)],
  );
  return Number(r.n);
}

test("exactly one of six overlapping checkouts wins, every round", async ({ request }) => {
  const b = await biz();
  for (let round = 0; round < 8; round++) {
    const date = upcoming(b.timezone, 2 + (round % 6), 8 + 7 * Math.floor(round / 6));
    const hour = 11 + round; // a fresh, empty part of the day every round
    const base = almaty(date, `${String(hour).padStart(2, "0")}:00`);
    // 60-minute slots starting 0..50 minutes apart: every pair overlaps.
    const starts = [0, 10, 20, 30, 40, 50].map((m) => base + m * 60_000);
    const results = await race(request, "Dana", starts, 60, `${round}`);
    const codes = results.map((r) => r.status);
    expect(codes.filter((c) => c !== 200 && c !== 409), `round ${round}: only 200/409, got ${codes}`).toEqual([]);
    for (const r of results.filter((x) => x.status === 409)) expect(r.body.error).toBe("slot_taken");
    expect(await confirmedIn("Dana", base, base + 2 * HOUR), `round ${round}: confirmed bookings, codes ${codes}`).toBe(1);
    expect(codes.filter((c) => c === 200), `round ${round}`).toHaveLength(1);
  }
});

test("different start, different duration still collide", async ({ request }) => {
  const b = await biz();
  const date = upcoming(b.timezone, 6, 22);
  const at = (hhmm: string) => almaty(date, hhmm);
  const sixty = await race(request, "Madina", [at("14:00")], 60, "9001");
  expect(sixty[0].status).toBe(200);
  const later = await race(request, "Madina", [at("14:15")], 45, "9002");
  expect(later[0].status, JSON.stringify(later[0].body)).toBe(409);
  expect(later[0].body.error).toBe("slot_taken");
});

test("other masters and cancelled bookings don't block", async ({ request }) => {
  const b = await biz();
  const date = upcoming(b.timezone, 7, 22);
  const at = almaty(date, "15:00");
  const dana = await race(request, "Dana", [at], 60, "9101");
  const madina = await race(request, "Madina", [at], 60, "9102");
  expect([dana[0].status, madina[0].status]).toEqual([200, 200]);
  await q("UPDATE bookings SET status = 'cancelled' WHERE id = $1", [dana[0].body.bookingId]);
  const again = await race(request, "Dana", [at + 15 * 60_000], 60, "9103");
  expect(again[0].status, JSON.stringify(again[0].body)).toBe(200);
});
