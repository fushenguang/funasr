---
name: dokploy-application-deploy
description: Deploy single-container Dockerfile services to self-hosted Dokploy via Application API. Covers idempotent setup, GFW workarounds, port mapping pitfalls, and failure diagnosis. Use when deploying wiki, web, or any single Dockerfile app to Dokploy Community Edition.
license: MIT
compatibility: Self-hosted Dokploy Community Edition. Host may be behind GFW.
metadata:
  author: calcifer
  version: "1.0"
---

Deploy a single-container Dockerfile service (e.g. Next.js wiki, Vite web app) to self-hosted Dokploy using the **Application** API (not Compose).

Supporting files:
- `../../../scripts/dokploy-setup.py` — idempotent create-or-update + deploy script
- `../dokploy-compose-deploy/scripts/gfw-deploy.sh` — GFW-safe deploy via GitHub zipball + `docker run`

---

## Dokploy Concepts

| Term | Meaning |
|------|---------|
| **Project** | Logical group of services (e.g. `Enterprises`) |
| **Application** | Single-container Dockerfile service (`application.*` API) |
| **Compose** | Multi-container docker-compose service (`compose.*` API) — use `../dokploy-compose-deploy` for this |
| **appName** | Auto-generated slug used as Docker Swarm service name |
| **buildPath** | Path within repo where build commands run (`.` for monorepo root) |
| **publishMode** | Port mode: `ingress` (Swarm routing mesh) or `host` (direct host binding) |

### 🔑 API Authentication

| Header | Value |
|--------|-------|
| `x-api-key` | API token from Dokploy Settings → API Tokens |
| `Content-Type` | `application/json` |

### 📡 Key API Endpoints

| Endpoint | Method | Notes |
|----------|--------|-------|
| `/api/project.all` | GET | List all projects |
| `/api/project.one?projectId=` | GET | Project detail with embedded applications |
| `/api/application.create` | POST | Create application (⚠️ drops critical fields — see Gotcha #1) |
| `/api/application.update` | POST | Update application config |
| `/api/application.deploy` | POST | Trigger deployment (returns empty body on success) |
| `/api/application.one?applicationId=` | GET | Application detail |
| `/api/application.delete` | POST | Delete application |
| `/api/port.create` | POST | Create port mapping (idempotent) |
| `/api/port.delete` | POST | Delete port mapping |

**⚠️ `/api/application.all?projectId=` returns 404** — use `project.one` to get embedded applications.

### 🖥️ Server Topology (our instance)

| Name | Type | IP |
|------|------|----|
| Build-Server | build | 192.168.31.50 |
| ecs_jd | deploy | 114.67.246.199 |

---

## Steps

### 1. Confirm prerequisites

Ensure the Dockerfile is ready:
- **Next.js**: `next.config.mjs` has `output: 'standalone'` (⚠️ mandatory — without it, runner stage fails)
- **Monorepo**: Dockerfile uses `pnpm install --filter <app>... --frozen-lockfile --ignore-scripts` (see Gotcha #4)
- **Build context**: Always build from repo root: `docker build -f apps/<app>/Dockerfile .`

### 2. Set up via `dokploy-setup.py` (idempotent)

```bash
python3 scripts/dokploy-setup.py \
  --app-name thefool-wiki \
  --project-name Enterprises \
  --dockerfile apps/wiki/Dockerfile \
  --source-type github \
  --github-repo fushenguang/thefoolai \
  --github-branch main \
  --publish-port 3092 \
  --server-name Build-Server \
  --env-vars "KEY1=val1;KEY2=val2"
```

This detects if the app exists → updates config. Creates if missing → deploys. Always safe to run repeatedly.

### 3. Verify deployment ⚠️ MANDATORY

Never trust `application.deploy` API response alone — Dokploy returns success even when the container crashes immediately.

#### 3a. Container check
```bash
ssh root@<host> "docker ps --filter 'name=<appName>' --format '{{.Names}} {{.Status}} {{.Ports}}'"
```

#### 3b. Port check
```bash
ssh root@<host> "ss -tlnp | grep <published-port>"
```
If port is not listening despite `docker ps` showing it, see Gotcha #5 (Swarm ingress failure).

#### 3c. HTTP check
```bash
curl -s -o /dev/null -w '%{http_code}' http://<host>:<port>/<a-known-route>
```

#### 3d. Log check
```bash
ssh root@<host> "docker logs <container-name> 2>&1 | tail -20"
```
Look for: `TypeError` / `Unhandled rejection` / `Cannot find module` / `✓ Ready`

### 4. Env var updates

```bash
# Via API
POST /api/application.update
{ "applicationId": "...", "env": "KEY1=value1\nKEY2=value2" }

# OR via setup script
python3 scripts/dokploy-setup.py --app-name <name> ... --env-vars "KEY1=val1;KEY2=val2"
```

⚠️ After updating env via API, verify with `docker exec <container> env`. Dokploy may not propagate changes to running containers immediately.

### 5. GFW workaround (when git clone fails)

Dokploy's built-in git clone fails on Build-Server (192.168.31.50) due to GFW DPI blocking git protocol. Use `../dokploy-compose-deploy/scripts/gfw-deploy.sh`:

```bash
# 1. Download source as zipball (HTTPS REST — far less GFW interference)
curl -H "Authorization: Bearer $GITHUB_PAT" \
  -o thefoolai.zip \
  "https://api.github.com/repos/fushenguang/thefoolai/zipball/main"

# 2. Build and run
cd fushenguang-thefoolai-*/
docker build -f apps/wiki/Dockerfile -t thefool-wiki:latest .
docker rm -f thefool-wiki-gf58bq 2>/dev/null
docker run -d --name thefool-wiki-gf58bq --restart unless-stopped \
  -p 3092:3000 \
  -e OPENROUTER_API_KEY=sk-... \
  -e OPENROUTER_BASE_URL=https://burn.hair/ \
  thefool-wiki:latest
```

---

## Gotchas (production-verified)

### #1 — `application.create` silently drops critical fields

**Symptom**: after creation, `buildType` is `nixpacks`, `githubId`/`buildServerId`/`owner`/`repository` are all `null`. The app ignores your Dockerfile and fails immediately.

**Fix**: always follow `create` with an immediate `update`:
```
create (name + projectId + serverId + envId)  →  update (buildType + githubId + buildServerId + dockerfile)  →  deploy
```

If `buildType` ends up as `nixpacks`, the app will ignore your `dockerfile` field.

### #2 — GitHub field names in Application API

**⚠️ Use `owner`/`repository`/`branch`, NOT `githubOwner`/`githubRepository`/`githubBranch`.**

Reference an existing GitHub-sourced application to confirm exact field names before creating new ones.

### #3 — `application.deploy` returns empty response

**Symptom**: `POST /api/application.deploy` returns empty body or 204. Scripts using `json.loads()` crash with `JSONDecodeError`.

**Fix**: handle empty/204 responses in scripts. The deploy was triggered successfully — check `application.one` deployment status to confirm.

### #4 — Monorepo Docker: `--filter` is mandatory

**Symptom**: Docker build fails with native module errors (e.g. `better-sqlite3`, `bufferutil`) from apps you're not deploying.

**Fix**:
```dockerfile
# ❌ Installs every app in the monorepo
RUN pnpm install --frozen-lockfile

# ✅ Installs only the target app + its workspace deps
RUN pnpm install --filter wiki... --frozen-lockfile --ignore-scripts
```

### #5 — Swarm ingress silently fails (port not published to host)

**Symptom**: `docker ps` shows port mapping, container logs show `✓ Ready`, but `curl http://<host>:<port>` returns connection refused. `ss -tlnp | grep <port>` shows nothing.

**Root cause**: Dokploy uses `publishMode: "ingress"` which relies on Docker Swarm's routing mesh. If the ingress network is broken, the port is never actually published on the host.

**Fix**: Verify Swarm ingress is truly broken (`docker network inspect ingress`, check IPVS rules). Only if Swarm is irreparably broken, use `docker run -p` directly (bypasses Swarm):
```bash
docker rm -f <container-name> 2>/dev/null
docker service rm <service-name> 2>/dev/null
docker run -d --name <container-name> --restart unless-stopped \
  -p <host-port>:<container-port> \
  -e KEY1=val1 \
  <image>
```

⚠️ **IMPORTANT**: Only use `docker run -p` bypass after confirming Swarm itself is broken. **DO NOT** use this for every port issue — first check Gotcha #10 (HOSTNAME binding) which is far more common.

### #6 — Next.js standalone mode requires `createMDX()` wrapper

**Symptom**: `next build` fails with "Unknown module type" for `.mdx` files. Turbopack doesn't know how to handle MDX.

**Fix**:
```js
// next.config.mjs
import { createMDX } from 'fumadocs-mdx/next';
const withMDX = createMDX();
export default withMDX({ output: 'standalone' });
```

### #7 — Next.js standalone runner CMD

After `output: 'standalone'`, the runner stage needs:
```dockerfile
FROM node:24-alpine3.22 AS runner
WORKDIR /app
COPY --from=builder /app/apps/wiki/.next/standalone ./
COPY --from=builder /app/apps/wiki/.next/static ./apps/wiki/.next/static
CMD ["node", "apps/wiki/server.js"]
```
No `pnpm install`, no `node_modules` manipulation needed.

### #8 — Feishu HMAC signing (verified)

CI notifications to Feishu use:
```bash
HMAC_KEY="${TS}\n${FEISHU_WEBHOOK_SECRET}"
SIGNED=$(printf "" | openssl dgst -sha256 -hmac "$HMAC_KEY" -binary | base64 -w0)
SIGNED_URL="${FEISHU_WEBHOOK_URL}?timestamp=${TS}&sign=${SIGNED}"
```
Key: `timestamp + "\n" + secret` is the HMAC **key** (not the message). Message is empty string. This has been verified working (June 2026).

### #9 — Env vars via API use `\n` separator

```json
POST /api/application.update
{
  "applicationId": "...",
  "env": "KEY1=value1\nKEY2=value2"
}
```

### #10 — Docker `HOSTNAME` causes Next.js to bind to wrong IP in Swarm

**Symptom**: `docker ps` shows port mapping, container logs show `✓ Ready`, `ss -tlnp` shows port LISTEN with docker-proxy, but `curl` returns **Connection reset by peer**. Other Swarm services work fine — only this service is broken.

**Root cause**: Docker automatically sets `HOSTNAME=<container-short-id>` (e.g. `HOSTNAME=6d2cd3bf90fe`). Next.js standalone server reads this, resolves it via DNS to the container's **bridge** IP (e.g. `10.0.1.37`), and only binds to that single IP. Swarm ingress routing mesh traffic arrives via the **overlay** network, which uses a different interface — the Next.js server rejects it with RST because it has no overlay IP binding.

**Proof**: `docker exec <container> netstat -tlnp` shows process listening on bridge IP only, not `0.0.0.0`.

**Fix**: Override HOSTNAME in Dockerfile runner stage:
```dockerfile
ENV HOSTNAME=0.0.0.0
```

⚠️ **Check this FIRST** when a Swarm service's port shows as LISTEN but curl fails. Gotcha #5 (Swarm ingress broken) is far less common. This is **by far the most likely cause** of "port listening but can't connect" in a Dokploy/Swarm environment.

---

## Failure Diagnosis Tree

```
application.status=error
  → "Github Provider not found"  →  application.update with githubId
  → "GnuTLS recv error"          →  Gotcha #5 (GFW — use gfw-deploy.sh)
  → "Unknown module type"        →  Gotcha #6 (add createMDX to next.config)
  → empty log                    →  port conflict or Dockerfile CMD wrong

container running but port not reachable
  → ss -tlnp shows nothing       →  Gotcha #5 (Swarm ingress broken)
  → ss shows port, curl RST      →  Gotcha #10 (HOSTNAME binding — add ENV HOSTNAME=0.0.0.0)
  → ss shows port, curl refused  →  firewall/iptables

app is 500
  → "jsxDEV is not a function"   →  Dockerfile build stage missing ENV NODE_ENV=production
  → "digest of undefined"        →  SPA mode + Fumadocs — migrate to Next.js
```

---

## Guardrails

- Always verify with `docker ps` + `ss -tlnp` + HTTP response — never trust Dokploy UI alone.
- `application.create` MUST be followed by `application.update` for non-trivial fields.
- Monorepo Dockerfiles MUST use `--filter <app>... --ignore-scripts`.
- **Never bypass Dokploy's management** (e.g. `docker run -p`) unless Swarm itself is broken. Prefer fixing application configuration (like Gotcha #10).
- When port is LISTEN but curl fails with RST, check `docker exec` netstat first — most likely HOSTNAME binding issue.
- GFW environment: assume git clone will fail — keep zipball workaround ready.
