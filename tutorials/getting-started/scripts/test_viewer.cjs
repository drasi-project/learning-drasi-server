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
    ['connect', 'api', 'sse', 'status', 'queries', 'events'].map(id => [id, new Element()])
  );
  nodes.api.value = 'http://127.0.0.1:8180';
  nodes.sse.value = 'http://127.0.0.1:8181/events';
  const connections = [];
  const requests = [];
  const state = {rows: [{MessageText: 'Hello World', Count: 2}], failure: false};
  const context = {
    document: {
      getElementById: id => nodes[id],
      createElement: () => new Element(),
      createTextNode: value => ({textContent: value})
    },
    EventSource: class {
      constructor(url) { this.url = url; connections.push(this); }
      close() { this.closed = true; }
    },
    fetch: async url => {
      requests.push(url);
      return {
        ok: !state.failure,
        json: async () => state.failure
          ? {success: false, error: 'test failure'}
          : {success: true, data: url.endsWith('/queries')
            ? [{id: 'message-counts'}] : state.rows}
      };
    }
  };
  const html = fs.readFileSync(path.join(__dirname, '../viewer/index.html'), 'utf8');
  vm.runInNewContext(html.split('<script>')[1].split('</script>')[0], context);
  return {nodes, connections, requests, state};
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test('viewer refreshes real current results on connect and change without treating events as a snapshot', async () => {
  const app = viewer();
  await app.nodes.connect.handlers.submit({preventDefault() {}});
  const connection = app.connections[0];
  assert.equal(connection.url, app.nodes.sse.value);
  connection.onopen();
  await settle();
  const panel = app.nodes.queries.children[0];
  const body = panel.children[1];
  assert.equal(body.children[0].children[1].children[1].textContent, 2);
  const raw = '{"queryId":"message-counts","results":[{"type":"aggregation","row_signature":18446744073709551615,"before":{"Count":2},"after":{"Count":3}}]}';
  app.state.rows = [{MessageText: '<img src=x onerror=alert(1)>', Count: 3}];
  connection.onmessage({data: raw});
  await settle();
  assert.equal(body.children[0].children[1].children[1].textContent, 3);
  assert.equal(body.children[0].children[1].children[0].textContent, '<img src=x onerror=alert(1)>');
  assert.equal(app.nodes.events.textContent, raw);
  assert.ok(app.requests.every(url => url.includes('/api/v1/instances/getting-started-server/')));
});

test('viewer rejects native sink payloads and makes disconnects and snapshot errors visible', async () => {
  const app = viewer();
  await app.nodes.connect.handlers.submit({preventDefault() {}});
  const connection = app.connections[0];
  connection.onmessage({data: '{"output":{},"sequence":1,"changes":[]}'});
  assert.match(app.nodes.status.textContent, /Expected ordinary SSE reaction/);
  connection.onerror();
  assert.match(app.nodes.status.textContent, /Events may be missing/);
  app.state.failure = true;
  connection.onopen();
  await settle();
  assert.match(app.nodes.status.textContent, /test failure/);
  assert.equal(app.nodes.status.className, 'error');
});

test('viewer ignores heartbeats and closes its old stream on explicit reconnect', async () => {
  const app = viewer();
  await app.nodes.connect.handlers.submit({preventDefault() {}});
  const previous = app.connections[0];
  previous.onmessage({data: '{"type":"heartbeat","ts":1}'});
  assert.equal(app.nodes.events.textContent, '');
  await app.nodes.connect.handlers.submit({preventDefault() {}});
  assert.equal(previous.closed, true);
  assert.equal(app.connections.length, 2);
});
