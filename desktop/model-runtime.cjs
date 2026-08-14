const fs = require("node:fs");
const path = require("node:path");

const OFFLINE_MANIFEST = "offline-models.json";

function resolveModelRuntime({ isPackaged, resourcesPath, userData }) {
  const bundledModelsDir = path.join(resourcesPath, "models");
  const bundled = Boolean(
    isPackaged
    && fs.existsSync(path.join(bundledModelsDir, OFFLINE_MANIFEST)),
  );
  const modelsDir = bundled ? bundledModelsDir : path.join(userData, "models");
  const environment = {
    OPENNOMARK_MODEL_DIR: modelsDir,
    HF_HOME: path.join(modelsDir, "huggingface"),
    HF_HUB_CACHE: path.join(modelsDir, "huggingface", "hub"),
    TORCH_HOME: path.join(modelsDir, "torch"),
    HF_HUB_DISABLE_TELEMETRY: "1",
  };

  if (bundled) {
    Object.assign(environment, {
      OPENNOMARK_OFFLINE_MODE: "1",
      HF_HUB_OFFLINE: "1",
      HF_DATASETS_OFFLINE: "1",
      TRANSFORMERS_OFFLINE: "1",
      HF_HUB_DISABLE_XET: "1",
    });
  }

  return { bundled, modelsDir, environment };
}

module.exports = { OFFLINE_MANIFEST, resolveModelRuntime };
