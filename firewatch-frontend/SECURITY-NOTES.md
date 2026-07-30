# Frontend Security Notes

## Accepted `npm audit` findings

`npm audit` currently reports findings that we have reviewed and accepted as
not applicable. If a bump becomes available that resolves one without a
disruptive breaking change, prefer taking it and removing the entry here.

### react-router — GHSA-qwww-vcr4-c8h2 (high) — accepted 2026-07-29

- **Advisory:** RSC Mode CSRF Bypass Allows Action Execution Before 400 Response.
- **Affected range:** react-router `7.12.0 – 8.2.0` (we are on `7.18.2`, the
  latest v7). There is **no patched v7** — the only fix is `react-router@8.3.0`,
  a second breaking major.
- **Why accepted:** the vulnerable code path is React Router's **RSC / server
  action** handling. This app is a client-side Vite SPA that uses only
  declarative routing (`BrowserRouter` + `<Routes>`/`<Route>` and the routing
  hooks). It has no RSC mode, no framework mode, no server actions, and no
  `createBrowserRouter` data router, so the affected path is never executed.
- **Revisit when:** upgrading to React Router v8 is on the table for other
  reasons, or a patched v7 line is published. At that point re-evaluate and
  drop this note.
