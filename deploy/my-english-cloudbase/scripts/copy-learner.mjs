import { copyFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const project = path.resolve(here, "..");
const repository = path.resolve(project, "../..");
const publicDir = path.join(project, "public");

await mkdir(publicDir, { recursive: true });
await copyFile(
  path.join(repository, "docs", "my-english.html"),
  path.join(publicDir, "my-english.html"),
);
await copyFile(
  path.join(repository, "docs", "my-english-og.png"),
  path.join(publicDir, "og.png"),
);
