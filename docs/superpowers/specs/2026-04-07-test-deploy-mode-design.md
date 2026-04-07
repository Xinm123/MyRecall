# Test/Deploy Mode Switching Design

## Status

Approved: 2026-04-07

## Overview

Add `--mode local` / `--mode remote` command-line flags to `run_client.sh` and `run_server.sh` to switch between local testing and deployed configurations.

## Motivation

Currently, switching between local testing (client + server on same machine) and deployed mode (client on local, server on edge) requires manually editing config files. This is error-prone and inconvenient. A simple `--mode` flag makes switching instant and explicit.

## Configuration Files

Create four new TOML configuration files:

| File | Purpose | Key Values |
|------|---------|------------|
| `client-local.toml` | Client + local Edge on same machine | API URL: `http://localhost:8083/api` |
| `client-remote.toml` | Client connects to remote Edge | API URL: `http://10.77.3.162:8083/api` |
| `server-local.toml` | Local Edge server (testing) | Host: `127.0.0.1`, Port: `8083` |
| `server-remote.toml` | Remote Edge server (production) | Host: `0.0.0.0`, Port: `8083` |

All other settings (capture, debounce, OCR, AI, etc.) remain identical across modes.

## Mode Parameter

### CLI Usage

```bash
# Client
./run_client.sh --mode local   # → client-local.toml
./run_client.sh --mode remote  # → client-remote.toml

# Server
./run_server.sh --mode local   # → server-local.toml
./run_server.sh --mode remote  # → server-remote.toml
```

### Mode Value Mapping

| Mode | Client API URL | Edge Base URL | Server Host | Server Port |
|------|---------------|---------------|-------------|-------------|
| `local` | `http://localhost:8083/api` | `http://localhost:8083` | `127.0.0.1` | `8083` |
| `remote` | `http://10.77.3.162:8083/api` | `http://10.77.3.162:8083` | `0.0.0.0` | `8083` |

### Backward Compatibility

- `--config` and `--env` flags still work as before (explicit overrides)
- When `--mode` is provided, it takes precedence over auto-discovered TOML
- When neither `--mode` nor `--config` is provided, fall back to existing auto-discovery behavior (existing `client.toml` / `server.toml`)
- `--debug` flag remains unchanged

## Implementation Details

### Shell Script Changes (`run_client.sh`, `run_server.sh`)

1. Add `--mode` argument parsing (accepts: `local`, `remote`)
2. When `--mode` is set, construct config path: `{name}-{mode}.toml`
3. Validate the mode value (fail fast if unknown mode)
4. Pass the resolved config path to Python entry point

### New Files to Create

- `client-local.toml` — from current `client.toml`, update API URLs
- `client-remote.toml` — from current `client.toml`, update API URLs
- `server-local.toml` — from current `server.toml`, update server host
- `server-remote.toml` — from current `server.toml`, update server host

### Files to Modify

- `run_client.sh` — add `--mode` parsing
- `run_server.sh` — add `--mode` parsing

### Files to Update (optional, low priority)

- `client.toml` → rename to `client.toml.example` as template reference
- `server.toml` → rename to `server.toml.example` as template reference

## Data Directory

All modes use the same data directories (`~/MRS` for server, `~/MRC` for client) to avoid confusion. Users who need separate data directories for testing can use `OPENRECALL_SERVER_DATA_DIR` / `OPENRECALL_CLIENT_DATA_DIR` environment variables as overrides.

## Error Handling

- Unknown `--mode` value: print usage message and exit with code 2
- `--mode` specified but config file not found: print error with expected path and exit with code 1
- Both `--mode` and `--config` provided: `--config` takes precedence (explicit override), print info message
