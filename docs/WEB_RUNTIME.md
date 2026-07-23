# OpenMontage / EveDirector Web Runtime

This document defines the first hosted-runtime path for the EVEMISSLAB fork.
The fork remains licensed under GNU AGPLv3.

## Goal

Turn the existing local, read-only Backlot board into a deployable web runtime
without breaking the original local workflow.

The first phase intentionally keeps Backlot read-only. Video production still
writes normal OpenMontage project artifacts; the hosted board observes the
mounted project directory and publishes live changes over SSE.

## What changed

- `BACKLOT_HOST` controls the bind address.
- `BACKLOT_PORT` remains supported.
- platform-provided `PORT` is accepted as a fallback.
- `Dockerfile.web` provides Python, FFmpeg, Node.js, npm, and the OpenMontage
  dependencies.
- `docker-compose.web.yml` mounts `./projects` at `/data/projects`.
- `OPENMONTAGE_PROJECTS_DIR` remains the single source of truth for project
  storage.

The local command continues to use loopback:

```bash
python -m backlot open
```

Hosted mode can bind to all interfaces:

```bash
BACKLOT_HOST=0.0.0.0 BACKLOT_PORT=4750 \
python -m backlot serve
```

## Docker quick start

```bash
docker compose -f docker-compose.web.yml up --build
```

Open:

```text
http://localhost:4750
```

## Persistent storage

Backlot derives all state from the OpenMontage project directory. A hosted
runtime must therefore use persistent storage for:

```text
/data/projects
```

The initial Compose profile maps the repository's `./projects` directory into
that location. A cloud deployment should replace it with a persistent volume.
Do not use an ephemeral filesystem for real productions.

## Network exposure and authentication

Backlot currently has no built-in account or permission system. Do not expose
it directly to the public internet in this phase.

Put it behind an authentication-aware reverse proxy or access gateway, for
example:

- Cloudflare Access / Tunnel
- an authenticated Caddy or Nginx reverse proxy
- a private VPN or zero-trust network

The next EveDirector control-plane phase will add project ownership, write
commands, and explicit permission boundaries. Those controls must not be mixed
into the read-only observer casually.

## AGPL source availability

A modified public network service must provide users access to the
corresponding source code of the running version. Set and display the fork's
source repository URL in the deployed interface or surrounding site:

```text
https://github.com/kakon77777-commits/OpenMontage
```

Recommended deployment metadata:

```bash
OPENMONTAGE_SOURCE_URL=https://github.com/kakon77777-commits/OpenMontage
```

A later UI patch should display this URL persistently in the footer or About
panel together with the AGPLv3 license notice and deployed commit SHA.

## Phase boundaries

### Phase W1 — hosted observer

- containerized Backlot
- persistent project volume
- SSE updates
- authenticated gateway
- source-code link
- one web-accessible production library

### Phase W2 — EveDirector control plane

- Project Graph API
- users and project ownership
- editable workflow
- infinite canvas
- timeline projection
- command/event log
- approval actions

### Phase W3 — hosted production worker

- queued agent runs
- model/provider secrets
- isolated workspaces
- render workers
- cost and quota policies
- artifact/object storage

### Phase L — local package

After the web architecture is stable, package the same Project Graph and UI as
a local desktop or one-command self-hosted distribution. Local mode should not
become a separate product or data model.

## Architectural rule

The hosted web UI and later local UI must share the same Project Graph and
command/event contracts. Only deployment, authentication, storage, and worker
routing should differ.
