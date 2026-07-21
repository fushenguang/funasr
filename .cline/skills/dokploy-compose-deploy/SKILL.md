---
name: dokploy-compose-deploy
description: Deploy a Next.js + Node.js monorepo to self-hosted Dokploy using Docker Compose. Covers idempotent bootstrap, GFW workarounds, env management, healthcheck pitfalls, and failure diagnosis. Use when deploying a monorepo (web + api + admin) to Dokploy Community Edition.
license: MIT
compatibility: Self-hosted Dokploy Community Edition. Host may be behind GFW.
metadata:
  author: calcifer
  version: "1.0"
---

Deploy a monorepo (Next.js web + Node.js API + Next.js admin) to self-hosted Dokploy using Docker Compose (`compose` type, `sourceType: raw`).

Supporting files in this skill directory:
- `templates/docker-compose.yml` — compose template with healthchecks and internal networking
- `templates/Dockerfile.nextjs` — multi-stage Next.js standalone Dockerfile
- `scripts/gfw-deploy.sh` — GFW-safe deploy via GitHub zipball + `docker service update`

---

## Dokploy Concepts

| Term | Meaning |
|------|---------|
| **Project** | Logical group of services (e.g. `my-project`) |
| **Environment** | Layer within a project (`production`, `staging`) |
| **Application** | Single-container Dockerfile service (`application.*` API) |
| **Compose** | Multi-container docker-compose service (`compose.*` API) — use this for monorepos |
| **appName** | Auto-generated slug used as Docker Swarm service name — NOT the human-readable `name` |
| **sourceType** | How Dokploy fetches the compose file: `github` (git clone) or `raw` (inline yaml string) |

> Dokploy Community Edition has **no Secrets/Vault**. All env vars are stored in plaintext in Dokploy's own database. Never use the term "secret manager" in runbooks.

### 🔑 API Authentication (verified 2026-06-24)

| Header | Value |
|--------|-------|
| `x-api-key` | API token from Dokploy Settings → API Tokens |
| `Content-Type` | `application/json` |

**⚠️ NOT `Authorization: Bearer`** — Dokploy uses `x-api-key` header exclusively. Using `Authorization` silently returns 401.

### 📡 Key API Endpoints

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/project.all` | GET | List all projects |
| `/api/project.one?projectId=` | GET | Project detail with embedded applications |
| `/api/server.all` | GET | List all servers (build + deploy) |
| `/api/registry.all` | GET | List container registries |
| `/api/application.create` | POST | Create application |
| `/api/application.update` | POST | Update application config |
| `/api/application.deploy` | POST | Trigger deployment |
| `/api/application.one?applicationId=` | GET | Application detail |
| `/api/port.create` | POST | Create port mapping |
| `/api/port.delete` | POST | Delete port mapping |

**⚠️ `/api/application.all?projectId=` returns 404** — use `project.one` to get embedded `environments[0].applications`.

### 🖥️ Server Topology (our instance)

| Name | Type | IP |
|------|------|----|
| Build-Server | build | 192.168.31.50 |
| ecs_jd | deploy | 114.67.246.199 |
| tencent_ecs | deploy | 175.27.190.215 |

### 🤖 Automation Script

`scripts/dokploy-setup.py` — idempotent create-or-update + deploy for Application type services:
```bash
python3 scripts/dokploy-setup.py \
  --app-name thefool-web-dev \
  --project-name Enterprises \
  --dockerfile apps/web/Dockerfile \
  --source-type github \
  --github-repo fushenguang/thefoolai \
  --github-branch main \
  --publish-port 3091
```

Detects if application exists → updates config. Creates if missing → deploys. Always safe to run repeatedly.

---

## Steps

### 1. Confirm project structure

Read the monorepo layout. Identify:
- Dockerfile paths for each service (`apps/web/Dockerfile`, `services/api/Dockerfile`, `apps/admin/Dockerfile`)
- Internal service ports
- Which ports need public exposure
- Required env vars per service

### 2. Prepare deployment artifacts

**2a. docker-compose.yml** — Use `templates/docker-compose.yml` as the base. Key rules:
- API service: **no** published port — web and admin reach it via Docker internal DNS (`http://api:<port>`)
- All services on a shared `overlay` network
- Every service must have a `healthcheck` using `127.0.0.1`, not `localhost` (see Gotcha #3)
- `start_period: 60s` for Next.js services (cold start is slow)
- Do NOT use `condition: service_completed_successfully` in `depends_on` — not supported on all Docker versions (see Gotcha #4)

**2b. Next.js Dockerfile** — Use `templates/Dockerfile.nextjs`. Requires `output: 'standalone'` in `next.config.js`. Without standalone mode the runner stage cannot start.

**2c. next.config.js** — Verify or add:
```js
module.exports = { output: 'standalone' };
```

### 3. Deploy via Dokploy API (idempotent)

Required env vars: `DOKPLOY_BASE_URL`, `DOKPLOY_API_TOKEN`.

```typescript
// Step 3a — find or create project + compose service
const projects = await get('/api/project.all');
const project = projects.find(p => p.name === PROJECT_NAME);
const env = project.environments.find(e => e.name === 'production');

let compose = env.composes?.find(c => c.name === COMPOSE_NAME);
if (!compose) {
  compose = await post('/api/compose.create', { name: COMPOSE_NAME, projectId: project.projectId });
}

// Step 3b — CRITICAL: always call update immediately after create to set sourceType
// compose.create silently ignores sourceType — it always defaults to 'github'
await post('/api/compose.update', {
  composeId: compose.composeId,
  sourceType: 'raw',
  composeFile: fs.readFileSync('deploy/docker-compose.yml', 'utf8'),
  env: Object.entries(envVars).map(([k, v]) => `${k}=${v}`).join('\n'),
});

// Step 3c — deploy and poll (5 min timeout — compose stacks take longer than single containers)
await post('/api/compose.deploy', { composeId: compose.composeId });
await pollUntil(() => get(`/api/compose.one?composeId=${compose.composeId}`)
  .then(r => ['done', 'error'].includes(r.composeStatus)), { timeoutMs: 300_000 });
```

### 4. If host is behind GFW (git clone fails)

Use `scripts/gfw-deploy.sh`. It bypasses Dokploy's clone pipeline entirely:
1. Downloads source via GitHub zipball API (HTTPS REST — far less GFW interference than git)
2. Builds Docker image directly from `/tmp`
3. Updates the Swarm service with `docker service update --image`

> **Do not** waste time re-checking `/etc/hosts` SNI pins. If `curl https://github.com/` returns 200 but deploy still fails, the git path is blocked — go straight to the zipball script.

### 5. Verify deployment ⚠️ MANDATORY

**Deployment is NOT complete until ALL of the following pass.** Never report "done" based on CI/CD status alone — the Dokploy deploy API returns success even when the container crashes immediately.

#### 5a. Container liveness check

```bash
# Container must be Up (not Restarting, not Exited)
ssh root@<host> "docker ps --filter 'name=<app-name>' --format '{{.Names}} {{.Status}}'"

# If no container found, look for Docker Swarm services
ssh root@<host> "docker service ls --filter 'name=<app-name>'"
```

#### 5b. HTTP response check

```bash
# Test every known working path (NOT just /api/health — that may not exist)
# Use multiple paths to catch SSR render errors vs static-serving errors
curl -sS -m 5 -o /dev/null -w '%{http_code}' http://<host>:<port>/
curl -sS -m 5 -o /dev/null -w '%{http_code}' http://<host>:<port>/<a-known-route>
```

**Any non-200 response (especially 500, 502, 503) is a DEPLOYMENT FAILURE.**

#### 5c. Container log check for runtime errors

```bash
# Check the last 30 log lines for runtime errors (not build warnings)
ssh root@<host> "docker logs <container-name> 2>&1 | tail -30"

# Key things to look for:
#   - "TypeError" / "ReferenceError" / "Unhandled rejection" → FAILED
#   - "Listening on" → PASSED (app started)
#   - Repeated crash/restart loops → FAILED
#   - "Cannot find module" → FAILED (missing dependency)
```

#### 5d. Common post-deploy failures and fixes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| 500 `jsxDevRuntimeExports.jsxDEV is not a function` | `@vitejs/plugin-react` after `tanstackStart()` in plugins array, or missing `NODE_ENV=production` during build | Move `viteReact()` before `tanstackStart()`; add `ENV NODE_ENV=production` in build stage |
| 500 `Cannot read properties of undefined (reading 'digest')` | SPA prerendered HTML mismatches client hydration for SSR-dependent lib (e.g. Fumadocs) | Disable SPA mode → use standard SSR |
| Container `Restarting` loop | CMD in Dockerfile fails (wrong path, missing file) | `docker logs <name>` to get the exact error |
| 200 but blank page | SPA `_shell.html` fallback serves empty shell without route resolution | Check `serve.json` rewrites or switch to SSR runner |
| `package.json` not found | Docker build context wrong — COPY assumes repo root | Ensure `docker build -f apps/<app>/Dockerfile` runs from monorepo root |

#### 5e. Declaration

Before reporting success to the user, **confirm**:
```
✅ Container is running (not restarting)
✅ HTTP 200 on at least 2 different routes
✅ No runtime errors in logs
❌ If ANY failure → diagnose and fix before reporting completion
```

---

## Gotchas (production-verified)

### #1 — `compose.create` ignores `sourceType`
**Symptom**: deploy reports "Github Provider not found" even though you passed `sourceType: 'raw'`.  
**Fix**: always call `compose.update` immediately after `compose.create` to set `sourceType: 'raw'`.

### #2 — `compose.update` env ≠ what the container sees
**Symptom**: Dokploy UI shows updated env, deploy status is `done`, but `docker exec ... env` shows old values.  
**Root cause**: Dokploy deploy reuses the existing Swarm service spec; it does not re-read Dokploy's DB.  
**Fix** (takes effect in seconds):
```bash
ssh root@<host> "docker service update --env-add KEY=VALUE <swarm-service-name>"
# Get swarm service name: docker service ls | grep <keyword>
```
Always verify with `docker exec` after any env change — Dokploy UI and actual container env can diverge.

### #3 — `localhost` resolves to IPv6 in Alpine healthchecks
**Symptom**: healthcheck fails immediately; container never becomes healthy.  
**Root cause**: Alpine resolves `localhost` → `::1` (IPv6), but the app listens on `0.0.0.0` (IPv4 only).  
**Fix**: use `127.0.0.1` in all `healthcheck.test` commands. Also, `node:alpine` has no `wget` — use:
```yaml
test: ["CMD", "node", "-e", "require('http').get('http://127.0.0.1:3000/api/health',r=>process.exit(r.statusCode===200?0:1))"]
```

### #4 — `service_completed_successfully` not supported on all hosts
**Symptom**: `composeStatus=error`, `deployments[0].log=""` (empty log — fails before docker compose runs).  
**Fix**: replace with `condition: service_healthy` or remove the `depends_on` condition entirely.

### #5 — `compose.stop` ≠ `docker compose down`
`compose.stop` only stops containers (leaves writable layers). To clean up orphaned bind-mount directories:
```bash
ssh root@<host> "cd /etc/dokploy/compose/<appName>/code && docker compose down"
```

### #7 — `application.create` silently drops critical fields (same as Gotcha #1 for compose)
**Symptom**: you pass `githubId`, `buildServerId`, `buildType: "dockerfile"`, `owner`, `repository` in the create body but after creation these fields are all `null` or `nixpacks`.  
**Fix**: **always** follow `create` with an immediate `update` to set:
- `githubId` / `gitlabId`
- `buildServerId`
- `buildType: "dockerfile"` (defaults to `nixpacks`!)
- `owner`, `repository`, `branch`
- `watchPaths`, `enableSubmodules`

**Correct Application creation flow:**
```
create (name + projectId + serverId + envId + sourceType)  →  update (githubId + buildServerId + buildType + dockerfile + watchPaths)  →  deploy
```

If `buildType` ends up as `nixpacks`, the app will ignore your `dockerfile` field and fail immediately.

### #8 — GitHub field names in Application API
**⚠️ The Application API uses `owner`/`repository`/`branch`, NOT `githubOwner`/`githubRepository`/`githubBranch`.**  
Reference an existing GitHub-sourced application to confirm the exact field names before creating new ones.

### #9 — Monorepo Docker: `--filter` is mandatory
**Symptom**: Docker build fails with native module errors (e.g. `better-sqlite3`, `bufferutil`, `utf-8-validate`) from apps you're not even deploying.  
**Root cause**: `pnpm install` without `--filter` installs ALL workspace packages, pulling in native deps from unrelated apps.  
**Fix**:
```dockerfile
# ❌ Installs every app in the monorepo
RUN pnpm install --frozen-lockfile

# ✅ Installs only the target app + its workspace deps + skips native rebuilds
RUN pnpm install --filter @myapp/web... --frozen-lockfile --ignore-scripts
```
Also COPY any root tsconfig files that the app's `tsconfig.json` extends (e.g. `tsconfig.base.json`).

### #10 — Nitro standalone runner needs no pnpm
Nitro's standalone output (`.output/`) is fully self-contained. The runner stage only needs:
```dockerfile
FROM node:24-alpine3.22 AS runner
WORKDIR /app
COPY --from=builder /app/apps/web/.output ./apps/web/.output
CMD ["node", "apps/web/.output/server/index.mjs"]
```
No `pnpm install`, no `packages/` copy, no `node_modules` manipulation.

### #11 — GFW: GnuTLS error on GitHub clone
**Symptom**: `fatal: unable to access 'https://github.com/...': GnuTLS recv error (-110): The TLS connection was non-properly terminated`.  
**Root cause**: Build-Server in mainland China cannot access GitHub via git protocol.  
**Fix**: Use `scripts/gfw-deploy.sh` (GitHub zipball API over HTTPS REST → local Docker build → `docker service update`). Or mirror the repo to a self-hosted GitLab instance (e.g. `git.fujia.site`).

### #12 — Env vars via API
Set application environment variables:
```json
POST /api/application.update
{
  "applicationId": "...",
  "env": "KEY1=value1\nKEY2=value2"
}
```
**⚠️ Dokploy Gotcha #2 applies**: after updating env via API, containers may still show old values. Verify with `docker exec ... env`. Wiki/static sites typically need no env vars. Web apps need at minimum `SUPABASE_URL` + `SUPABASE_ANON_KEY`.

### #13 — Port creation is idempotent-friendly
`/api/port.create` succeeds even if a port mapping already exists (returns existing port). No need to delete first. Append `publishMode: "ingress"` for Traefik routing.

---

## Failure Diagnosis Tree

```
composeStatus=error, log="" (empty)
  → port conflict:  ss -tlnp sport = :<port>
  → yaml error:     docker compose -f deploy/docker-compose.yml config  (run locally)

composeStatus=error, log has content
  → "Github Provider not found"  →  compose.update with sourceType='raw'
  → "unable to access github.com"  →  run scripts/gfw-deploy.sh
  → healthcheck failed  →  Gotcha #3 (127.0.0.1 + no wget in alpine)

composeStatus=running → error  (containers started but unhealthy)
  → start_period too short  →  set to 60s for Next.js
  → healthcheck command broken  →  docker exec manually to test it

composeStatus=done, but ECONNREFUSED
  → wait 30s (Gotcha #6)
  → docker service ls: check REPLICAS shows 1/1
```

---

## Guardrails

- Never hard-code `appName` (Dokploy auto-generates it) — always read it from `compose.one` response.
- Never assume `compose.update` env is live in the container — always verify with `docker exec`.
- Do not use `compose.stop` when you need a clean slate — SSH and run `docker compose down`.
- Do not add published ports to the API service — it should only be reachable via internal DNS.
