# Joplin baseline qualification

Date: 23 September 2026. Source: the user's public [Joplin fork](https://github.com/lspinheiro/joplin), checked out at `1d6beb0443e6d958b2c241f45978bd5de069f309` in ignored `.data/joplin-source`. The checkout was clean before regression work. No upstream repository write is part of this plan.

## Pinned toolchain

| Input | Source at the pinned commit | Selected value |
| --- | --- | --- |
| Joplin | Git commit | `1d6beb0443e6d958b2c241f45978bd5de069f309` |
| Node | root `package.json` `engines.node`; `devbox.json`; Agent Server base image | `>=22.19`; Devbox `24.12.0`; base image `24.21.0` |
| Yarn | root `package.json` `packageManager`; `.yarnrc.yml` `yarnPath`; tracked `.yarn/releases/yarn-4.16.0.cjs` | `4.16.0` |
| Yarn engine discrepancy | root `package.json` `engines.yarn` | `4.14.1`; the committed Yarn binary and package manager declaration take precedence for this build |
| Python | OpenHands Agent Server image, verified in the built image | `3.13.5`; controller remains uv managed |
| Agent Server | Plan 02 pinned image | `ghcr.io/openhands/agent-server@sha256:44426bffabffa704b54a79cfeae71d0af5e702e80ef1b7276861307ecc9d598c`, release `1.48.0` |

The source checkout includes `yarn.lock`. `.yarnrc.yml` selects the committed Yarn binary, enables dependency scripts, and uses `node-modules`. The root `postinstall` runs `husky && gulp build`. The build context comes from `git archive` of the pinned commit, excluding the fork's `.git` metadata and local files. CI's Linux setup (`.github/workflows/shared/setup-build-environment/action.yml`) names `libsecret-1-dev` and `xvfb`; the image also includes Electron shared libraries, native build tools, Pango/Cairo headers, and Rust tooling.

The first build used the upstream `.dockerignore`. It excluded `packages/app-desktop` and other Yarn workspaces. Yarn's immutable install then reported `YN0028` because resolving that incomplete tree would change the lockfile. The build script now replaces `.dockerignore` only inside the disposable archive context with exclusions for `.git`, `node_modules`, and Yarn cache. A second immutable resolution completed without changing the lockfile and entered the fetch step.

The second build fetched dependencies but exhausted Docker's 32 GB filesystem during Yarn's `node-modules` link step (`ENOSPC` under `packages/lib/node_modules`). The host had 31 GiB available, while the Docker VM reported 7.5 GiB free after the failure. Other projects' Docker images and volumes were retained. The two-workspace focused install completed, but image export again drove the VM to 99% with about 525 MB free. That export was stopped. Only a task-owned build cache layer was pruned afterward.

Host qualification exposed two more build inputs. Focusing `@joplin/lib` and `@joplin/app-desktop` omits root ESLint and dependencies needed by desktop startup. Focusing root plus these workspaces completes an immutable install when the root `postinstall` is temporarily changed to `true` in the disposable build context. The pinned root `postinstall` (`husky && gulp build`) failed on unrelated React Native workspaces. The image recipe restores the exact root `package.json` after installation and explicitly builds the packages used by the selected regressions. Host native modules loaded after that focused install.

The `linux/arm64` image build completed and produced a host-side Docker archive. The first import ran out of VM space while unpacking the dependency layer. Removing the completed build's task-owned cache left enough space to unpack and start the imported image. Its inspected content ID is `sha256:eb3a8f1b239ef7e2b4d6859bbc8a8f6c42fa981abc751a67f6af9670aa71e5af`. The source and image `yarn.lock` and root `package.json` hashes matched. The image reports Python 3.13.5, Node 24.21.0, and Yarn 4.16.0.

The focused Linux checks need three more generated workspace outputs. The core Jest suite initially could not parse `@joplin/fork-uslug` TypeScript. `node .yarn/releases/yarn-4.16.0.cjs workspace @joplin/fork-uslug tsc` resolved that setup failure. Electron bundling initially could not resolve `@joplin/turndown` and `@joplin/turndown-plugin-gfm` because their `lib` outputs were absent. Their pinned `build` scripts resolved that setup failure. These commands are in the trusted validation profiles before Jest and Electron. No dependency reinstall or lockfile change was needed.

The Docker host reports `arm64` and Docker 29.7.2. The base image is ARM64. No architecture emulation is planned. Tests use a disposable profile and virtual display, without host display or personal notebook mounts.

## Qualification results

The host's committed Yarn 4.16.0 binary ran the core Note suite after building `@joplin/fork-htmlparser2`, `@joplin/utils`, `@joplin/renderer`, and `@joplin/lib`. Jest's pinned config matches compiled `*.test.js`, so the focused argv ends in `models/Note.test.js`. The baseline had 2 intended assertion failures and 65 passes; a temporary correction passed 67/67. The desktop PromptDialog Jest suite had 1 intended failure and 6 passes; a temporary correction passed 7/7. The Electron test reached the actual dialog on macOS and failed at the expected close assertion. The temporary correction made the filtered Electron test pass. These corrections were restored in the ignored source checkout; the committed fixture patches contain tests only.

Inside the imported Linux image, the focused Note suite failed the two intended underscore assertions and passed 65 other tests. With a temporary correction applied only in a disposable container, the same suite passed 67/67. The PromptDialog Jest suite failed its intended cleared-input assertion and passed 6 other tests; the controlled correction passed 7/7. The Electron Playwright test ran under Xvfb with the container's capability drop and `no-new-privileges` setting. On the pinned desktop source, it failed at the expected visible-dialog assertion. The controlled correction passed the full scenario, including reopening the dialog to check persisted tag associations. Playwright captured screenshots and traces. The controlled source edits are absent from the image and test fixtures.

The image digest and toolchain are recorded in `docker/versions.json`. The build used native ARM64; no emulation, host display, personal profile, or credentials were supplied. The exact red and green commands are the Jest and Playwright argv in `validation/profiles.json`, after their listed dependency builds.

The production combined validation profile passed all 12 commands against a temporary corrective candidate based directly on the approved source SHA. The validator applied the trusted regression patches in a disposable clone, copied only the candidate and test changes into a credential-free container, and wrote command logs under ignored `.data/validation-evidence/`. The local red and green Electron traces are under ignored `.data/linux-red-test-results/` and `.data/linux-green-test-results/`.
