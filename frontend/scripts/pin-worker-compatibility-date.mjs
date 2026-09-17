// Nitro stamps the generated Worker config with the build machine's current
// date. That makes the artifact non-reproducible and, once the date runs ahead
// of the wrangler runtime pinned in the frontend image, the Worker refuses to
// start with:
//
//   This Worker requires compatibility date "<today>", but the newest date
//   supported by this server binary is "<older>".
//
// Cloudflare's own guidance is that a compatibility date should be pinned
// deliberately, not floated, so this postbuild step rewrites it to the date
// the shipped wrangler version actually supports.
import { readFile, writeFile } from "node:fs/promises";

const WRANGLER_CONFIG = new URL("../.output/server/wrangler.json", import.meta.url);

// Must not exceed the wrangler version installed in frontend/Dockerfile.
const PINNED_COMPATIBILITY_DATE = "2026-08-22";

const raw = await readFile(WRANGLER_CONFIG, "utf8");
const config = JSON.parse(raw);

if (config.compatibility_date !== PINNED_COMPATIBILITY_DATE) {
  const previous = config.compatibility_date;
  config.compatibility_date = PINNED_COMPATIBILITY_DATE;
  await writeFile(WRANGLER_CONFIG, `${JSON.stringify(config, null, 2)}\n`, "utf8");
  console.log(
    `pinned worker compatibility_date ${previous} -> ${PINNED_COMPATIBILITY_DATE}`,
  );
} else {
  console.log(`worker compatibility_date already pinned to ${PINNED_COMPATIBILITY_DATE}`);
}
