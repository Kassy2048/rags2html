/** This service worker is a way to play HTML files located in MEMFS.
 * It forwards fetch requests to the rags2html page so it can extract the resources
 * and send them back to the browser.
 */

// play/<pageId>/<path>
const pathRE = new RegExp("/play/([^/]+)/(.*)(\\?.*)?$");

// Map of pending requests that will get resolved when the page send the response message
self.requests = {
  // id: {path, pageId, resolve, reject, time},
};
self.reqId = 0;

self.addEventListener("fetch", (e) => {
  console.debug('SW', 'fetch', e);
  const m = pathRE.exec(e.request.url);
  if(m === null) return;

  const pageId = decodeURIComponent(m[1]);
  const path = decodeURI(m[2]);

  e.respondWith(new Promise(async (resolve, reject) => {
    const client = await self.clients.get(pageId);
    if(client === undefined) {
      // Page has been closed/reloaded
      resolve(new Response(null, {
        status: 404,
      }));
      return;
    }

    const reqId = ++self.reqId;
    self.requests[reqId] = {
      path: path,
      pageId: pageId,
      resolve: resolve,
      reject: reject,
      time: Date.now(),  // TODO Remove stale requests
    };

    client.postMessage({name: 'getFile', id: reqId, path: path});
  }));
});

self.addEventListener("message", (e) => {
  console.debug('SW', 'message', e);
  const msg = e.data;
  const client = e.source;
  switch(msg.name) {
    case 'getPageId':
      client.postMessage({name: 'getPageId-resp', id: msg.id, pageId: client.id});
      break;

    case 'getFile-resp':
      const request = self.requests[msg.id];
      if(request === undefined) {
        console.error('File request ID not found', msg);
        break;
      }

      delete self.requests[msg.id];

      if(msg.error !== undefined) {
        request.resolve(new Response(null, {
          status: msg.error,
        }));
      } else {
        request.resolve(new Response(msg.content, {
          //TODO headers: { "Content-Type": "application/json" },
        }));
      }
      break;

    default:
      console.error('Invalid message', e);
      client.postMessage({name: 'error', id: msg.id, text: `Invalid message: ${msg}`});
  }
});

self.addEventListener("install", function () {
  console.debug('SW', 'install');
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  console.debug('SW', 'activate');
  event.waitUntil(self.clients.claim());
  console.debug('SW', 'ready');
});