# GitHub Actions — Release

Release pipelines that produce wheels, multi-platform PyApp onefiles, multi-arch container images, and a GitHub release — all from a single `v*` tag push.

## Two topologies

| Project | Targets | Flavor |
| --- | --- | --- |
| litestar-fullstack-inertia | 4 platforms (Linux x86_64/arm64, macOS x86_64/arm64) | Simple PyApp via `hatch build --target binary` |
| accelerator (DMA) | 2 Linux platforms (x86_64, arm64) + 2 distroless container images | Advanced: custom bundler, `cargo zigbuild`, offline onefiles |

## Shape of a release

```text
v1.2.3 tag push
   │
   ├──▶ validate      (tag format)
   │
   ├──▶ lint          (required gate)
   ├──▶ docs          (required gate)
   │
   ├──▶ build-wheel   (one wheel, uploaded as artifact)
   │      │
   │      └────────────┐
   │                   ▼
   ├──▶ build-onefiles (matrix: linux-x86_64, linux-arm64, macos-..., windows-...)
   │      │            (each downloads the wheel artifact)
   │      │            (each uploads app-<target> binary)
   │      │
   │      └────────────┐
   │                   ▼
   ├──▶ build-images  (downloads onefiles, wraps in distroless Docker, uploads .tar)
   │
   └──▶ publish       (downloads all artifacts, creates GitHub release, uploads)
```

Each stage `needs:` the prior one. Failures short-circuit the pipeline; a partial release never reaches `gh release create`.

## Simple (inertia) — full workflow

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Validate tag format
        run: |
          TAG="${GITHUB_REF#refs/tags/}"
          if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "Invalid tag: $TAG (expected vX.Y.Z)"
            exit 1
          fi

  test:
    runs-on: ubuntu-latest
    needs: validate
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
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.12
      - run: mkdir -p app/domain/web/public
      - run: uv sync --all-extras --dev
      - run: uv run pytest tests -v
        env:
          DATABASE_URL: postgresql+asyncpg://app:app@localhost:5432/app

  build-wheel:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v6
      - uses: oven-sh/setup-bun@v2
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.12
      - run: uv sync --all-extras --dev
      - run: uv run app assets install
      - run: uv run app assets build
      - run: uv build --wheel
      - name: Verify wheel contents
        run: |
          unzip -l dist/*.whl | grep -qE '\.(js|css|html)$' || (echo "Missing frontend" && exit 1)
      - uses: actions/upload-artifact@v6
        with:
          name: wheel
          path: dist/*.whl
          if-no-files-found: error

  build-binary:
    needs: build-wheel
    strategy:
      fail-fast: false
      matrix:
        include:
          - target: x86_64-unknown-linux-gnu
            runner: ubuntu-latest
          - target: aarch64-unknown-linux-gnu
            runner: ubuntu-24.04-arm
          - target: x86_64-apple-darwin
            runner: macos-13
          - target: aarch64-apple-darwin
            runner: macos-14
    runs-on: ${{ matrix.runner }}
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.12
      - uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}
      - uses: actions/download-artifact@v7
        with:
          name: wheel
          path: dist/
      - run: mkdir -p app/domain/web/public
      - run: uv sync --all-extras --dev
      - run: uv run hatch build --target binary
      - name: Rename and chmod
        run: |
          mv dist/binary/app dist/binary/app-${{ matrix.target }}
          chmod +x dist/binary/app-${{ matrix.target }}
      - uses: actions/upload-artifact@v6
        with:
          name: binary-${{ matrix.target }}
          path: dist/binary/app-${{ matrix.target }}

  publish:
    needs: [build-wheel, build-binary]
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - uses: actions/download-artifact@v7
        with:
          path: release-files/
          merge-multiple: true
      - name: Create Release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          TAG="${GITHUB_REF#refs/tags/}"
          gh release create "$TAG" \
            --title "App $TAG" \
            --generate-notes \
            release-files/*
```

## Advanced (accelerator) — key differences

### Target-specific onefile job

```yaml
build-onefiles:
  needs: [lint, docs]
  strategy:
    fail-fast: false
    matrix:
      job:
        - target: x86_64-unknown-linux-gnu
          os: self-hosted
          artifact: dma-x86_64-linux-gnu
        - target: aarch64-unknown-linux-gnu
          os: self-hosted
          artifact: dma-aarch64-linux-gnu
  runs-on: ${{ matrix.job.os }}
  env:
    PYAPP_REPO: pyapp
    PYAPP_VERSION: v0.29.0
    PYAPP_PYTHON_VERSION: "3.13"
    PYAPP_PROJECT_NAME: "dma"
    PYAPP_FULL_ISOLATION: "true"
    PYAPP_PROJECT_FEATURES: "cloudrun"
    BZIP2_SYS_STATIC: "1"
    LZMA_API_STATIC: "1"
  steps:
    - uses: actions/checkout@v6
    - uses: ./.github/actions/setup-python
      with:
        python-version: "${{ env.STABLE_PYTHON_VERSION }}"
    - uses: ./.github/actions/setup-node

    - name: Clone PyApp at pinned version
      run: git clone --depth 1 --branch ${{ env.PYAPP_VERSION }} https://github.com/ofek/pyapp ${{ env.PYAPP_REPO }}

    - name: Patch PyApp Cargo.toml for static libs
      working-directory: ${{ env.PYAPP_REPO }}
      run: |
        sed -i 's/bzip2 = "\([^"]*\)"/bzip2 = { version = "\1", features = ["static"] }/' Cargo.toml
        sed -i '/\[dependencies\]/a bzip2-sys = { version = "*", features = ["static"] }' Cargo.toml

    - name: Install Zig + cargo-zigbuild
      run: |
        ZIG_VERSION="0.15.2"
        ZIG_INSTALL_DIR="$HOME/.local/zig"
        mkdir -p "$ZIG_INSTALL_DIR"
        ARCH=$(uname -m)
        ZIG_ARCH=$([ "$ARCH" = "aarch64" ] && echo "aarch64" || echo "x86_64")
        curl -fsSL "https://ziglang.org/download/${ZIG_VERSION}/zig-${ZIG_ARCH}-linux-${ZIG_VERSION}.tar.xz" \
          | tar -xJ --strip-components=1 -C "$ZIG_INSTALL_DIR"
        echo "$ZIG_INSTALL_DIR" >> $GITHUB_PATH
        uv tool install cargo-zigbuild

    - uses: dtolnay/rust-toolchain@stable
      with:
        targets: ${{ matrix.job.target }}

    - name: Build wheel
      run: make build-wheel

    - name: Export requirements.txt
      run: |
        uv export --frozen --no-dev --no-editable --no-hashes --no-header --no-emit-project --extra cloudrun > dist/requirements.txt
        VERSION=$(uv run python -c "from dma.__metadata__ import __version__; print(__version__)")
        echo "$(realpath dist/dma-${VERSION}-py3-none-any.whl)" >> dist/requirements.txt
        echo "VERSION=${VERSION}" >> $GITHUB_OUTPUT
      id: version

    - name: Bundle Python + deps (and patch PyApp for install dir)
      run: |
        uv run tools/bundler.py build \
          --target ${{ matrix.job.target }} \
          --requirements dist/requirements.txt \
          --output dist/python-dist-${{ matrix.job.target }}.tar.gz \
          --pyapp-dir ${{ env.PYAPP_REPO }} \
          --install-root "~/.dma" \
          --project-name "runtime"

    - name: Build PyApp onefile (Linux GNU, glibc 2.17 baseline)
      if: contains(matrix.job.target, 'linux-gnu')
      working-directory: ${{ env.PYAPP_REPO }}
      env:
        PYAPP_PROJECT_PATH: ${{ github.workspace }}/dist/dma-${{ steps.version.outputs.VERSION }}-py3-none-any.whl
        PYAPP_DISTRIBUTION_PATH: ${{ github.workspace }}/dist/python-dist-${{ matrix.job.target }}.tar.gz
        PYAPP_DISTRIBUTION_EMBED: "true"
        PYAPP_DISTRIBUTION_PYTHON_PATH: python/bin/python3
        PYAPP_SKIP_INSTALL: "true"
        PYAPP_ALLOW_UPDATES: "true"
      run: cargo zigbuild --release --target ${{ matrix.job.target }}.2.17

    - name: Rename binary
      run: |
        cp ${{ env.PYAPP_REPO }}/target/${{ matrix.job.target }}.2.17/release/pyapp dist/${{ matrix.job.artifact }}
        chmod +x dist/${{ matrix.job.artifact }}

    - name: Offline smoke test (network-isolated)
      if: contains(matrix.job.target, 'x86_64-unknown-linux-gnu')
      run: |
        docker run --rm --network=none \
          -v $PWD/dist/${{ matrix.job.artifact }}:/app:ro \
          gcr.io/distroless/cc-debian12:nonroot /app --help

    - uses: actions/upload-artifact@v3
      with:
        name: ${{ matrix.job.artifact }}
        path: dist/${{ matrix.job.artifact }}
        if-no-files-found: error
```

### Container image packaging

```yaml
build-images:
  needs: build-onefiles
  runs-on: self-hosted
  steps:
    - uses: actions/checkout@v6
    - uses: actions/download-artifact@v3
      with:
        path: artifacts

    - name: Prepare dist directory
      run: |
        mkdir -p dist
        cp artifacts/dma-x86_64-linux-gnu/dma-x86_64-linux-gnu  dist/dma-amd64-linux-gnu
        cp artifacts/dma-aarch64-linux-gnu/dma-aarch64-linux-gnu dist/dma-arm64-linux-gnu
        chmod +x dist/dma-amd64-linux-gnu dist/dma-arm64-linux-gnu

    - uses: docker/setup-qemu-action@v4
    - uses: docker/setup-buildx-action@v4

    - name: Build AMD64 image
      uses: docker/build-push-action@v7
      with:
        context: .
        file: tools/deploy/docker/run/Dockerfile.canonical
        platforms: linux/amd64
        load: true
        tags: dma:latest-amd64

    - name: Smoketest AMD64 image
      run: |
        docker run --rm dma:latest-amd64 --help
        docker run --rm dma:latest-amd64 manage --help

    - name: Export AMD64 image tar
      run: docker save dma:latest-amd64 -o dist/dma-image-amd64.tar

    - name: Build & export ARM64 image
      uses: docker/build-push-action@v7
      with:
        context: .
        file: tools/deploy/docker/run/Dockerfile.canonical
        platforms: linux/arm64
        outputs: type=docker,dest=dist/dma-image-arm64.tar
        tags: dma:latest-arm64

    - uses: actions/upload-artifact@v3
      with:
        name: container-images
        path: dist/dma-image-*.tar
```

### Publish job (with changelog generation)

```yaml
publish:
  needs: [build-wheel, build-onefiles, build-images]
  runs-on: self-hosted
  permissions:
    contents: write
  steps:
    - uses: actions/checkout@v6
      with:
        fetch-depth: 0      # required for `git log <prev-tag>..<tag>`

    - uses: actions/download-artifact@v3
      with:
        path: dist

    - uses: ./.github/actions/setup-python
      with:
        python-version: "${{ env.STABLE_PYTHON_VERSION }}"

    - name: Build deploy kit
      run: make build-deploy-kit

    - name: Generate changelog
      run: |
        TAG="${GITHUB_REF#refs/tags/}"
        PREV_TAG=$(git describe --tags --abbrev=0 ${TAG}^ 2>/dev/null || echo "")
        if [ -n "$PREV_TAG" ]; then
          echo "## Changes since $PREV_TAG" > CHANGELOG.md
          git log ${PREV_TAG}..${TAG} --pretty=format:"- %s (%h)" >> CHANGELOG.md
        else
          echo "## Initial Release" > CHANGELOG.md
        fi

    - name: Upload to GitHub release
      env:
        GH_TOKEN: ${{ github.token }}
      run: |
        TAG="${GITHUB_REF#refs/tags/}"
        # Flatten artifact subdirs
        mkdir -p dist_flat
        find dist -type f -exec mv {} dist_flat/ \;
        rm -rf dist
        mv dist_flat dist
        gh release create "$TAG" --repo "$GITHUB_REPOSITORY" --notes-file CHANGELOG.md dist/* \
          || gh release upload "$TAG" --repo "$GITHUB_REPOSITORY" dist/* --clobber
```

## Tag validation patterns

### Strict semver

```bash
[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]
```

### Semver + pre-release (accelerator)

```bash
[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(([ab]|rc)[0-9]+)?$ ]]
```

Accepts `v1.2.3`, `v1.2.3a1`, `v1.2.3b2`, `v1.2.3rc1`.

## Concurrency: don't cancel releases

CI jobs cancel on re-push; release jobs must not:

```yaml
concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false    # ← key for releases
```

For CI, use `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}` — cancel on PRs, don't cancel on main.

## Release assets checklist

| Asset | Purpose |
| --- | --- |
| `app-X.Y.Z-py3-none-any.whl` | For PyPI upload / container image / hatch-binary rebuild |
| `app-x86_64-unknown-linux-gnu` | Onefile for x86_64 Linux (glibc 2.17+) |
| `app-aarch64-unknown-linux-gnu` | Onefile for ARM64 Linux (glibc 2.17+) |
| `app-x86_64-apple-darwin` | Onefile for Intel macOS |
| `app-aarch64-apple-darwin` | Onefile for Apple Silicon macOS |
| `app-image-amd64.tar` | `docker load`-able image for AMD64 |
| `app-image-arm64.tar` | `docker load`-able image for ARM64 |
| `app-deploy-kit-vX.Y.Z.zip` | Shell-script installer for downstream infra |

Minimum recipe for most projects: wheel + 2 Linux onefiles. Add macOS/Windows when a user asks.

## Common mistakes

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Missing `fetch-depth: 0` | `git log <prev>..` fails in changelog step | `with: fetch-depth: 0` on checkout |
| `cancel-in-progress: true` on release | Interrupted releases corrupt artifacts | Use `false` for release concurrency |
| Building wheel per-matrix-cell | Multiple non-identical wheels uploaded | Separate `build-wheel` job, download via artifact |
| `--generate-notes` without manual changelog | Release notes missing the assets/deploy-kit section | Write CHANGELOG.md then pass `--notes-file CHANGELOG.md` |
| Forgetting `if-no-files-found: error` | Silent empty release | Always set on upload-artifact in release workflows |
| Building binary before tests pass | Broken code in release | `needs: [test, build-wheel]` chain |

## Summary

1. `on: push: tags: ['v*']` + tag-format validation.
2. Gate: lint + test + docs must pass.
3. One wheel, uploaded as an artifact; all onefile jobs download it.
4. Matrix onefile jobs per target (Rust target + runner OS).
5. For Linux, use `cargo-zigbuild --target X.2.17` for glibc 2.17 compatibility.
6. Publish job downloads everything, generates changelog, `gh release create`.
7. `concurrency.cancel-in-progress: false` on release workflows.
