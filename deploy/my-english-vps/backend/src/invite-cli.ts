import { normalizeEmail } from "./auth";
import { openDatabase } from "./database";
import {
  createRegistrationInvites,
  revokeInviteBatch,
} from "./invites";

const USAGE = `Usage:
  node dist/invite-cli.js create [--count N] [--email EMAIL] [--days N] [--database PATH]
  node dist/invite-cli.js revoke --batch-id BATCH_ID [--database PATH]

DATABASE_PATH is used when --database is omitted.
New invite codes are printed once, one per stdout line.`;

function fail(message: string): never {
  throw new Error(`${message}\n\n${USAGE}`);
}

function parseOptions(
  values: string[],
): Map<string, string> {
  const options = new Map<string, string>();
  for (let index = 0; index < values.length; index += 2) {
    const name = values[index];
    const value = values[index + 1];
    if (!name?.startsWith("--") || value == null || value.startsWith("--")) {
      fail("Every option must use --name VALUE.");
    }
    if (options.has(name)) fail(`Duplicate option: ${name}`);
    options.set(name, value);
  }
  return options;
}

function integerOption(
  options: Map<string, string>,
  name: string,
): number | undefined {
  const raw = options.get(name);
  if (raw == null) return undefined;
  if (!/^\d+$/.test(raw)) fail(`${name} must be a positive integer.`);
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed < 1) {
    fail(`${name} must be a positive integer.`);
  }
  return parsed;
}

function assertOnly(
  options: Map<string, string>,
  allowed: ReadonlySet<string>,
): void {
  for (const name of options.keys()) {
    if (!allowed.has(name)) fail(`Unknown option: ${name}`);
  }
}

function databasePath(options: Map<string, string>): string {
  const value =
    options.get("--database")?.trim() ||
    process.env.DATABASE_PATH?.trim();
  if (!value) fail("--database or DATABASE_PATH is required.");
  return value;
}

function main(): void {
  const [command, ...rawOptions] = process.argv.slice(2);
  if (!command || command === "--help" || command === "-h") {
    process.stdout.write(`${USAGE}\n`);
    return;
  }
  const options = parseOptions(rawOptions);
  const path = databasePath(options);
  const database = openDatabase(path);
  try {
    if (command === "create") {
      assertOnly(
        options,
        new Set(["--count", "--email", "--days", "--database"]),
      );
      const rawEmail = options.get("--email");
      const emailNormalized =
        rawEmail == null ? null : normalizeEmail(rawEmail);
      const created = createRegistrationInvites(database, {
        count: integerOption(options, "--count"),
        emailNormalized,
        ttlDays: integerOption(options, "--days"),
      });
      const first = created[0];
      process.stderr.write(
        `Created ${created.length} invite(s); batch_id=${first.batchId}; ` +
          `expires_at=${new Date(first.expiresAt).toISOString()}; ` +
          `email=${first.emailNormalized || "*"}\n`,
      );
      for (const invite of created) {
        process.stdout.write(`${invite.code}\n`);
      }
      return;
    }

    if (command === "revoke") {
      assertOnly(
        options,
        new Set(["--batch-id", "--database"]),
      );
      const batchId = options.get("--batch-id");
      if (!batchId) fail("--batch-id is required for revoke.");
      const revoked = revokeInviteBatch(database, batchId);
      process.stdout.write(
        `Revoked ${revoked} unused invite(s) in batch ${batchId}.\n`,
      );
      return;
    }

    fail(`Unknown command: ${command}`);
  } finally {
    database.close();
  }
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    process.stderr.write(
      `${error instanceof Error ? error.message : String(error)}\n`,
    );
    process.exitCode = 1;
  }
}
