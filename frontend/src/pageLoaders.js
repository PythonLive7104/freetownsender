/* One place that knows how to fetch each page's chunk.
   App.jsx wraps these in lazy() for routing; Layout.jsx calls them on nav hover to
   warm the chunk before the click lands. Sharing the map keeps the two in step and
   avoids a circular import between App and Layout.

   Repeat calls are free — the browser and Vite both cache a resolved module. */
export const pageLoaders = {
  "/mailboxes": () => import("./pages/Mailboxes"),
  "/auto-reply": () => import("./pages/AutoReply"),
  "/rules": () => import("./pages/Rules"),
  "/check": () => import("./pages/Check"),
  "/configuration": () => import("./pages/Configuration"),
  "/listeners": () => import("./pages/Listeners"),
  "/placeholders": () => import("./pages/Placeholders"),
  "/links": () => import("./pages/Links"),
  "/attachments": () => import("./pages/Attachments"),
  "/proxies": () => import("./pages/Proxies"),
  "/team": () => import("./pages/Team"),
  "/billing": () => import("./pages/Billing"),
  "/security": () => import("./pages/Security"),
  "/telegram": () => import("./pages/Telegram"),
  "/settings": () => import("./pages/Settings"),
};

/** Warm a page's chunk ahead of the click. Never throws — a failed prefetch just
 *  means the normal lazy load happens on navigation instead. */
export function prefetchPage(path) {
  pageLoaders[path]?.().catch(() => {});
}
