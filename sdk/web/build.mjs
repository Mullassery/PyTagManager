import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const source = join(root, "src", "pytagmanager.js");
const destination = join(root, "dist", "pytagmanager.js");
const packageAsset = join(
  root,
  "..",
  "..",
  "python",
  "pytagmanager",
  "distribution",
  "assets",
  "pytagmanager.js",
);
mkdirSync(dirname(destination), { recursive: true });
copyFileSync(source, destination);
mkdirSync(dirname(packageAsset), { recursive: true });
copyFileSync(source, packageAsset);
const bytes = readFileSync(destination);
const digest = createHash("sha256").update(bytes).digest("hex");
writeFileSync(join(root, "dist", "pytagmanager.js.sha256"), `${digest}  pytagmanager.js\n`);
console.log(`built ${destination} (${bytes.length} bytes, sha256 ${digest})`);
