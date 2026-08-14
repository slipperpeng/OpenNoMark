const standardBuild = require("./package.json").build;

module.exports = {
  ...standardBuild,
  appId: "io.github.slipperpeng.opennomark.offline",
  productName: "OpenNoMark Offline",
  extraResources: [
    ...standardBuild.extraResources,
    {
      from: "bundled-models",
      to: "models",
    },
    {
      from: "../docs/third-party-models.md",
      to: "THIRD_PARTY_MODELS.md",
    },
  ],
  artifactName: "OpenNoMark-Offline-${version}-${os}-${arch}.${ext}",
};
