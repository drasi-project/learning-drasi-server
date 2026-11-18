// Copyright 2026 The Drasi Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');

const source = fs.readFileSync(
  path.join(__dirname, '../tutorials/getting-started/scripts/download.sh'), 'utf8',
);

async function download(t, responseStatus) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tutorial-download-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const requests = { server: 0, sse: 0 };
  const binary = '#!/bin/sh\necho "fixture version"\n';
  const server = http.createServer((req, res) => {
    const asset = req.url.includes('drasi-sse-cli') ? 'sse' : 'server';
    const status = responseStatus(asset, ++requests[asset]);
    res.writeHead(status);
    res.end(status === 200 ? binary : 'download failed');
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const script = source.replace(
    'https://github.com/drasi-project/drasi-server/releases/latest/download',
    `http://127.0.0.1:${server.address().port}`,
  );
  assert.notEqual(script, source, 'Redirect fixture downloads to the local HTTP server');
  const child = spawn('bash', ['-c', script], {
    cwd: dir,
    env: { ...process.env, NO_PROXY: '127.0.0.1', no_proxy: '127.0.0.1' },
  });
  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (data) => { stdout += data; });
  child.stderr.on('data', (data) => { stderr += data; });
  const [code] = await once(child, 'close');
  return { code, stdout, stderr, requests, dir, binary };
}

test('both binary downloads recover from a transient HTTP 500 and are verified', async (t) => {
  const result = await download(t, (_asset, attempt) => attempt === 1 ? 500 : 200);
  assert.equal(result.code, 0, result.stderr);
  assert.deepEqual(result.requests, { server: 2, sse: 2 });
  assert.equal(fs.readFileSync(path.join(result.dir, 'bin/drasi-server'), 'utf8'), result.binary);
  assert.equal(fs.readFileSync(path.join(result.dir, 'bin/drasi-sse-cli'), 'utf8'), result.binary);
  assert.equal(result.stdout.match(/fixture version/g).length, 2);
});

test('persistent HTTP 500 stops after three retries and surfaces the failure', async (t) => {
  const result = await download(t, () => 500);
  assert.equal(result.code, 22);
  assert.deepEqual(result.requests, { server: 4, sse: 0 });
  assert.match(result.stderr, /500/);
  assert.doesNotMatch(result.stdout, /Verifying installations|installed to/);
});

test('a permanent HTTP 404 is not retried or reported as a successful install', async (t) => {
  const result = await download(t, (asset) => asset === 'server' ? 200 : 404);
  assert.equal(result.code, 22);
  assert.deepEqual(result.requests, { server: 1, sse: 1 });
  assert.match(result.stderr, /404/);
  assert.doesNotMatch(result.stdout, /Verifying installations|installed to/);
});
