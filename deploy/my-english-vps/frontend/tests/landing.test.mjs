import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const html = readFileSync(
  new URL("../index.html", import.meta.url),
  "utf8",
);
const source = readFileSync(
  new URL("../src/main.js", import.meta.url),
  "utf8",
);
const prepareSource = readFileSync(
  new URL("../scripts/copy-learner.mjs", import.meta.url),
  "utf8",
);

test("signed-out markup is a focused two-entry landing page", () => {
  assert.match(html, /\bid="guest-landing"/);
  assert.match(html, />\s*使用邀请码注册\s*</);
  assert.match(html, />\s*已有账号登录\s*</);
  assert.match(html, /src="\/hotel-checkin-preview\.png"/);
  assert.match(
    prepareSource,
    /my-english-hotel-checkin-concept-v0\.png/,
    "the build should copy the checked-in concept image into public assets",
  );
  assert.equal(
    (html.match(/\bclass="landing-button\b/g) || []).length,
    2,
    "the landing page should expose exactly two primary account actions",
  );
  assert.doesNotMatch(html, /<iframe\b/i);
  assert.doesNotMatch(html, /\b65 words\b/i);
  assert.doesNotMatch(html, /\bDaily review\b/i);
});

test("learning content is created only inside the authenticated path", () => {
  assert.match(source, /document\.createElement\("iframe"\)/);
  assert.match(
    source,
    /if \(!currentUser \|\| !target \|\| target === "guest"\)/,
  );
  assert.match(
    source,
    /async function activateUser\(user\)[\s\S]*await switchLearningProfile\(profile\)/,
  );
  assert.doesNotMatch(source, /switchLearningProfile\("guest"\)/);
  assert.doesNotMatch(source, /querySelector\("#learner-frame"\)/);
});
