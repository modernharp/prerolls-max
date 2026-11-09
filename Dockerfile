# syntax=docker/dockerfile:1

# Prerolls Max. Builds everything from this folder, nothing prebuilt needed:
#   docker build -t prerollsmax .
# The release workflow (.github/workflows/docker.yml) adds the build info:
#   --build-arg PMAX_REPOSITORY=owner/repo --build-arg VERSION=1.2.3 ...
#
# Behind a proxy that re-signs HTTPS (a corporate proxy, a sandbox), pass its CA
# bundle as a BuildKit secret; it is used by the build stages only and never
# ends up in the image:
#   docker build --secret id=build_ca,src=/path/ca-bundle.crt \
#     --build-arg HTTPS_PROXY=... --build-arg HTTP_PROXY=... --network host .
# Without the secret every step below behaves exactly as a normal build.

# Deno for yt-dlp's YouTube extraction, from Deno's official binary image.
# Pinned like BGUTIL_VERSION below; bump it when yt-dlp needs a newer Deno.
ARG DENO_VERSION=2.9.7

# --- Deno binary (copied into the runtime stage) ---
FROM denoland/deno:bin-${DENO_VERSION} AS deno

# --- Web interface build stage ---
# The interface is plain files, so it is built once on the build machine for
# every target platform (no emulation).
FROM --platform=$BUILDPLATFORM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=bind,source=docker/build-ca.sh,target=/tmp/build-ca.sh \
    --mount=type=secret,id=build_ca,required=false,mode=0444 \
    . /tmp/build-ca.sh && \
    npm ci --no-audit --no-fund && \
    build_ca_done
COPY frontend/ ./
RUN npm run build && test -f dist/index.html

# --- Build stage: compile Python wheels with native deps ---
FROM python:3.12-slim AS builder

RUN --mount=type=bind,source=docker/build-ca.sh,target=/tmp/build-ca.sh \
    --mount=type=secret,id=build_ca,required=false,mode=0444 \
    . /tmp/build-ca.sh && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        rustc \
        cargo \
        pkg-config && \
    rm -rf /var/lib/apt/lists/* && \
    build_ca_done

WORKDIR /build
COPY requirements.txt .
RUN --mount=type=bind,source=docker/build-ca.sh,target=/tmp/build-ca.sh \
    --mount=type=secret,id=build_ca,required=false,mode=0444 \
    . /tmp/build-ca.sh && \
    pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt && \
    build_ca_done

# --- PO-token provider build stage (bgutil) ---
# Builds the YouTube Proof-of-Origin token server. This is what gets NeX-Up past
# YouTube's "Sign in to confirm you're not a bot" wall. node:22 + bookworm keeps
# it glibc-compatible with the python:3.12-slim runtime so we can copy node and
# the (native-canvas) node_modules across stages. node:22 (>=22.12) is required
# because the provider's jsdom stack pulls an ESM-only @exodus/bytes that is
# loaded via require(); on Node <22.12 that crashes the server at startup with
# ERR_REQUIRE_ESM. Keep BGUTIL_VERSION in sync with the bgutil-ytdlp-pot-provider
# pin in requirements.txt and PROVIDER_VERSION in backend/nexup_potoken.py.
# 2.0.0 fixes a remote code execution hole (GHSA-qpv9-8xfj-xx9m) in servers
# listening on every interface, which 1.x did by default.
FROM node:22-bookworm-slim AS potoken
ARG BGUTIL_VERSION=2.0.0
# ca-certificates is required for the HTTPS git clone below (the slim node image
# ships without it, so the clone fails with "server certificate verification
# failed"). git pulls the provider; the rest are a fallback toolchain in case
# node-canvas has no prebuilt binary for this arch and builds from source.
RUN --mount=type=bind,source=docker/build-ca.sh,target=/tmp/build-ca.sh \
    --mount=type=secret,id=build_ca,required=false,mode=0444 \
    . /tmp/build-ca.sh && \
    apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git python3 build-essential pkg-config \
        libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev librsvg2-dev && \
    rm -rf /var/lib/apt/lists/* && \
    build_ca_done
# Install from the provider's lockfile, build, then keep only what runs: the
# compiler, linters and their dependencies are build tools, and shipping them
# put packages such as js-yaml, brace-expansion and flatted in the image's
# vulnerability report. `npm audit fix` applies patched releases of runtime
# dependencies that fit the provider's version ranges; it never changes a
# major version, and a registry outage does not fail the build.
# basic-ftp is the exception: proxy-agent > pac-proxy-agent > get-uri pins
# ^5.3.1, and its directory-listing DoS (CVE-2026-102990) is fixed only in
# 6.2.1. get-uri uses the same Client calls in 6.x, and the provider only
# reaches FTP for an ftp:// proxy auto-config URL, so the override is safe.
RUN --mount=type=bind,source=docker/build-ca.sh,target=/tmp/build-ca.sh \
    --mount=type=secret,id=build_ca,required=false,mode=0444 \
    . /tmp/build-ca.sh && \
    git clone --depth 1 --branch ${BGUTIL_VERSION} \
        https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/bgutil-provider && \
    cd /opt/bgutil-provider/server && \
    npm ci --no-audit --no-fund && \
    npx tsc && \
    npm pkg set 'overrides.basic-ftp=^6.2.1' && \
    npm install --no-audit --no-fund && \
    (npm audit fix --omit=dev --no-fund || true) && \
    npm prune --omit=dev --no-audit --no-fund && \
    test -f build/main.js && \
    build_ca_done

# --- Plugin build stage ---
# Builds the Prerolls Max Intros plugins (Jellyfin 10.11 and 12, Emby) with
# plugins/build.sh, so the running container can hand them out from the
# Connect page (/jellyfin/plugin/download, /emby/plugin/download) and they
# always match this build. Only the .NET 10 SDK and nuget.org are needed:
# Emby's server libraries come from its NuGet packages.
# The plugins are .NET assemblies that run anywhere, so they too are built
# natively on the build machine: .NET under QEMU emulation is slow and flaky.
FROM --platform=$BUILDPLATFORM mcr.microsoft.com/dotnet/sdk:10.0 AS pluginbuild
WORKDIR /src/plugins
COPY plugins/ ./
RUN --mount=type=bind,source=docker/build-ca.sh,target=/tmp/build-ca.sh \
    --mount=type=secret,id=build_ca,required=false,mode=0444 \
    . /tmp/build-ca.sh && \
    apt-get update && apt-get install -y --no-install-recommends zip && \
    rm -rf /var/lib/apt/lists/* && \
    bash build.sh && \
    mkdir -p /out && cp out/*.zip out/PrerollsMax.Emby.dll /out/ && \
    build_ca_done

# --- Runtime stage: slim image without build tools ---
FROM python:3.12-slim

ARG VERSION=dev
# The GitHub repository that builds and publishes this image ("owner/repo",
# GITHUB_REPOSITORY in the workflows). It goes into build_info.json, which
# sets the update check and project link, and into the labels GHCR uses to
# link the package to its repository. Empty for a local build: updates off.
ARG PMAX_REPOSITORY=""
ARG PMAX_COMMIT=""
ARG PMAX_IMAGE=""
LABEL org.opencontainers.image.title="Prerolls Max" \
      org.opencontainers.image.description="Prerolls Max: intro videos (prerolls) for Plex, Jellyfin and Emby. Replaces NeXroll." \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="PolyForm-Noncommercial-1.0.0" \
      org.opencontainers.image.revision="${PMAX_COMMIT}" \
      org.opencontainers.image.source="${PMAX_REPOSITORY:+https://github.com/}${PMAX_REPOSITORY}" \
      org.opencontainers.image.url="${PMAX_REPOSITORY:+https://github.com/}${PMAX_REPOSITORY}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PMAX_PORT=9393 \
    PMAX_DB_DIR=/data \
    PMAX_PREROLL_PATH=/data/prerolls \
    PMAX_SECRETS_DIR=/data \
    PMAX_RUN_AS_PUID=true \
    PUID=1000 \
    PGID=1000 \
    PLEX_URL="" \
    JELLYFIN_URL="" \
    RADARR_URL="" \
    SONARR_URL="" \
    TZ=UTC

RUN --mount=type=bind,source=docker/build-ca.sh,target=/tmp/build-ca.sh \
    --mount=type=secret,id=build_ca,required=false,mode=0444 \
    . /tmp/build-ca.sh && \
    apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        unzip \
        tzdata \
        # DejaVu + Liberation fonts so FFmpeg drawtext can render extended-Latin
        # glyphs (German umlauts ä/ö/ü, accents, etc.) in generated prerolls /
        # Coming Soon lists. Without a real fontfile, drawtext falls back to a
        # built-in font with poor coverage and umlauts render as garbage.
        fonts-dejavu-core \
        fonts-liberation && \
    # Remove ncurses binaries (CVE-2025-69720) — not used by Prerolls Max
    { dpkg --remove --force-depends ncurses-base ncurses-bin 2>/dev/null || true; } && \
    rm -rf /var/lib/apt/lists/* && \
    build_ca_done

# Deno (required for yt-dlp YouTube extraction), from the deno stage. It used
# to come from piping deno.land's install script into sh: unpinned, and
# nothing checked what it downloaded.
COPY --from=deno /deno /usr/local/bin/deno

# YouTube PO-token provider: copy the Node runtime + the prebuilt bgutil server
# from the potoken stage, and install the shared libs its native `canvas`
# dependency links against. The backend (backend/nexup_potoken.py) launches
# `node build/main.js` from PMAX_BGUTIL_DIR so yt-dlp can mint PO tokens.
COPY --from=potoken /usr/local/bin/node /usr/local/bin/node
COPY --from=potoken /opt/bgutil-provider/server /opt/bgutil-provider/server
RUN --mount=type=bind,source=docker/build-ca.sh,target=/tmp/build-ca.sh \
    --mount=type=secret,id=build_ca,required=false,mode=0444 \
    . /tmp/build-ca.sh && \
    apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libjpeg62-turbo \
        libgif7 librsvg2-2 libpixman-1-0 libfontconfig1 && \
    rm -rf /var/lib/apt/lists/* && \
    build_ca_done
ENV PMAX_BGUTIL_DIR=/opt/bgutil-provider/server

WORKDIR /app/server

# Install pre-built Python wheels (no compiler needed).
# The wheels are bind-mounted from the builder stage rather than COPYed in. A
# COPY commits them to their own layer, and the `rm -rf` that used to follow
# could only write a whiteout on top of it -- a layer that is already committed
# cannot be removed by a later one, so the wheels shipped in every pull. A bind
# mount is never committed to a layer, so there is nothing left to remove.
COPY requirements.txt /app/server/requirements.txt
#
# pip is removed afterwards. It is only needed to install, and it carries its
# own copies of setuptools and msgpack (listed in pip/_vendor/vendor.txt), which
# image scanners report as installed packages; even the newest pip vendors a
# setuptools with open advisories. Nothing at runtime uses it: the in-app
# yt-dlp upgrade refuses to run in Docker. ensurepip's bundled pip wheel goes
# with it for the same reason.
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels -r /app/server/requirements.txt && \
    python -m pip uninstall -y pip && \
    rm -rf /usr/local/lib/python3.12/ensurepip/_bundled /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12

# Fail the build if a broken/partial yt-dlp wheel is ever resolved — this is
# the exact failure shape that caused a day-long outage in the field
# (AttributeError: module 'yt_dlp' has no attribute 'utils'/'version').
RUN python -c "import yt_dlp; assert yt_dlp.version.__version__; assert yt_dlp.utils; print(f'yt-dlp OK: {yt_dlp.version.__version__}')"

# Copy backend
COPY app/backend /app/server/backend


# Copy CHANGELOG
COPY app/CHANGELOG.md /app/server/CHANGELOG.md

# Copy audio assets for Coming Soon generator

# Typefaces the Preroll Generator offers. The image only carries DejaVu and
# Liberation otherwise, so without these the font picker is nearly empty in
# Docker while a Windows install shows a dozen. SIL OFL 1.1; see
# assets/fonts/licenses/.
COPY assets/fonts /app/assets/fonts

# The web interface, from the frontend stage.
COPY --from=frontend /src/frontend/dist /app/server/frontend/build

# build_info.json: where update checks look and the project link (see
# app/backend/build_info.py). Written from the build args above.
COPY app/version.py /app/server/version.py
COPY scripts/write_build_info.py /tmp/write_build_info.py
RUN python /tmp/write_build_info.py --out /app/server/build_info.json \
        --version-file /app/server/version.py \
        --repository "${PMAX_REPOSITORY}" --commit "${PMAX_COMMIT}" --image "${PMAX_IMAGE}" && \
    rm /tmp/write_build_info.py

# Prerolls Max Intros plugins (Jellyfin 10.11 and 12 zips, the Emby DLL),
# served for download from the Connect page.
COPY --from=pluginbuild /out/ /app/plugins/

# Prepare persistent data volume
RUN mkdir -p /data /data/prerolls

VOLUME ["/data"]

EXPOSE 9393

# Healthcheck: FastAPI health endpoint
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS http://localhost:${PMAX_PORT:-9393}/health || exit 1

# Runs Prerolls Max as PUID:PGID (1000:1000 unless set), not root. Set
# PMAX_RUN_AS_PUID=false to run as root (see the script).
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Start Uvicorn. exec, so uvicorn gets Docker's stop signal itself instead of a
# shell that doesn't pass it on (the stop used to wait out its 10 s timeout).
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PMAX_PORT:-9393}"]
