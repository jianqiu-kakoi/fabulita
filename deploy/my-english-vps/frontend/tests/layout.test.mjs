import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const styles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("the authenticated learner iframe fills a definite viewport-height grid row", () => {
  assert.match(
    styles,
    /\.learning-app\s*\{[^}]*height:\s*100vh;[^}]*height:\s*100dvh;[^}]*min-height:\s*0;[^}]*grid-template-rows:\s*auto auto minmax\(0,\s*1fr\);/s,
  );
  assert.match(
    styles,
    /\.learner-shell\s*\{[^}]*position:\s*relative;[^}]*min-height:\s*0;[^}]*overflow:\s*hidden;/s,
  );
  assert.match(
    styles,
    /\.learner-frame\s*\{[^}]*position:\s*absolute;[^}]*inset:\s*0;[^}]*height:\s*100%;/s,
  );
});
