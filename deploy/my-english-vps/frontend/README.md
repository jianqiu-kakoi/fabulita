# My English VPS frontend

Static Vite shell for the My English learner. The learner stays inside the
same-origin iframe while this shell provides email/password accounts, progress
sync, and the server-side LLM scoring bridge.

## Build and verify

```sh
npm ci
npm run check
```

`npm run build` copies `docs/my-english.html` and
`docs/my-english-og.png` from the repository into the generated `dist/`
directory. Generated `public/`, `dist/`, and `node_modules/` directories are
ignored.

For local development, `npm run dev` serves on `127.0.0.1:4174` and proxies
`/api` to `127.0.0.1:3000`.

## Runtime contract

The production web server must serve `dist/` and proxy `/api` to the
same-origin backend. Every request includes browser credentials. The frontend
uses:

- `GET /api/auth/me`
- `POST /api/auth/register` with
  `{ "email", "password", "privacyConsent": { "accepted": true, "version": "2026-07-25" } }`
- `POST /api/auth/login` with `{ "email", "password" }`
- `POST /api/auth/logout`
- `POST /api/action` with the existing sync or score action payload

Successful authentication responses provide
`{ "ok": true, "user": { "id", "email" }, "csrfToken" }`. The current CSRF
token is sent as `X-CSRF-Token` on logout and action calls. Errors use
`{ "ok": false, "code", "message" }` with a matching non-2xx status.

The backend cookie must be `HttpOnly`, `Secure` in production, and use an
appropriate `SameSite` policy. The browser never stores the password or any LLM
provider key.
