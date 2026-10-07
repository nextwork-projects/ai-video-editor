// Bundles the preview page. preview.py copies this folder's app.tsx, Sfx.tsx and this file into
// ~/.ai-video-editor/remotion/preview/ and runs it there, so it uses the renderer's own node_modules
// and the same src/ the render does. Output: dist/app.js.
import * as esbuild from "esbuild";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
await esbuild.build({
  entryPoints: [path.join(here, "app.tsx")],
  outfile: path.join(here, "dist", "app.js"),
  bundle: true,
  format: "esm",
  target: "es2020",
  jsx: "automatic",
  minify: true,
  define: { "process.env.NODE_ENV": '"production"' },
  logLevel: "warning",
  plugins: [{
    name: "preview-sfx",
    setup(b) {
      // src/StyleEdit.tsx's "./Sfx" -> ./Sfx.tsx here (see that file)
      b.onResolve({ filter: /^\.\/Sfx$/ }, (a) =>
        path.basename(a.resolveDir) === "src" ? { path: path.join(here, "Sfx.tsx") } : undefined);
    },
  }],
});
