# GitHub Actions — CI (Test Matrix)

Reference patterns for testing a Litestar app in CI. Covers uv + bun setup, Python matrix, composite actions, and the "placeholder asset directory" trick that keeps lint/typecheck jobs from falling over.

## Three real topologies

| Project | Runners | Python matrix | Setup style | Notable |
| --- | --- | --- | --- | --- |
| litestar-fullstack-inertia | `ubuntu-latest` | 3.11, 3.12, 3.13 | Reusable workflow (`test.yml` w/ `workflow_call`) | Coverage only from 3.12 |
| litestar-fullstack-spa | `ubuntu-latest` | 3.12, 3.13 | Inline, `setup-uv@v6` with `enable-cache: true` | No services; React Email built in CI |
| accelerator (DMA) | `self-hosted` | 3.11, 3.12, 3.13 | Composite actions (`setup-python`, `setup-node`) | Pins uv=0.11.6, bun=v1.3.12; aggressive disk cleanup |

## Pattern 1 — Reusable workflow (inertia)

### `.github/workflows/test.yml` (called from ci.yml)

```yaml
name: Test

on:
  workflow_call:
    inputs:
      python-version:
        required: true
        type: string
      coverage:
        required: false
        type: boolean
        default: false
      os:
        required: false
        type: string
        default: "ubuntu-latest"
      timeout:
        required: false
        type: number
        default: 60

jobs:
  test:
    runs-on: ${{ inputs.os }}
    timeout-minutes: ${{ inputs.timeout }}
    steps:
      - uses: actions/checkout@v6

      - uses: astral-sh/setup-uv@v7

      - name: Install Python ${{ inputs.python-version }}
        run: uv python install ${{ inputs.python-version }}

      - name: Placeholder frontend directory
        run: mkdir -p app/domain/web/public

      - name: Sync dependencies
        run: uv sync --all-extras --dev

      - name: Set PYTHONPATH
        run: echo "PYTHONPATH=$PWD" >> $GITHUB_ENV

      - name: Test
        if: ${{ !inputs.coverage }}
        run: uv run pytest --dist "loadgroup" -m "" -n 2

      - name: Test with coverage
        if: ${{ inputs.coverage }}
        run: uv run pytest --dist "loadgroup" -m "" --cov=app --cov-report=xml -n 2

      - uses: actions/upload-artifact@v6
        if: ${{ inputs.coverage }}
        with:
          name: coverage-xml
          path: coverage.xml
```

### `.github/workflows/ci.yml` (the caller)

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.12
      - run: mkdir -p app/domain/web/public
      - run: uv sync --all-extras --dev
      - run: uv run pre-commit install
      - uses: actions/cache@v5
        with:
          path: ~/.cache/pre-commit/
          key: pre-commit|${{ env.pythonLocation }}|${{ hashFiles('.pre-commit-config.yaml') }}
      - run: uv run pre-commit run --show-diff-on-failure --color=always --all-files

  mypy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.12
      - run: mkdir -p app/domain/web/public
      - run: uv sync --all-extras --dev
      - run: uv run mypy app/ tests/

  pyright:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.12
      - run: mkdir -p app/domain/web/public
      - run: uv sync --all-extras --dev
      - run: uv run pyright

  build_assets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: latest
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.12
      - run: mkdir -p app/domain/web/public
      - run: uv sync --all-extras --dev
      - run: uv run app assets install
      - run: make frontend-check
      - run: uv run app assets build
      - uses: actions/upload-artifact@v6
        with:
          name: built-assets
          path: app/domain/web/public/
          retention-days: 1

  test_python:
    name: "test (python ${{ matrix.python-version }})"
    strategy:
      fail-fast: true
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    uses: ./.github/workflows/test.yml
    with:
      coverage: ${{ matrix.python-version == '3.12' }}
      python-version: ${{ matrix.python-version }}

  codecov:
    needs: [test_python, validate]
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v6
      - uses: actions/download-artifact@v7
        with:
          name: coverage-xml
          path: .
      - uses: codecov/codecov-action@v5
        with:
          files: coverage.xml
          token: ${{ secrets.CODECOV_TOKEN }}
```

**Why a reusable workflow:** the test matrix is parameterized, and matrix cells emit comparable artifacts. Also, `ci.yml` stays readable — no 80-line test job repeated per Python version.

## Pattern 2 — Composite actions (accelerator)

For repos with 10+ jobs that all need the same setup, extract it to composite actions.

### `.github/actions/setup-python/action.yml`

```yaml
name: "Setup Python Environment"
description: "Set up Python with uv package manager and dependency caching"
inputs:
  python-version:
    required: false
    default: "3.12"
  install-dependencies:
    required: false
    default: "true"

runs:
  using: "composite"
  steps:
    - name: Check if uv is installed
      id: check-uv
      shell: bash
      run: |
        if command -v uv &> /dev/null; then
          echo "uv-installed=true" >> $GITHUB_OUTPUT
        else
          echo "uv-installed=false" >> $GITHUB_OUTPUT
        fi

    - name: Install uv (pinned)
      if: steps.check-uv.outputs.uv-installed != 'true'
      shell: bash
      env:
        UV_VERSION: "0.11.6"
      run: |
        set -euo pipefail
        curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
        echo "$HOME/.cargo/bin" >> "$GITHUB_PATH"

    - name: Pin Python
      shell: bash
      run: uv python pin ${{ inputs.python-version }}

    - name: Placeholder frontend directory
      shell: bash
      run: |
        mkdir -p src/py/dma/server/public
        touch src/py/dma/server/public/.gitkeep

    - name: Install dependencies
      if: inputs.install-dependencies == 'true'
      shell: bash
      run: uv sync --all-extras --dev
```

### `.github/actions/setup-node/action.yml`

```yaml
name: "Setup Node Environment"
description: "Bun + frontend dependency caching"
inputs:
  bun-version:
    required: false
    default: "latest"
  working-directory:
    required: false
    default: "src/js/web"

runs:
  using: "composite"
  steps:
    - name: Check if Bun is installed
      id: check-bun
      shell: bash
      run: |
        if command -v bun &> /dev/null; then
          echo "bun-installed=true" >> $GITHUB_OUTPUT
        else
          echo "bun-installed=false" >> $GITHUB_OUTPUT
        fi

    - name: Install Bun (pinned)
      if: steps.check-bun.outputs.bun-installed != 'true'
      shell: bash
      env:
        BUN_INSTALL_VERSION: "bun-v1.3.12"
      run: |
        set -euo pipefail
        curl -fsSL https://bun.sh/install | bash -s "${BUN_INSTALL_VERSION}"
        echo "$HOME/.bun/bin" >> "$GITHUB_PATH"

    - name: Install JS dependencies
      shell: bash
      working-directory: ${{ inputs.working-directory }}
      run: bun install --frozen-lockfile
```

### Using the composite actions

```yaml
# ci.yml
lint-python:
  runs-on: self-hosted
  steps:
    - uses: actions/checkout@v6
    - uses: ./.github/actions/setup-python
      with:
        python-version: "3.12"
    - run: make py-check

test-python:
  runs-on: self-hosted
  strategy:
    fail-fast: false
    matrix:
      python-version: ["3.11", "3.12", "3.13"]
  steps:
    - uses: actions/checkout@v6
    - uses: ./.github/actions/setup-python
      with:
        python-version: ${{ matrix.python-version }}
    - uses: ./.github/actions/setup-node
    - run: uv run python manage.py assets build
    - run: uv run pytest src/py/tests -v
```

**Why composite actions:** `uv` and `bun` versions are pinned in **one place**. Dependency drift requires a one-line change, not a sweep across 12 jobs.

## Service containers

Only needed when your tests hit a database/Redis. Add under `services:` on the relevant job:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: app
          POSTGRES_PASSWORD: app
          POSTGRES_DB: app
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/setup-python
      - run: uv run pytest tests/ -v
        env:
          DATABASE_URL: postgresql+asyncpg://app:app@localhost:5432/app
          REDIS_URL: redis://localhost:6379/0
```

Both fullstack reference apps only put services in the **release** workflow (the CI workflow uses in-memory SQLite + no-op SAQ). accelerator doesn't use services at all — its tests start containers via `pytest-databases`, which is more portable across `self-hosted` runners.

## The "placeholder asset directory" trick

Every CI job that runs `uv sync` fails Hatchling if the asset output dir doesn't exist:

```text
ValueError: Directory not found: app/domain/web/public
```

Even for **lint/typecheck jobs** that don't care about the frontend. Fix:

```yaml
- run: mkdir -p app/domain/web/public     # or src/py/app/server/static/web
- run: uv sync --all-extras --dev
```

Or bake it into the composite action (see `setup-python/action.yml` above).

## Matrix patterns worth knowing

### Coverage from exactly one Python version

```yaml
strategy:
  matrix:
    python-version: ["3.11", "3.12", "3.13"]
steps:
  - uses: ./.github/workflows/test.yml
    with:
      coverage: ${{ matrix.python-version == '3.12' }}
```

Multiple versions uploading `coverage.xml` stomp each other in codecov.

### Per-cell OS

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-14, windows-2022]
    python-version: ["3.12", "3.13"]
runs-on: ${{ matrix.os }}
```

Useful when your app has OS-specific dependencies (oracledb, pypika).

### Expensive tests only on one cell

accelerator runs the full e2e + integration suite only on Python 3.12; 3.11 and 3.13 get unit-only for compatibility:

```yaml
- name: Run full tests (3.12 only)
  if: matrix.python-version == '3.12' && steps.disk-check.outputs.sufficient == 'true'
  timeout-minutes: 100
  run: uv run pytest src/py/tests/unit src/py/tests/integration src/py/tests/e2e -v

- name: Run unit tests (compatibility)
  if: matrix.python-version != '3.12'
  timeout-minutes: 15
  run: uv run pytest src/py/tests/unit -v
```

Pattern: heavy tests on the stable version, light tests everywhere else. Keeps CI latency reasonable as the matrix grows.

## Disk cleanup for large builds

GitHub's `ubuntu-latest` has ~30 GB free. Frontend + Python + Playwright + Docker layers blow past it. accelerator's cleanup block (run before heavy jobs):

```yaml
- name: Free additional space
  run: |
    sudo docker rmi $(docker image ls -aq) >/dev/null 2>&1 || true
    sudo rm -rf \
      /usr/share/dotnet \
      /usr/local/lib/android \
      /opt/ghc \
      /usr/local/share/powershell \
      /usr/share/swift \
      /usr/local/.ghcup \
      /usr/lib/jvm \
      /usr/local/graalvm \
      /usr/local/share/chromium \
      /usr/local/share/edge \
      /opt/hostedtoolcache/CodeQL \
      /opt/hostedtoolcache/go \
      /opt/hostedtoolcache/node \
      /opt/hostedtoolcache/Ruby \
      /imagegeneration \
      /opt/az \
      || true
    sudo apt-get autoremove -y && sudo apt-get clean -y || true
    sudo rm -rf /root/.cache /var/apt/lists/* /var/cache/apt/* /tmp/* || true
```

Recovers ~15 GB. Alternative: `jlumbroso/free-disk-space@main` if you don't mind a third-party action.

## All-checks-complete sentinel

accelerator has a merge gate that aggregates all jobs:

```yaml
all-checks-complete:
  name: All Checks Complete
  if: always()
  runs-on: self-hosted
  needs:
    - lint-python
    - typecheck-mypy
    - typecheck-pyright
    - slotscheck
    - pre-commit
    - lint-frontend
    - typecheck-frontend
    - audit-python
    - audit-javascript
    - test-python
    - test-frontend
    - build-frontend
    - smoke-test-binary
  steps:
    - name: Check all deps succeeded
      run: |
        if [[ "${{ contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled') }}" == "true" ]]; then
          echo "One or more checks failed"
          exit 1
        fi
        echo "All checks passed"
```

Configure as a **required status check** in branch protection. One box to tick, instead of 14.

## Common mistakes

| Mistake | Symptom | Fix |
| --- | --- | --- |
| `uv sync` before placeholder dir | Hatchling errors in lint/typecheck jobs | `mkdir -p <bundle_dir>` before `uv sync` |
| `uv` version floats | Reproducibility issues across runs | Pin in composite action: `UV_VERSION: "0.11.6"` |
| Coverage from every Python version | Last-writer-wins in codecov | Conditional: `coverage: ${{ matrix.python-version == '3.12' }}` |
| `fail-fast: true` on experimental matrix cells | One flaky cell kills the whole matrix | `fail-fast: false` for expensive/experimental matrices |
| No timeout-minutes | Runaway test hangs consume minutes budget | Set per-job (e.g. 30 for lint, 100 for e2e) |
| `actions/checkout@v6` without `fetch-depth` | Changelog generation fails in release | `with: fetch-depth: 0` for release jobs |

## Summary

1. Use `astral-sh/setup-uv@v7` (or `@v6` with `enable-cache: true` on older repos).
2. `uv python install <version>` to install Python — faster than `setup-python@v5`.
3. `oven-sh/setup-bun@v2` for frontend builds.
4. Always `mkdir -p <bundle_dir>` before `uv sync`.
5. Reusable workflow for matrix tests; composite actions for shared setup.
6. Services block for DB/Redis; prefer pytest-databases containers for portability.
7. Coverage from exactly one Python version.
8. Large projects: add disk cleanup + an all-checks-complete sentinel.
