import { createHash } from "node:crypto";
import type { JsonValue } from "./contracts";

export function stableStringify(value: JsonValue): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  const fields = Object.keys(value).sort();
  return `{${fields
    .map(
      (field) =>
        `${JSON.stringify(field)}:${stableStringify(value[field] as JsonValue)}`,
    )
    .join(",")}}`;
}

export function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

export function ownerKeyFromUid(uid: string): string {
  return `u_${sha256(`vps:${uid}`)}`;
}
