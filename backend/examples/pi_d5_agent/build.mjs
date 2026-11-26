import { mkdir, writeFile } from 'node:fs/promises';
import { isBuiltin } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const core = dirname(fileURLToPath(import.meta.resolve('@earendil-works/pi-agent-core')));
const ai = dirname(fileURLToPath(import.meta.resolve('@earendil-works/pi-ai')));

const { metafile, outputFiles } = await build({
  absWorkingDir: dirname(fileURLToPath(import.meta.url)),
  entryPoints: ['worker.mjs', 'workspace-worker.mjs'],
  outdir: 'dist',
  outExtension: { '.js': '.mjs' },
  bundle: true,
  format: 'esm',
  platform: 'node',
  target: 'node22.19',
  write: false,
  metafile: true,
  plugins: [{
    name: 'pi-broker-only',
    setup(builder) {
      // Pi 0.75.5's public barrel loads provider and harness modules. Bundle
      // the pinned package's actual loop, event stream and validator directly.
      builder.onResolve({ filter: /^@earendil-works\/pi-agent-core$/ }, () => ({
        path: join(core, 'agent-loop.js'),
      }));
      builder.onResolve({ filter: /^@earendil-works\/pi-ai$/ }, () => ({
        path: 'stream-and-validation', namespace: 'pi-broker-only',
      }));
      builder.onLoad({ filter: /.*/, namespace: 'pi-broker-only' }, () => ({
        resolveDir: ai,
        contents: [
          "export * from './utils/event-stream.js';",
          "export { validateToolArguments } from './utils/validation.js';",
          "export function streamSimple() { throw new Error('Broker stream required'); }",
        ].join('\n'),
      }));
    },
  }],
});

if (Object.keys(metafile.inputs).some(path => path.includes('/pi-ai/dist/providers/'))
    || Object.values(metafile.outputs).some(output => output.imports.some(entry => !isBuiltin(entry.path)))) {
  throw new Error('Worker must bundle Pi without provider code or runtime dependencies');
}

await mkdir(dirname(outputFiles[0].path), { recursive: true });
await Promise.all(outputFiles.map(artifact => writeFile(artifact.path, artifact.contents)));
