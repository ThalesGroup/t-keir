#!/usr/bin/env node
/**
 * React 19 ships package.json "exports" without a "types" condition.
 * TypeScript (especially IDE language services with moduleResolution=bundler)
 * then fails with: Cannot find module 'react' or its corresponding type declarations.
 *
 * Wire exports to the installed @types/react / @types/react-dom packages.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");

function patch(pkgName, mapping) {
  const pkgPath = path.join(root, "node_modules", pkgName, "package.json");
  if (!fs.existsSync(pkgPath)) {
    console.warn(`patch-react-types: skip missing ${pkgName}`);
    return;
  }
  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
  const exportsField = pkg.exports;
  if (!exportsField || typeof exportsField !== "object") {
    console.warn(`patch-react-types: ${pkgName} has no exports`);
    return;
  }

  let changed = false;
  for (const [subpath, typesRel] of Object.entries(mapping)) {
    const typesPath = path.join(root, "node_modules", pkgName, typesRel);
    if (!fs.existsSync(path.resolve(path.dirname(pkgPath), typesRel))) {
      // resolve relative to package dir
      const abs = path.resolve(path.dirname(pkgPath), typesRel);
      if (!fs.existsSync(abs)) {
        console.warn(`patch-react-types: missing types ${abs}`);
        continue;
      }
    }
    const current = exportsField[subpath];
    if (!current) continue;
    if (typeof current === "string") {
      exportsField[subpath] = { types: typesRel, default: current };
      changed = true;
      continue;
    }
    if (typeof current === "object" && current.types !== typesRel) {
      exportsField[subpath] = { types: typesRel, ...current };
      changed = true;
    }
  }

  if (pkg.types !== mapping["."] && mapping["."]) {
    pkg.types = mapping["."];
    changed = true;
  }

  if (changed) {
    fs.writeFileSync(pkgPath, `${JSON.stringify(pkg, null, 2)}\n`, "utf8");
    console.log(`patch-react-types: patched ${pkgName}`);
  } else {
    console.log(`patch-react-types: ${pkgName} already patched`);
  }
}

patch("react", {
  ".": "../@types/react/index.d.ts",
  "./jsx-runtime": "../@types/react/jsx-runtime.d.ts",
  "./jsx-dev-runtime": "../@types/react/jsx-dev-runtime.d.ts",
  "./compiler-runtime": "../@types/react/compiler-runtime.d.ts",
});

patch("react-dom", {
  ".": "../@types/react-dom/index.d.ts",
  "./client": "../@types/react-dom/client.d.ts",
  "./server": "../@types/react-dom/server.d.ts",
});
