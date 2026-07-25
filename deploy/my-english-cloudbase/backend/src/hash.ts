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
  return `u_${sha256(`cloudbase:${uid}`)}`;
}

export function eventDocumentId(ownerKey: string, eventId: string): string {
  return `e_${sha256(`${ownerKey}\u0000${eventId}`)}`;
}

export function checkpointDocumentId(
  ownerKey: string,
  scope: string,
): string {
  return `c_${sha256(`${ownerKey}\u0000${scope}`)}`;
}

export function rateLimitDocumentId(ownerKey: string): string {
  return `r_${sha256(ownerKey)}`;
}
