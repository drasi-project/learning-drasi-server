// Copyright 2026 The Drasi Authors. Licensed under the Apache License, Version 2.0.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

class Element {
  constructor() {
    this.children = [];
    this.textContent = '';
    this.className = '';
    this.handlers = {};
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  insertRow() {
    const row = new Element();
    this.children.push(row);
    return row;
  }
  insertCell() { return this.insertRow(); }
}

function viewer() {
  const nodes = Object.fromEntries(
    ['connect', 'api', 'status', 'queries', 'events'].map(id => [id, new Element()])
  );
  nodes.api.value = 'http://127.0.0.1:8180';
  const streams = [];
  const requests = [];
  const state = {failure: false};
  const context = {
    document: {
      getElementById: id => nodes[id],
      createElement: () => new Element(),
      createTextNode: value => ({textContent: value})
    },
    EventSource: class {
      constructor(url) { this.url = url; this.listeners = {}; streams.push(this); }
      addEventListener(name, handler) { this.listeners[name] = handler; }
      close() { this.closed = true; }
    },
    fetch: async url => {
      requests.push(url);
      return {
        ok: !state.failure,
        json: async () => state.failure
          ? {success: false, error: 'test failure'}
          : {success: true, data: [
            {id: '0a1b', name: 'message-counts', status: 'Running'},
            {id: '9f9f', name: 'someone-elses-query', status: 'Running'}
          ]}
      };
    }
  };
  const html = fs.readFileSync(path.join(__dirname, '../viewer/index.html'), 'utf8');
  vm.runInNewContext(html.split('<script>')[1].split('</script>')[0], context);
  return {nodes, streams, requests, state};
}

function rows(app) {
  const table = app.nodes.queries.children[0].children[1].children[0];
  return table.children.slice(1).map(row => row.children.map(cell => cell.textContent));
}

const snapshot = data => ({data: JSON.stringify(data)});

test('viewer attaches each tutorial query and applies changes to its snapshot', async () => {
  const app = viewer();
  await app.nodes.connect.handlers.submit({preventDefault() {}});
  assert.equal(app.streams.length, 1);
  const stream = app.streams[0];
  assert.equal(stream.url,
    'http://127.0.0.1:8180/api/v1/instances/getting-started-server/queries/0a1b/attach');
  stream.listeners.snapshot(snapshot([
    {MessageText: 'Hello World', Count: 2}, {MessageText: 'Goodbye World', Count: 1}
  ]));
  assert.deepEqual(rows(app), [['Hello World', 2], ['Goodbye World', 1]]);
  const raw = '{"query_id":"0a1b","sequence":3,"results":[' +
    '{"type":"aggregation","row_signature":18446744073709551615,' +
    '"before":{"MessageText":"Hello World","Count":2},"after":{"Count":3,"MessageText":"Hello World"}},' +
    '{"type":"ADD","data":{"MessageText":"<img src=x onerror=alert(1)>","Count":1},"row_signature":1},' +
    '{"type":"DELETE","data":{"Count":1,"MessageText":"Goodbye World"},"row_signature":2}]}';
  stream.onmessage({data: raw});
  assert.deepEqual(rows(app), [['Hello World', 3], ['<img src=x onerror=alert(1)>', 1]]);
  assert.equal(app.nodes.events.textContent, `message-counts: ${raw}`);
  assert.ok(app.requests.every(url => url.includes('/api/v1/instances/getting-started-server/')));
});

test('a change that does not match the table reattaches for a fresh snapshot', async () => {
  const app = viewer();
  await app.nodes.connect.handlers.submit({preventDefault() {}});
  const first = app.streams[0];
  first.listeners.snapshot(snapshot([{MessageText: 'Hello World', Count: 2}]));
  first.onmessage({data: JSON.stringify({results: [
    {type: 'UPDATE', before: {MessageText: 'Missing', Count: 1}, after: {MessageText: 'Missing', Count: 2}}
  ]})});
  assert.equal(first.closed, true);
  assert.equal(app.streams.length, 2);
  assert.equal(app.streams[1].url, first.url);
  assert.match(app.nodes.status.textContent, /fresh snapshot/);
});

test('viewer reports disconnects and request errors, and closes old streams on reconnect', async () => {
  const app = viewer();
  await app.nodes.connect.handlers.submit({preventDefault() {}});
  const previous = app.streams[0];
  previous.onerror();
  assert.match(app.nodes.status.textContent, /next snapshot replaces the table/);
  await app.nodes.connect.handlers.submit({preventDefault() {}});
  assert.equal(previous.closed, true);
  assert.equal(app.streams.length, 2);
  app.state.failure = true;
  await app.nodes.connect.handlers.submit({preventDefault() {}});
  assert.match(app.nodes.status.textContent, /test failure/);
  assert.equal(app.nodes.status.className, 'error');
});
