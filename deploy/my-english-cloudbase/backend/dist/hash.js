"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.stableStringify = stableStringify;
exports.sha256 = sha256;
exports.ownerKeyFromUid = ownerKeyFromUid;
exports.eventDocumentId = eventDocumentId;
exports.checkpointDocumentId = checkpointDocumentId;
exports.rateLimitDocumentId = rateLimitDocumentId;
const node_crypto_1 = require("node:crypto");
function stableStringify(value) {
    if (value === null || typeof value !== "object") {
        return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
        return `[${value.map(stableStringify).join(",")}]`;
    }
    const fields = Object.keys(value).sort();
    return `{${fields
        .map((field) => `${JSON.stringify(field)}:${stableStringify(value[field])}`)
        .join(",")}}`;
}
function sha256(value) {
    return (0, node_crypto_1.createHash)("sha256").update(value).digest("hex");
}
function ownerKeyFromUid(uid) {
    return `u_${sha256(`cloudbase:${uid}`)}`;
}
function eventDocumentId(ownerKey, eventId) {
    return `e_${sha256(`${ownerKey}\u0000${eventId}`)}`;
}
function checkpointDocumentId(ownerKey, scope) {
    return `c_${sha256(`${ownerKey}\u0000${scope}`)}`;
}
function rateLimitDocumentId(ownerKey) {
    return `r_${sha256(ownerKey)}`;
}
