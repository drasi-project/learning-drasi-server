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
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const scheduled = fs.readFileSync(path.join(root, '.github/workflows/tutorial-evaluation-scheduled.yml'), 'utf8');
const manual = fs.readFileSync(path.join(root, '.github/workflows/tutorial-evaluation.yml'), 'utf8');

function blocks(source, key) {
  const lines = source.split('\n');
  const result = [];
  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(new RegExp(`^( +)${key}: \\|$`));
    if (!match) continue;
    const indent = match[1].length + 2;
    const body = [];
    while (i + 1 < lines.length && (!lines[i + 1].trim() || lines[i + 1].startsWith(' '.repeat(indent)))) {
      body.push(lines[++i].slice(indent));
    }
    result.push(body.join('\n'));
  }
  return result;
}

for (const [name, command, expectedModel] of [
  ...blocks(scheduled, 'runCmd').map((command, i) => [`scheduled attempt ${i + 1}`, command, i < 2]),
  ['manual evaluation', blocks(manual, 'runCmd')[0], true],
]) {
  test(`${name} passes the selected model literally or uses the default`, (t) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tutorial-model-test-'));
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
    fs.mkdirSync(path.join(dir, 'bin'));
    fs.mkdirSync(path.join(dir, 'evaluation-test'));
    fs.writeFileSync(path.join(dir, 'prompt.md'), 'Evaluate the tutorial.');
    fs.writeFileSync(path.join(dir, 'evaluation-test/report.md'), '## STATUS: SUCCESS\n');
    fs.writeFileSync(path.join(dir, 'bin/copilot'), `#!${process.execPath}
require('node:fs').writeFileSync('arguments.json', JSON.stringify(process.argv.slice(2)));
`);
    fs.writeFileSync(path.join(dir, 'bin/timeout'), `#!${process.execPath}
require('node:fs').writeFileSync('timeout.json', JSON.stringify(process.argv.slice(2)));
const result = require('node:child_process').spawnSync(process.argv[3], process.argv.slice(4), { stdio: 'inherit' });
process.exit(result.status ?? 1);
`);
    for (const executable of ['copilot', 'timeout']) {
      fs.chmodSync(path.join(dir, 'bin', executable), 0o755);
    }
    const model = 'test-model; $(touch injected)';
    const result = spawnSync('bash', ['-e', '-c', command], {
      cwd: dir,
      env: { ...process.env, PATH: `${path.join(dir, 'bin')}:${process.env.PATH}`, TUTORIAL_EVALUATION_MODEL: model },
      encoding: 'utf8',
    });
    assert.equal(result.status, 0, result.stderr);
    const args = JSON.parse(fs.readFileSync(path.join(dir, 'arguments.json'), 'utf8'));
    const index = args.indexOf('--model');
    if (expectedModel) {
      assert.notEqual(index, -1);
      assert.equal(args[index + 1], model);
    } else {
      assert.equal(index, -1);
    }
    assert.equal(fs.existsSync(path.join(dir, 'injected')), false);
    assert.equal(JSON.parse(fs.readFileSync(path.join(dir, 'timeout.json'), 'utf8'))[0], '1200');
    assert.ok(args.includes('--allow-all-tools'));
    assert.ok(args.includes('shell(ssh *)'));
    assert.ok(args.includes('shell(dd *)'));
  });
}

for (const [recovered, status, expectedExit] of [
  [true, 'SUCCESS', 0],
  [false, 'SUCCESS', 0],
  [true, 'FAILURE', 1],
]) {
  test(`report ${status} with default recovery=${recovered} preserves status and warns only on recovery`, (t) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tutorial-report-test-'));
    t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
    const report = path.join(dir, 'report.md');
    const summary = path.join(dir, 'summary.md');
    fs.writeFileSync(report, `## STATUS: ${status}\n`);
    fs.writeFileSync(summary, '');
    const check = blocks(scheduled, 'run').find((body) => body.includes('Found report:'));
    const result = spawnSync('bash', ['-e', '-c', check.slice(check.indexOf('if grep -qiE'))], {
      env: {
        ...process.env,
        REPORT: report,
        GITHUB_STEP_SUMMARY: summary,
        DEFAULT_MODEL_RECOVERY: String(recovered),
        TUTORIAL_EVALUATION_MODEL: 'configured-gpt-model',
      },
      encoding: 'utf8',
    });
    assert.equal(result.status, expectedExit, result.stderr);
    if (recovered && status === 'SUCCESS') {
      assert.match(result.stdout, /::warning::/);
      assert.match(fs.readFileSync(summary, 'utf8'), /default model/i);
    } else {
      assert.doesNotMatch(result.stdout, /::warning::/);
    }
  });
}

function evaluation(conclusion, third = 'skipped', tutorial = 'getting-started') {
  return {
    name: `evaluate (${tutorial}, .devcontainer/${tutorial}/devcontainer.json, tutorials/${tutorial})`,
    conclusion,
    steps: [
      { name: 'Run evaluation (attempt 1)', conclusion: 'success' },
      { name: 'Run evaluation (attempt 2)', conclusion: third === 'skipped' ? 'skipped' : 'success' },
      { name: 'Run evaluation (attempt 3)', conclusion: third },
      { name: 'Check evaluation status', conclusion },
      { name: 'Post Run evaluation (attempt 3)', conclusion: 'success' },
    ],
  };
}

async function report(jobs) {
  const issues = [];
  const script = blocks(scheduled, 'script')[0];
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  const run = new AsyncFunction('github', 'context', 'process', script);
  await run({
    rest: {
      actions: { listJobsForWorkflowRun: async () => ({ data: { jobs } }) },
      issues: { create: async (issue) => issues.push(issue) },
    },
  }, {
    serverUrl: 'https://github.com',
    repo: { owner: 'drasi-project', repo: 'learning-drasi-server' },
    runId: 123,
  }, { env: { TUTORIAL_EVALUATION_MODEL: 'configured-gpt-model' } });
  return issues;
}

test('ordinary first- or second-attempt success does not create an issue', async () => {
  const first = evaluation('success');
  const second = evaluation('success');
  second.steps[1].conclusion = 'success';
  assert.deepEqual(await report([first, second]), []);
});

test('successful third-attempt recovery creates a warning, not a failure issue', async () => {
  const issues = await report([evaluation('success', 'success')]);
  assert.equal(issues.length, 1);
  assert.match(issues[0].title, /warning/i);
  assert.doesNotMatch(issues[0].title, /failed/i);
  assert.deepEqual(issues[0].labels, ['automated']);
  assert.match(issues[0].body, /configured-gpt-model/);
  assert.match(issues[0].body, /default/i);
  assert.match(issues[0].body, /getting-started/);
  assert.match(issues[0].body, /https:\/\/github.com\/drasi-project\/learning-drasi-server\/actions\/runs\/123/);
  assert.doesNotMatch(issues[0].body, /UNKNOWN/);
});

test('third-attempt failure stays a failure issue with actual API conclusions', async () => {
  const issues = await report([evaluation('failure', 'failure')]);
  assert.equal(issues.length, 1);
  assert.match(issues[0].title, /failed/i);
  assert.ok(issues[0].labels.includes('tutorial-failure'));
  assert.match(issues[0].body, /Attempt 3.*FAILURE/);
  assert.doesNotMatch(issues[0].body, /UNKNOWN/);
});

test('failure before a third attempt is not reported as recovery', async () => {
  const job = evaluation('failure');
  job.steps = [];
  const issues = await report([job]);
  assert.equal(issues.length, 1);
  assert.match(issues[0].title, /failed/i);
});

test('canceled and skipped jobs do not create recovery warnings', async () => {
  assert.deepEqual(await report([evaluation('cancelled', 'success'), evaluation('skipped')]), []);
});

test('a failed final report check takes precedence over a successful third step', async () => {
  const issues = await report([evaluation('failure', 'success')]);
  assert.equal(issues.length, 1);
  assert.match(issues[0].title, /failed/i);
});

test('mixed results produce a failure issue that also records recovered tutorials', async () => {
  const issues = await report([
    evaluation('failure', 'failure', 'broken-tutorial'),
    evaluation('success', 'success', 'recovered-tutorial'),
  ]);
  assert.equal(issues.length, 1);
  assert.match(issues[0].title, /failed/i);
  assert.match(issues[0].body, /broken-tutorial/);
  assert.match(issues[0].body, /recovered-tutorial/);
});
