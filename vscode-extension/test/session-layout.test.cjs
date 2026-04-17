const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const {
  assertWithinRoot,
  buildSessionWorkspacePaths,
  isWithinRoot,
  sanitizeSessionSegment,
} = require("../out/sessionLayout.js");

test("buildSessionWorkspacePaths keeps all session paths under sessions root", () => {
  const sessionsRoot = path.resolve("/tmp/workspace/sessions");
  const workspace = buildSessionWorkspacePaths(sessionsRoot, "Research Batch");
  assert.equal(workspace.sessionRoot, path.join(sessionsRoot, "Research Batch"));
  assert.equal(workspace.inputDir, path.join(sessionsRoot, "Research Batch", "data", "raw"));
  assert.equal(workspace.qualityDir, path.join(sessionsRoot, "Research Batch", "outputs", "quality"));
  assert.equal(workspace.manifestPath, path.join(sessionsRoot, "Research Batch", "outputs", ".manifest.json"));
});

test("sanitizeSessionSegment strips unsafe path characters", () => {
  assert.equal(sanitizeSessionSegment("../demo:batch"), "-demo-batch");
  assert.equal(sanitizeSessionSegment("   "), "default");
});

test("assertWithinRoot rejects path traversal outside the session root", () => {
  const root = path.resolve("/tmp/workspace/sessions/demo");
  const inside = path.join(root, "data", "raw", "paper");
  assert.equal(assertWithinRoot(root, inside, "inside"), inside);
  assert.equal(isWithinRoot(root, inside), true);
  assert.throws(() => assertWithinRoot(root, path.resolve(root, "..", "..", "escape"), "escape"), /escaped/);
});
