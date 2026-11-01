// Runs the `-- invariant: <name>` blocks of an .sql file. Each block is a
// query that returns the offending rows; an empty result means it holds.
import { readFileSync } from "node:fs";
import pg from "pg";

const blocks = readFileSync(process.argv[2], "utf8")
  .split(/^-- invariant:\s*/m)
  .slice(1)
  .map((b) => {
    const nl = b.indexOf("\n");
    return { name: b.slice(0, nl).trim(), sql: b.slice(nl + 1).trim() };
  });

const client = new pg.Client({ connectionString: process.env.DATABASE_URL });
await client.connect();
const results = [];
for (const { name, sql } of blocks) {
  try {
    const { rows } = await client.query(sql);
    results.push({ name, pass: rows.length === 0, detail: rows.length ? JSON.stringify(rows.slice(0, 5)) : undefined });
  } catch (e) {
    results.push({ name, pass: false, detail: `query error: ${e.message}` });
  }
}
await client.end();
console.log(JSON.stringify(results));
