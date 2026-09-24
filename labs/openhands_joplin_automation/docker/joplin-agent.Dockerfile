FROM ghcr.io/openhands/agent-server@sha256:44426bffabffa704b54a79cfeae71d0af5e702e80ef1b7276861307ecc9d598c

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cargo git gettext libasound2t64 libatk-bridge2.0-0 \
    libatk1.0-0 libcairo2-dev libcups2t64 libdbus-1-3 libdrm2 \
    libgbm1 libgtk-3-0 libnss3 libpango1.0-dev libsecret-1-dev \
    libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 \
    libxrandr2 pkg-config python3-dev rsync xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=openhands:openhands . /opt/joplin
USER openhands
WORKDIR /opt/joplin
ENV CI=1
RUN test "$(node --version)" = "v24.21.0" \
    && test "$(node .yarn/releases/yarn-4.16.0.cjs --version)" = "4.16.0" \
    && cp package.json /tmp/joplin-package.json.pinned \
    && node -e 'const fs=require("fs"); const p=JSON.parse(fs.readFileSync("package.json")); p.scripts.postinstall="true"; fs.writeFileSync("package.json", JSON.stringify(p,null,2)+"\n")' \
    && YARN_ENABLE_IMMUTABLE_INSTALLS=1 node .yarn/releases/yarn-4.16.0.cjs \
       workspaces focus root @joplin/lib @joplin/app-desktop \
    && mv /tmp/joplin-package.json.pinned package.json \
    && node .yarn/releases/yarn-4.16.0.cjs workspaces foreach -Rt --from @joplin/utils run build \
    && node .yarn/releases/yarn-4.16.0.cjs workspace @joplin/htmlpack tsc \
    && node .yarn/releases/yarn-4.16.0.cjs workspace @joplin/renderer tsc \
    && node .yarn/releases/yarn-4.16.0.cjs workspace @joplin/lib tsc \
    && node .yarn/releases/yarn-4.16.0.cjs workspace @joplin/app-desktop tsc \
    && node .yarn/releases/yarn-4.16.0.cjs workspace @joplin/app-desktop exec gulp compilePackageInfo \
    && node packages/app-desktop/node_modules/electron/install.js \
    && rm -rf .yarn/cache

WORKDIR /workspace
USER root
RUN apt-get update && apt-get install -y --no-install-recommends xauth \
    && rm -rf /var/lib/apt/lists/*
USER openhands
