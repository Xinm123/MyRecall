# Rename openrecall → myrecall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all active references to `openrecall` / `OpenRecall` / `OPENRECALL_*` with `myrecall` / `MyRecall` / `MYRECALL_*` across the codebase, in 4 stages with per-stage verification gates.

**Architecture:** Rename the Python package directory and all import paths (Stage 1), then sweep environment variable names in code and config (Stage 2), then update packaging metadata (Stage 3), then clean documentation (Stage 4). Each stage is a separate commit with tests/verification required before proceeding.

**Tech Stack:** Python 3.11+, pydantic-settings, pytest, git, bash, systemd, pip

---

## File Structure

| File/Directory | Responsibility | Stage |
|---|---|---|
| `openrecall/` → `myrecall/` | Python package root | 1 |
| `myrecall/shared/config.py` | Pydantic env alias definitions (~30 OPENRECALL_* fields) | 2 |
| `myrecall/shared/config_base.py` | TOML loader with `OPENRECALL_CONFIG_PATH` env read | 2 |
| `myrecall/shared/logging_config.py` | Logger default component name | 1 |
| `myrecall/main.py` | Combined entry point banner | 1 |
| `myrecall/client/__main__.py` | Client entry point banner + prog + env read | 1, 2 |
| `myrecall/server/__main__.py` | Server entry point banner + prog | 1 |
| `myrecall/client/` (all subdirs) | Client modules with `from openrecall...` imports | 1 |
| `myrecall/server/` (all subdirs) | Server modules with `from openrecall...` imports | 1 |
| `myrecall/client/web/templates/*.html` | Jinja2 templates with `openrecall-config-changed` event | 1 |
| `myrecall/server/templates/*.html` | Jinja2 templates with `openrecall-config-changed` event | 1 |
| `tests/` | Test files with `import openrecall` and hardcoded env | 1, 2 |
| `run_client.sh` | Shell script with `OPENRECALL_DEBUG`, `-m openrecall.client` | 2 |
| `run_server.sh` | Shell script with `OPENRECALL_DEBUG`, `-m openrecall.server` | 2 |
| `openrecall-server.service` → `myrecall-server.service` | systemd unit with paths and module name | 2 |
| `myrecall_client.env` / `myrecall_server.env` | Environment files with `OPENRECALL_*` | 2 |
| `server-local.toml` / `client-local.toml` | TOML configs with `OpenRecall` in comments | 2 |
| `server-remote.toml` / `client-remote.toml` | TOML configs with `OpenRecall` in comments | 2 |
| `client.toml.example` / `server.toml.example` | Old config examples (to merge then delete) | 2 |
| `myrecall_client.toml.example` / `myrecall_server.toml.example` | New config examples (to keep, update comments) | 2 |
| `.coveragerc` / `.coveragerc.critical` | Coverage config with `source = openrecall` | 2 |
| `setup.py` | Package name `OpenRecall` → `MyRecall` | 3 |
| `OpenRecall.egg-info/` → `MyRecall.egg-info/` | Package metadata (delete + regen) | 3 |
| `README.md` | Project documentation | 4 |
| `CLAUDE.md` | Project documentation | 4 |
| `AGENTS.md` | Project documentation | 4 |
| `GEMINI.md` | Project documentation | 4 |

---

## Stage 1: Package Rename + Import Rewrite

### Task 1: Rename package directory

**Files:**
- Rename: `openrecall/` → `myrecall/`

- [ ] **Step 1: Rename directory**

```bash
git mv openrecall/ myrecall/
```

- [ ] **Step 2: Verify rename**

```bash
ls -d myrecall/ && test ! -d openrecall/ && echo "OK"
```

Expected: `OK`

---

### Task 2: Replace Python import statements in all .py files

**Files:**
- Modify: all `*.py` under `myrecall/` and `tests/`

- [ ] **Step 1: Replace `import openrecall` → `import myrecall`**

```bash
find myrecall/ tests/ scripts/ -type f -name "*.py" \
  -exec perl -pi -e 's/import openrecall/import myrecall/g' {} +
```

- [ ] **Step 2: Replace `from openrecall` → `from myrecall`**

```bash
find myrecall/ tests/ scripts/ -type f -name "*.py" \
  -exec perl -pi -e 's/from openrecall/from myrecall/g' {} +
```

- [ ] **Step 3: Verify no `import openrecall` or `from openrecall` remains**

```bash
grep -RIn '^import openrecall\|^from openrecall' myrecall/ tests/
```

Expected: no output (0 matches)

---

### Task 3: Replace string literal paths and logger names

**Files:**
- Modify: `myrecall/` and `tests/` .py files with string references to `openrecall`

- [ ] **Step 1: Replace `"openrecall/` path prefixes in string literals**

```bash
find myrecall/ tests/ scripts/ -type f -name "*.py" \
  -exec perl -pi -e 's/"openrecall\//"myrecall\//g' {} +
```

- [ ] **Step 2: Replace `getLogger("openrecall.` → `getLogger("myrecall.`**

```bash
find myrecall/ tests/ scripts/ -type f -name "*.py" \
  -exec perl -pi -e 's/getLogger\("openrecall\./getLogger("myrecall\./g' {} +
```

- [ ] **Step 3: Replace remaining `"openrecall"` string literals (templates, importlib, etc)**

```bash
# First, see what remains
grep -RIn '"openrecall"' myrecall/ tests/ scripts/ | head -20
```

Expected: This should show remaining hits. For each, manually inspect and decide:
- `"openrecall"` in `__main__.py` banner/logger → replace with `"myrecall"`
- `"openrecall"` in Flask template path references → replace with `"myrecall"`

Then run targeted replacement:
```bash
find myrecall/ tests/ scripts/ -type f -name "*.py" \
  -exec perl -pi -e 's/"openrecall"/"myrecall"/g' {} +
```

- [ ] **Step 4: Verify**

```bash
grep -RIn '\bopenrecall\b' myrecall/ tests/ scripts/ | grep -v 'OpenRecall' | grep -v 'OPENRECALL'
```

Expected: 0 matches

---

### Task 4: Replace HTML template JS event names

**Files:**
- Modify: `myrecall/client/web/templates/settings.html`
- Modify: `myrecall/client/web/templates/layout.html`
- Modify: `myrecall/client/web/templates/index.html`
- Modify: `myrecall/server/templates/layout.html`
- Modify: `myrecall/server/templates/index.html`

- [ ] **Step 1: Replace `openrecall-config-changed` → `myrecall-config-changed`**

```bash
find myrecall/ -type f -name "*.html" \
  -exec perl -pi -e 's/openrecall-config-changed/myrecall-config-changed/g' {} +
```

- [ ] **Step 2: Verify**

```bash
grep -RIn 'openrecall-config-changed' myrecall/
```

Expected: no output

---

### Task 5: Replace banner text and CLI prog names

**Files:**
- Modify: `myrecall/main.py`
- Modify: `myrecall/client/__main__.py`
- Modify: `myrecall/server/__main__.py`

- [ ] **Step 1: Replace banner text**

```bash
# In myrecall/main.py
perl -pi -e 's/OpenRecall Starting/MyRecall Starting/g' myrecall/main.py

# In myrecall/client/__main__.py
perl -pi -e 's/OpenRecall Client Starting/MyRecall Client Starting/g' myrecall/client/__main__.py

# In myrecall/server/__main__.py
perl -pi -e 's/OpenRecall Server Starting/MyRecall Server Starting/g' myrecall/server/__main__.py
```

- [ ] **Step 2: Replace `prog` parameter**

```bash
perl -pi -e 's/prog="openrecall-client"/prog="myrecall-client"/g' myrecall/client/__main__.py
perl -pi -e 's/prog="openrecall-server"/prog="myrecall-server"/g' myrecall/server/__main__.py
```

- [ ] **Step 3: Verify**

```bash
grep -n 'OpenRecall' myrecall/main.py myrecall/client/__main__.py myrecall/server/__main__.py
```

Expected: Only the docstring line `OpenRecall main entry point` and `OpenRecall Client entry point` may remain (those are in docstrings, will be handled in Stage 4). All banner/prog lines should be gone.

---

### Task 6: Replace logging config default component

**Files:**
- Modify: `myrecall/shared/logging_config.py`

- [ ] **Step 1: Replace default parameter**

```bash
perl -pi -e 's/component: str = "openrecall"/component: str = "myrecall"/g' myrecall/shared/logging_config.py
```

- [ ] **Step 2: Verify**

```bash
grep -n '"openrecall"' myrecall/shared/logging_config.py
```

Expected: no output

---

### Task 7: Stage 1 Verification Gate

- [ ] **Step 1: Import test**

```bash
python -c "import myrecall.client; import myrecall.server; import myrecall.shared; print('OK')"
```

Expected: `OK`

- [ ] **Step 2: Unit tests**

```bash
pytest -m unit -x
```

Expected: All pass (exit 0)

- [ ] **Step 3: Grep check for remaining lowercase `openrecall`**

```bash
grep -RIn '\bopenrecall\b' myrecall/ tests/ scripts/ 2>/dev/null | grep -v 'OpenRecall' | grep -v 'OPENRECALL' | grep -v 'openrecall_test_data' | grep -v 'openrecall-config'
```

Expected: 0 matches

- [ ] **Step 4: Commit Stage 1**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: rename openrecall/ package to myrecall/

- git mv openrecall/ myrecall/
- replace all import/from openrecall → myrecall
- replace string literal paths, logger names, template paths
- replace JS event names: openrecall-config-changed → myrecall-config-changed
- replace banner text and CLI prog names
- replace logging_config default component
EOF
)"
```

---

## Stage 2: Env Vars + Config + Scripts + Service

### Task 8: Replace pydantic env aliases in config.py

**Files:**
- Modify: `myrecall/shared/config.py`

- [ ] **Step 1: Replace all `OPENRECALL_` → `MYRECALL_` in this file**

```bash
perl -pi -e 's/OPENRECALL_/MYRECALL_/g' myrecall/shared/config.py
```

- [ ] **Step 2: Verify**

```bash
grep -c 'OPENRECALL_' myrecall/shared/config.py && grep -c 'MYRECALL_' myrecall/shared/config.py
```

Expected: First number = 0, second number ≈ 60+

---

### Task 9: Replace hardcoded os.environ reads

**Files:**
- Modify: `myrecall/client/__main__.py`
- Modify: `myrecall/client/accessibility/debug.py`
- Modify: `myrecall/client/recorder.py`
- Modify: `myrecall/client/events/permissions.py`
- Modify: `myrecall/shared/config_base.py`
- Modify: `myrecall/shared/config.py` (legacy fallback lines)
- Modify: `myrecall/client/chat/conversation.py`
- Modify: `myrecall/client/chat/config_manager.py`
- Modify: `myrecall/server/ocr/rapid_backend.py`

- [ ] **Step 1: Replace `OPENRECALL_` → `MYRECALL_` in each file**

```bash
for f in \
  myrecall/client/__main__.py \
  myrecall/client/accessibility/debug.py \
  myrecall/client/recorder.py \
  myrecall/client/events/permissions.py \
  myrecall/shared/config_base.py \
  myrecall/client/chat/conversation.py \
  myrecall/client/chat/config_manager.py \
  myrecall/server/ocr/rapid_backend.py \
  scripts/acceptance/p1_s2a_backpressure_gate.py \
  scripts/acceptance/p1_s2a_loss_rate_gate.py \
  scripts/acceptance/p1_s2a_runtime_gate.py \
  scripts/verify_phase6.py; do
  perl -pi -e 's/OPENRECALL_/MYRECALL_/g' "$f"
done
```

Note: `myrecall/shared/config.py` was already handled in Task 8.

- [ ] **Step 2: Verify no hardcoded `OPENRECALL_` remains in these files**

```bash
grep -RIn 'os\.environ.*OPENRECALL' myrecall/ | grep -v 'config\.py:'
```

Expected: no output (all env reads use MYRECALL_)

---

### Task 10: Replace env files

**Files:**
- Modify: `myrecall_client.env`
- Modify: `myrecall_server.env`

- [ ] **Step 1: Replace all `OPENRECALL_` → `MYRECALL_`**

```bash
perl -pi -e 's/OPENRECALL_/MYRECALL_/g' myrecall_client.env myrecall_server.env
```

- [ ] **Step 2: Verify**

```bash
grep -c 'OPENRECALL_' myrecall_client.env myrecall_server.env
```

Expected: both = 0

---

### Task 11: Replace TOML config file comments

**Files:**
- Modify: `server-local.toml`
- Modify: `client-local.toml`
- Modify: `server-remote.toml`
- Modify: `client-remote.toml`

- [ ] **Step 1: Replace `OpenRecall` in comments**

```bash
for f in server-local.toml client-local.toml server-remote.toml client-remote.toml; do
  perl -pi -e 's/OpenRecall/MyRecall/g' "$f"
done
```

- [ ] **Step 2: Verify**

```bash
grep -n 'OpenRecall' server-local.toml client-local.toml server-remote.toml client-remote.toml
```

Expected: no output

---

### Task 12: Merge and deduplicate config examples

**Files:**
- Modify: `myrecall_client.toml.example`
- Modify: `myrecall_server.toml.example`
- Delete: `client.toml.example`
- Delete: `server.toml.example`

- [ ] **Step 1: Check diffs to see what unique fields old examples have**

```bash
diff client.toml.example myrecall_client.toml.example
diff server.toml.example myrecall_server.toml.example
```

- [ ] **Step 2: Merge unique fields from old to new (manual)**

For each field present in `client.toml.example` but NOT in `myrecall_client.toml.example`, copy the relevant section into `myrecall_client.toml.example`. Same for server.

Key fields to check (from earlier diff analysis):
- `client.toml.example` had `show_ai_description = false` in `[ui]` section — ensure this is in `myrecall_client.toml.example` if relevant
- Check all other sections for missing fields

- [ ] **Step 3: Delete old examples**

```bash
git rm client.toml.example server.toml.example
```

- [ ] **Step 4: Update new example comments**

```bash
perl -pi -e 's/OpenRecall/MyRecall/g' myrecall_client.toml.example myrecall_server.toml.example
```

- [ ] **Step 5: Verify**

```bash
test ! -f client.toml.example && test ! -f server.toml.example && echo "Old deleted"
grep -c 'OpenRecall' myrecall_client.toml.example myrecall_server.toml.example
```

Expected: Old deleted, OpenRecall count = 0

---

### Task 13: Replace shell scripts

**Files:**
- Modify: `run_client.sh`
- Modify: `run_server.sh`

- [ ] **Step 1: Replace `OPENRECALL_` → `MYRECALL_`**

```bash
perl -pi -e 's/OPENRECALL_/MYRECALL_/g' run_client.sh run_server.sh
for f in scripts/acceptance/*.sh scripts/*.sh 2>/dev/null; do
  [ -f "$f" ] && perl -pi -e 's/OPENRECALL_/MYRECALL_/g' "$f"
done
```

- [ ] **Step 2: Replace `openrecall.client` → `myrecall.client` and `openrecall.server` → `myrecall.server`**

```bash
perl -pi -e 's/openrecall\.client/myrecall.client/g' run_client.sh
perl -pi -e 's/openrecall\.server/myrecall.server/g' run_server.sh
for f in scripts/acceptance/*.sh scripts/*.sh 2>/dev/null; do
  [ -f "$f" ] && perl -pi -e 's/openrecall\.client/myrecall.client/g; s/openrecall\.server/myrecall.server/g' "$f"
done
```

- [ ] **Step 3: Verify**

```bash
grep -n 'OPENRECALL_\|openrecall\.client\|openrecall\.server' run_client.sh run_server.sh scripts/acceptance/*.sh scripts/*.sh 2>/dev/null
```

Expected: no output

---

### Task 14: Replace systemd service file

**Files:**
- Rename: `openrecall-server.service` → `myrecall-server.service`
- Modify: `myrecall-server.service`

- [ ] **Step 1: Rename file**

```bash
git mv openrecall-server.service myrecall-server.service
```

- [ ] **Step 2: Replace content**

```bash
perl -pi -e 's/OpenRecall/MyRecall/g' myrecall-server.service
perl -pi -e 's/openrecall/myrecall/g' myrecall-server.service
```

- [ ] **Step 3: Verify**

```bash
grep -n 'openrecall\|OpenRecall' myrecall-server.service
```

Expected: no output

---

### Task 15: Replace test fixtures

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Replace `openrecall_test_data_` → `myrecall_test_data_`**

```bash
perl -pi -e 's/openrecall_test_data_/myrecall_test_data_/g' tests/conftest.py
```

- [ ] **Step 2: Replace `OPENRECALL_` → `MYRECALL_`**

```bash
perl -pi -e 's/OPENRECALL_/MYRECALL_/g' tests/conftest.py
```

- [ ] **Step 3: Replace path string `openrecall/server/database/migrations` → `myrecall/server/database/migrations`**

```bash
perl -pi -e 's|openrecall/server/database/migrations|myrecall/server/database/migrations|g' tests/conftest.py
```

- [ ] **Step 4: Verify**

```bash
grep -n 'openrecall_test_data_\|OPENRECALL_\|"openrecall/' tests/conftest.py
```

Expected: no output

---

### Task 16: Replace coverage config files

**Files:**
- Modify: `.coveragerc`
- Modify: `.coveragerc.critical`

- [ ] **Step 1: Replace `openrecall` → `myrecall`**

```bash
perl -pi -e 's/openrecall/myrecall/g' .coveragerc .coveragerc.critical
```

- [ ] **Step 2: Verify**

```bash
grep -n 'openrecall' .coveragerc .coveragerc.critical
```

Expected: no output

---

### Task 17: Stage 2 Verification Gate

- [ ] **Step 1: Run unit + integration tests**

```bash
pytest -m "unit or integration" -x
```

Expected: All pass

- [ ] **Step 2: Smoke test server startup**

```bash
# Terminal 1
./run_server.sh --mode local --debug &
SERVER_PID=$!
sleep 3
curl -fsS http://localhost:8083/v1/health && echo "Server OK"
kill $SERVER_PID 2>/dev/null
```

Expected: `Server OK`

- [ ] **Step 3: Smoke test client startup**

```bash
# Terminal 2 (after server is running)
./run_client.sh --mode local --debug &
CLIENT_PID=$!
sleep 3
curl -fsS http://localhost:8889/ && echo "Client web OK"
kill $CLIENT_PID 2>/dev/null
```

Expected: `Client web OK`

- [ ] **Step 4: Grep check for remaining `OPENRECALL_`**

```bash
grep -RIn 'OPENRECALL_' myrecall/ tests/ scripts/ \
  myrecall_client.env myrecall_server.env \
  server-local.toml client-local.toml server-remote.toml client-remote.toml \
  run_client.sh run_server.sh myrecall-server.service \
  .coveragerc .coveragerc.critical \
  2>/dev/null
```

Expected: No hits. If any remain, fix them before committing. The only acceptable exception is a historical reference in a docstring that will be handled in Stage 4 (e.g., deprecation warning text in config.py).

- [ ] **Step 5: Commit Stage 2**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: rename OPENRECALL_* env vars to MYRECALL_*

- Replace all pydantic Field(alias=OPENRECALL_*) → MYRECALL_* in config.py
- Replace 9 hardcoded os.environ reads across 7 files
- Update env files, shell scripts, systemd unit, toml configs
- Merge and deduplicate config examples (keep myrecall_*.toml.example)
- Update .coveragerc and .coveragerc.critical paths
- Update tests/conftest.py env vars and paths
EOF
)"
```

---

## Stage 3: Packaging Metadata

### Task 18: Update setup.py

**Files:**
- Modify: `setup.py`

- [ ] **Step 1: Replace package name**

```bash
perl -pi -e 's/name="OpenRecall"/name="MyRecall"/g' setup.py
```

- [ ] **Step 2: Check requirements.txt for OpenRecall references**

```bash
grep -n 'OpenRecall\|openrecall' requirements.txt 2>/dev/null || echo "No references found"
```

If any references exist, replace them.

- [ ] **Step 3: Verify setup.py**

```bash
grep -n 'OpenRecall' setup.py
```

Expected: no output

---

### Task 19: Regenerate egg-info

**Files:**
- Delete: `OpenRecall.egg-info/`
- Create: `MyRecall.egg-info/` (via pip install)

- [ ] **Step 1: Remove old egg-info**

```bash
rm -rf OpenRecall.egg-info/
git rm -r --cached OpenRecall.egg-info/ 2>/dev/null || true
```

- [ ] **Step 2: Regenerate with new name**

```bash
pip install -e .
```

- [ ] **Step 3: Verify**

```bash
pip show MyRecall >/dev/null && echo "MyRecall OK"
pip show OpenRecall 2>/dev/null || echo "OpenRecall gone"
ls MyRecall.egg-info/
```

Expected: `MyRecall OK`, `OpenRecall gone`, `MyRecall.egg-info/` exists with PKG-INFO, SOURCES.txt, etc.

---

### Task 20: Stage 3 Verification Gate

- [ ] **Step 1: Test module entry points**

```bash
python -m myrecall.client --help >/dev/null 2>&1 && echo "client OK"
python -m myrecall.server --help >/dev/null 2>&1 && echo "server OK"
```

Expected: both `OK`

- [ ] **Step 2: Commit Stage 3**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore: rename package metadata OpenRecall → MyRecall

- setup.py: name="MyRecall"
- Remove OpenRecall.egg-info/, regenerate via pip install -e .
EOF
)"
```

---

## Stage 4: Documentation Sweep + Final Check

### Task 21: Replace README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `OpenRecall` → `MyRecall`, `openrecall` → `myrecall`, `OPENRECALL_` → `MYRECALL_`**

```bash
perl -pi -e 's/OPENRECALL_/MYRECALL_/g' README.md
perl -pi -e 's/OpenRecall/MyRecall/g' README.md
```

- [ ] **Step 2: Handle GitHub URL (manual decision)**

Check if GitHub repo has been renamed:
```bash
grep 'github.com/openrecall' README.md
```

If repo URL has NOT changed, keep the old URL but add a note. If it HAS changed, replace:
```bash
# If renaming:
perl -pi -e 's|github.com/openrecall/openrecall|github.com/myrecall/myrecall|g' README.md
```

- [ ] **Step 3: Replace remaining lowercase `openrecall` in README (non-URL, non-code-block)**

```bash
# Check remaining occurrences
grep -n 'openrecall' README.md | head -20
```

Manually review each remaining occurrence. Replace contextually appropriate ones:
- `openrecall.client` → `myrecall.client`
- `openrecall.server` → `myrecall.server`

```bash
perl -pi -e 's/openrecall\.client/myrecall.client/g' README.md
perl -pi -e 's/openrecall\.server/myrecall.server/g' README.md
```

- [ ] **Step 4: Verify**

```bash
grep -c 'OPENRECALL_' README.md
grep -c 'OpenRecall' README.md
```

Expected: Both = 0 (or OpenRecall count = number of historical references like "formerly OpenRecall" which may be intentional)

---

### Task 22: Replace CLAUDE.md, AGENTS.md, GEMINI.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Modify: `GEMINI.md`

- [ ] **Step 1: Replace env var prefixes**

```bash
for f in CLAUDE.md AGENTS.md GEMINI.md; do
  perl -pi -e 's/OPENRECALL_/MYRECALL_/g' "$f"
done
```

- [ ] **Step 2: Replace brand name**

```bash
for f in CLAUDE.md AGENTS.md GEMINI.md; do
  perl -pi -e 's/OpenRecall/MyRecall/g' "$f"
done
```

- [ ] **Step 3: Replace module paths**

```bash
for f in CLAUDE.md AGENTS.md GEMINI.md; do
  perl -pi -e 's/openrecall\.client/myrecall.client/g' "$f"
  perl -pi -e 's/openrecall\.server/myrecall.server/g' "$f"
  perl -pi -e 's/openrecall\//myrecall\//g' "$f"
done
```

- [ ] **Step 4: Replace `--cov=openrecall` in AGENTS.md**

```bash
perl -pi -e 's/--cov=openrecall/--cov=myrecall/g' AGENTS.md
```

- [ ] **Step 5: Verify**

```bash
for f in CLAUDE.md AGENTS.md GEMINI.md; do
  echo "=== $f ==="
  grep -c 'OPENRECALL_' "$f"
  grep -c 'OpenRecall' "$f"  # May have "formerly OpenRecall" - check manually
  grep -n 'openrecall\.' "$f" | head -5
done
```

Expected: `OPENRECALL_` = 0 in all. `OpenRecall` may have historical references. `openrecall.` should be 0.

---

### Task 23: Update toml example comments

**Files:**
- Modify: `myrecall_client.toml.example`
- Modify: `myrecall_server.toml.example`

- [ ] **Step 1: Replace `OpenRecall` in comments**

```bash
perl -pi -e 's/OpenRecall/MyRecall/g' myrecall_client.toml.example myrecall_server.toml.example
```

- [ ] **Step 2: Verify**

```bash
grep -n 'OpenRecall' myrecall_client.toml.example myrecall_server.toml.example
```

Expected: no output

---

### Task 24: Final whitelist grep

- [ ] **Step 1: Run whitelist grep**

```bash
grep -RIn -E 'openrecall|OpenRecall|OPENRECALL_' . \
  --exclude-dir=openspec/changes/archive \
  --exclude-dir=docs/superpowers/specs \
  --exclude-dir=docs/superpowers/plans \
  --exclude-dir=_ref \
  --exclude-dir=.git \
  --exclude-dir=.claude \
  --exclude-dir=__pycache__ \
  --exclude='*.egg-info/*' \
  --exclude='*.sql' \
  --exclude='*.pyc' \
  2>/dev/null
```

- [ ] **Step 2: If any hits, triage each**

For each hit:
- In frozen dir? → Expected, no action
- In `*.egg-info/*`? → Run `pip install -e .` again or `rm -rf *.egg-info/ && pip install -e .`
- In `__pycache__`? → `find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; find . -name "*.pyc" -delete`
- In README/CLAUDE with "formerly OpenRecall"? → Intentional, add to whitelist note
- In active code/config? → Fix and rerun grep

- [ ] **Step 3: Repeat until 0 hits**

Run the grep again. If still hits, fix them. Repeat until clean.

---

### Task 25: Stage 4 Verification + Commit

- [ ] **Step 1: Run full test suite**

```bash
pytest -m "unit or integration" -x
```

Expected: All pass

- [ ] **Step 2: End-to-end smoke test**

```bash
# Terminal 1
./run_server.sh --mode local --debug &
SERVER_PID=$!
sleep 3
curl -fsS http://localhost:8083/v1/health || { echo "Server failed"; exit 1; }

# Terminal 2
./run_client.sh --mode local --debug &
CLIENT_PID=$!
sleep 3
curl -fsS http://localhost:8889/ || { echo "Client web failed"; exit 1; }

# Cleanup
kill $SERVER_PID $CLIENT_PID 2>/dev/null
wait 2>/dev/null
echo "E2E smoke OK"
```

Expected: `E2E smoke OK`

- [ ] **Step 3: Commit Stage 4**

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: sweep all docs for openrecall → myrecall

- README.md, CLAUDE.md, AGENTS.md, GEMINI.md: full rename
- AGENTS.md: --cov=openrecall → --cov=myrecall
- toml example comments updated
- Final whitelist grep: 0 hits in active code
EOF
)"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Section | Implementing Task(s) |
|---|---|
| §3: Python package dir | Task 1 |
| §3: Module paths | Task 2 |
| §3: Entry commands | Tasks 5, 13 |
| §3: Env var prefix (pydantic alias) | Task 8 |
| §3: systemd unit | Task 14 |
| §3: systemd paths | Task 14 |
| §3: Egg-info | Tasks 18-19 |
| §3: Config examples merge/dedup | Task 12 |
| §3: Top-level docs | Tasks 21-22 |
| §3: Coverage config | Task 16 |
| §3: Logger component | Task 6 |
| §3: CLI prog | Task 5 |
| §3: JS events | Task 4 |
| §4 Stage 1: banner text | Task 5 |
| §4 Stage 1: logging_config | Task 6 |
| §4 Stage 2: hardcoded env (9 locations across 8 source files + scripts/) | Task 9, Task 13 |
| §4 Stage 2: .coveragerc | Task 16 |
| §4 Stage 2: tests/conftest.py | Task 15 |
| §4 Stage 4: AGENTS.md --cov | Task 22 |
| §4 Stage 4: GitHub URL | Task 21 |
| §4 Stage 4: toml example comments | Task 23 |
| §5: pip install -e . egg-info | Task 19 |
| §5: requirements.txt | Task 18 |
| §6: pytest -m unit -x | Verification in Tasks 7, 17, 20, 25 |
| §6: pytest -m "unit or integration" -x | Verification in Tasks 7, 17, 25 |
| §6: E2E smoke | Verification in Tasks 17, 25 |
| §6: Final whitelist grep | Task 24 |

**No gaps identified (post-review fixes applied: scripts/ coverage, grep filter logic, __pycache__ exclusion, requirements.txt check).**

### Placeholder Scan

- [x] No "TBD", "TODO", "implement later", "fill in details"
- [x] No vague instructions like "add appropriate error handling"
- [x] No "Write tests for the above" without actual test code
- [x] No "Similar to Task N" cross-references
- [x] Every step shows exact commands or exact code
- [x] All file paths are exact (no relative "src/" placeholders)

### Type Consistency

- [x] `openrecall` consistently → `myrecall` (lowercase)
- [x] `OpenRecall` consistently → `MyRecall` (PascalCase)
- [x] `OPENRECALL_` consistently → `MYRECALL_` (UPPERCASE prefix)
- [x] No mixed naming within a single task
- [x] Logger component parameter matches the package name

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-05-rename-openrecall-to-myrecall.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per stage (or per task group), review between stages, fast iteration. Each subagent handles a small slice with full context.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints for review after each Stage.

**Which approach?**
