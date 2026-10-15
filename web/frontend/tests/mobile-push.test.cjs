/* eslint-disable @typescript-eslint/no-require-imports */
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function worker() {
  const handlers = {}, notices = [], opened = [];
  const self = { location: { origin: 'https://search.example.test' }, addEventListener: (name, fn) => { handlers[name] = fn; }, registration: { showNotification: async (...args) => notices.push(args) }, clients: { matchAll: async () => [], openWindow: async url => opened.push(url) } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../public/searchos-sw.js'), 'utf8'), { self, URL });
  return { handlers, notices, opened };
}
test('notification target stays on mobile origin; private responses are never cached', async () => {
  const { handlers, notices, opened } = worker(); let pending;
  handlers.push({ data: { json: () => ({ url: 'https://evil.example/steal', body: 'generic', tag: 'event' }) }, waitUntil: p => { pending = p; } });
  await pending;
  assert.equal(notices[0][1].data.url, 'https://search.example.test/m?view=inbox');
  let closed = false;
  handlers.notificationclick({ notification: { close: () => { closed = true; }, data: { url: '/m?report=r1' } }, waitUntil: p => { pending = p; } });
  await pending;
  assert.equal(closed, true);
  assert.equal(opened[0], 'https://search.example.test/m?report=r1');
  assert.equal(handlers.fetch, undefined);
});
test('malformed push still displays a generic reminder', async () => {
  const { handlers, notices } = worker(); let pending;
  handlers.push({ data: { json: () => { throw new Error('invalid'); } }, waitUntil: p => { pending = p; } });
  await pending;
  assert.equal(notices[0][0], 'SearchOS');
  assert.equal(notices[0][1].body, '你有一条新的任务消息。');
});
