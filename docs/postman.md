# Postman, from zero — testing the Ward Vitals lab's API

A guided first session with [Postman](https://www.postman.com), written for
someone who has never opened the tool. You will make ten API calls against
this lab — the same calls a monitoring script or CI job would make — and
learn the three most common auth styles on the way.

## What is Postman, in one paragraph

An API is what a server looks like to other programs: URLs you fetch
(`GET`) and data you send (`POST`), with responses in JSON. Postman is a
friendly GUI on top of that — you type the URL, click **Send**, and read the
response without writing any code. Requests can be saved into a
**collection**, share secrets through **environments** as variables
(`{{name}}`), and check responses automatically with test scripts.

## What we'll do in this lab

You do not need to type any request from scratch. Two files import
everything. Your only real work is to paste two credentials and click Send
ten times, top to bottom.

| # | Request | Proves | Auth used |
| --- | --- | --- | --- |
| 01 | Health check | the server is alive | none |
| 02 | Who am I | your password credentials work | basic |
| 03 | Read datasources | Grafana sees TimescaleDB | basic |
| 04 | Find the Ward dashboard | dashboards are indexable | basic |
| 05 | Fetch the dashboard JSON | dashboards are exportable | basic |
| 06 | Run live SQL | SQL can hit TimescaleDB through the API | basic |
| 07 | Create a service account | machines get a named identity | basic |
| 08 | Mint an API token | identities get secrets | basic |
| 09 | Use the token | bearer tokens authenticate | bearer |
| 10 | Cleanup | everything deleted again | basic |

Requests 07–10 create a temporary *service account* and then delete it, so
the lab is left exactly as it was.

## Before you start

- The stack is running: `make infra-up` (see [Infrastructure](infrastructure.md)).
- You can open Grafana at http://localhost:3000.
- In the terminal, `grep -E 'GF_SECURITY_(ADMIN_USER|ADMIN_PASSWORD)' .env`
  — or open `.env` — and note your admin username and password. You will
  paste them into Postman shortly.

## Part 1 — Install and open Postman

1. Download Postman from <https://www.postman.com/downloads/>, install, and
   open it. Skip any "create a workspace" prompts for now.
2. Ignore everything on screen except the **Import** button (top-left, or
   the `Import` menu entry). You only need two files from this repo:
   - `postman/postman_collection.json` — the ten requests
   - `postman/postman_environment.json` — the variables/secrets
3. Click **Import**, select **Upload Files**, pick both files, and Import.
   You should now see a collection called
   **"Ward Vitals Lab — Grafana API"** in the left sidebar.

## Part 2 — Set up the environment (variables)

Postman uses **{{double-curly}}** placeholders so requests don't hard-code
URLs or secrets. The values live in the environment you just imported.

1. In the top-right of the window there's a dropdown that says
   **No Environment** (or similar). Click it and choose
   **"Ward Vitals Lab (local)"**.
2. Click the **eye icon** next to that dropdown → **Variables** → pencil /
   edit. You'll see five entries. Fill in:
   - `adminUser` ← your `GF_SECURITY_ADMIN_USER` value (e.g. `admin`)
   - `adminPassword` ← your `GF_SECURITY_ADMIN_PASSWORD` value.
     Fields marked `•••` are masked; the value is stored hidden on purpose.
3. Close / persist. `baseUrl` is already set to `http://localhost:3000`, and
   `scopedToken`/`serviceAccountId` stay empty — requests 07–09 fill them.

> A placeholder with no value sends as literally `{{baseUrl}}`. If you see
> that in a request, you forgot Part 2 step 1.

## Part 3 — Run the requests

Click the little arrow beside the collection name to expand it, then open
request **01 · Health check (no auth)** and press **Send**.

Three things happen, and they repeat for every request:

- **Response body** (bottom pane): the JSON the server returned.
- The **Tests** tab next to the body: a script ran and each `pm.test(...)`
  shows green. Green = the response was what the lab expects.
- Status code bubble top-right: `200` is the happy path.

Work through 01 → 10 in order. Each request's **Description** (the text
above the URL box, under the "…" menu) explains that step's one idea.

### Expected results, request by request

| # | Response code | The test script checks that… |
| --- | --- | --- |
| 01 | 200 | `database` is `"ok"`; version prints to Console |
| 02 | 200 | you're a grafana admin |
| 03 | 200 | a datasource with uid `timescale` exists |
| 04 | 200 | the index contains `ward-vitals` |
| 05 | 200 | dashboard title == `"Ward Vitals"` |
| 06 | 200 | the SQL frame returned at least one row |
| 07 | **201** | a service account named `postman-lab` was created (201 = Created) |
| 08 | 200 | a `glsa_…` token was minted and saved as `scopedToken` |
| 09 | 200 | the token is accepted (no username/password on this request!) |
| 10 | 200/204 | the account was deleted; token vars cleared |

Open the **Console** (footer icon) at request 02 and 06 to see the friendly
`console.log(...)` lines — they show the version and row counts.

### The "auth ladder" — the real lesson in this lab

1. **No auth (01)** — public endpoint, fine to leave open.
2. **Basic auth (02–08, 10)** — a username + password. The Authorization
   section of those request tabs shows the `{{adminUser}}`/`{{adminPassword}}`
   placeholders being used. This is how a person signs in.
3. **Bearer token (09)** — no credentials at all; instead an
   `Authorization: Bearer glsa_…` header. Got it from 08, scoped to the
   read-only **Viewer** role. This is how a *machine* signs in — you can
   revoke the token without changing the admin password.

Try it: run 09, then re-run 09 after running 10. Without the token variable
it returns 401 — because the token is gone. Deleting credentials works.

## Gotchas you will probably hit

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Could not get response` / ECONNREFUSED | stack isn't up, or wrong `baseUrl` | `make infra-up`; confirm `baseUrl` is `http://localhost:3000` |
| 401 on 02 | wrong password, or empty env | eye icon → re-check `adminPassword`; confirm environment is **Active** |
| 401 on 10 | you already ran 10 (id cleared) | re-run 07 → 08 → 10 in one pass |
| `{{scopedToken}}` sent literally | token never set (skipped 08) | run 07 and 08 first |
| 06 returns an empty frame | you edited the SQL to a `now()` window | keep the `WHERE time = (SELECT max(time)…)` trick, or use `time > '2026-02-01'` |
| 400 Bad Request on 06 | malformed JSON in the Body tab | validate the body; check braces and commas |

## Why the dataset window matters for request 06

The lab simulates a January ward on a clock that starts ~**2026-01-01** and
ticks forward (live tail currently ~2026-02-01+). The container's real
clock — and therefore Postgres `now()` — is today's date, which has **no**
monitoring data in it. So a "last 6 hours" query against `now()` comes back
empty by design. Request 06 sidesteps this by aggregating the **newest hour
present in `vitals`**, so it always returns rows. When you copy its SQL to
use elsewhere, remember to bind against the sim window, e.g.
`WHERE time > '2026-02-01'`.

## Cleanup

Running request 10 deletes the `postman-lab` service account and clears
`scopedToken`. If you want to double-check in the UI: Grafana →
Administration → Users and access → Service accounts — `postman-lab` will
only exist while requests 07–08 have run and 10 hasn't.

## Files in this repo

| File | Purpose |
| --- | --- |
| `postman/postman_collection.json` | the 10 requests + test scripts |
| `postman/postman_environment.json` | the `{{variables}}` (fill in credentials) |
| `docs/postman.md` | this guide |

## Further reading

- [Grafana HTTP API](https://grafana.com/docs/grafana/latest/developers/http_api/) —
  reference for every endpoint used here.
- Postman's own [Getting started](https://learning.postman.com/docs/getting-started/)
  if you want to build your own requests.