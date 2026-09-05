const CACHE="arjuna-ai-v5";
const ASSETS=["/","/static/styles.css","/static/preview.css","/static/growth.css","/static/integrations.css","/static/warrior.css","/static/app.js","/static/workspace.js","/static/preview.js","/static/growth.js","/static/integrations.js","/static/icon.svg","/manifest.webmanifest"];
self.addEventListener("install",e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener("activate",e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener("fetch",e=>{if(e.request.method!=="GET")return;const path=new URL(e.request.url).pathname;if(path.startsWith("/api/")||path.startsWith("/v1/")||path.startsWith("/p/"))return;e.respondWith(fetch(e.request).then(r=>{const copy=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));return r;}).catch(()=>caches.match(e.request)));});
