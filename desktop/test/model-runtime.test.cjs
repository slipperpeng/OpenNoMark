const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { OFFLINE_MANIFEST, resolveModelRuntime } = require("../model-runtime.cjs");

test("source and standard builds use the writable user model cache", () => {
  const runtime = resolveModelRuntime({
    isPackaged: false,
    resourcesPath: "/read-only/resources",
    userData: "/writable/user-data",
  });

  assert.equal(runtime.bundled, false);
  assert.equal(runtime.modelsDir, path.join("/writable/user-data", "models"));
  assert.equal(runtime.environment.HF_HUB_OFFLINE, undefined);
});

test("offline builds use bundled models and disable network model access", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "opennomark-model-runtime-"));
  try {
    const resourcesPath = path.join(root, "resources");
    const modelsDir = path.join(resourcesPath, "models");
    fs.mkdirSync(modelsDir, { recursive: true });
    fs.writeFileSync(path.join(modelsDir, OFFLINE_MANIFEST), "{}\n");

    const runtime = resolveModelRuntime({
      isPackaged: true,
      resourcesPath,
      userData: path.join(root, "user-data"),
    });

    assert.equal(runtime.bundled, true);
    assert.equal(runtime.modelsDir, modelsDir);
    assert.equal(runtime.environment.OPENNOMARK_OFFLINE_MODE, "1");
    assert.equal(runtime.environment.HF_HUB_OFFLINE, "1");
    assert.equal(runtime.environment.TRANSFORMERS_OFFLINE, "1");
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
