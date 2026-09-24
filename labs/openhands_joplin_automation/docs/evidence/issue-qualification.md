# Joplin issue qualification

Captured: 23 September 2026 at 10:25:42 UTC. Target checkout: the user's [Joplin fork](https://github.com/lspinheiro/joplin) at `1d6beb0443e6d958b2c241f45978bd5de069f309`. The regression inputs contain public behaviour descriptions and tests. They omit reporter device identifiers, sync targets, and proposed solution patches.

## Issue status at capture

| Issue | Public report | State and development status |
| --- | --- | --- |
| Core [#16638](https://github.com/laurent22/joplin/issues/16638) | A generated note title loses matched underscores from date-like first lines. | Open, unassigned, labelled `bug` and `high`; no linked PR in the issue API. A maintainer attributed the behaviour to Markdown underscore filtering and suggested matching only token boundaries. |
| Desktop [#16261](https://github.com/laurent22/joplin/issues/16261) | Erasing an existing tag prefix then pressing Enter adds the suggested tag. | Open, unassigned, labelled `bug` and `stale`. The timeline links a [closed third-party fork PR](https://github.com/osgroupw/joplin-osgroupw/pull/9). The report came from Windows 3.7.12 with Rich Text editing, so Linux reproduction is required before acceptance. |

## Baseline source trace

`packages/lib/models/Note.ts` delegates `defaultTitleFromBody` to `markdownUtils.titleFromBody` in `packages/lib/markdownUtils.ts`. The latter applies Markdown formatting regexes to the first non-empty line; the `_..._` pattern can span the underscores in `YYYY_MM_` and `YYYY_MM_DD`. The controller-owned patch adds assertions to the existing `packages/lib/models/Note.test.ts` suite for the reported shape and established formatting behaviour.

`packages/app-desktop/gui/WindowCommandsAndDialogs/commands/setTags.ts` opens a `PromptDialog` with `inputType: 'tags'`. The command saves the dialog answer through `Tag.setNoteTagsByTitles`. `packages/app-desktop/gui/PromptDialog.tsx` uses `CreatableSelect`, and its Enter handler leaves an open suggestion menu to react-select. The desktop regression must test the rendered interaction and reopen the dialog to check persisted tag associations.

## Reproduction evidence

The pinned Linux image was built and inspected as `sha256:eb3a8f1b239ef7e2b4d6859bbc8a8f6c42fa981abc751a67f6af9670aa71e5af`. Docker Desktop's 32 GB VM initially ran out of space during export and import. Reclaiming only this lab's build cache allowed the imported image to unpack. Its lockfile and root package hashes match the approved source.

On the macOS ARM64 host, the committed Yarn 4.16.0 binary and pinned source produced the expected core failure: `YYYY_MM_` became `YYYYMM`, and `YYYY_MM_DD` became `YYYYMMDD`; 65 other Note tests passed. A temporary correction in the ignored source checkout made all 67 Note tests pass. The correction was restored, and the baseline red result was repeated after recompilation. The final core command is `node .yarn/releases/yarn-4.16.0.cjs workspace @joplin/lib test --runInBand --runTestsByPath models/Note.test.js` after compiling its dependencies and library. The pinned Jest config only matches compiled `*.test.js`.

The rendered `PromptDialog` Jest regression failed at the intended Enter assertion on the pinned source; 6 other tests passed. A temporary correction made all 7 pass. Joplin's filtered Electron Playwright test then reached the real tag dialog in a disposable macOS profile. With the baseline source, the dialog stayed visible after repeated Backspace cleared the suggested tag prefix and Enter was pressed. The same temporary correction made the Electron test pass. The Playwright spec attaches before/after screenshots and records a trace on every run. It reopens the dialog and checks for selected tag chips, so a merely hidden dialog is insufficient. The correction was restored and is absent from the controller-owned regression inputs.

Linux ARM64 reproduced the same intended failures. The core Note Jest suite failed 2 new assertions with 65 passes; its controlled correction passed 67/67. The final desktop PromptDialog Jest suite failed 1 new assertion with 7 passes; its correction passed 8/8. The passing cases include keyboard and mouse selection of an existing tag. Electron Playwright under Xvfb reached the real tag dialog and failed because it remained visible after clearing the prefix and pressing Enter. The controlled correction passed the full scenario, including the persisted association check after reopening. Temporary corrections were applied only in a disposable container. The regression patches remain tests only. The exact prerequisite build commands appear in `validation/profiles.json`.

The production `CandidateValidator` then ran the `combined` profile against a temporary corrective commit whose parent is the approved baseline. It applied both controller-owned regression patches in a clean clone and passed all 12 trusted commands: dependency builds, TypeScript, `linter-ci`, both Jest suites, and Electron Playwright. The evidence record binds candidate `10bac775df70c103d64860246c778d3be3bb08d5` to the image digest above. The temporary commit and its evidence remain under ignored `.data/`; they are not agent inputs or part of this course branch. `validation/profiles.json` is marked `linux-qualified`.
