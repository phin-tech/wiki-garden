# Vendored: @kenn-io/kit-ui

Source: https://github.com/kenn-io/kit-ui
Commit: d985dc46f4850fbbba5c8ec5aa39d8402fc08866
License: Apache-2.0 (see ./LICENSE)
Path vendored: upstream `src/lib` -> `./lib`

kit-ui is distributed as source (its package `svelte`/`main` export points at
`src/lib/index.ts`). We consume it by compiling those Svelte sources directly,
aliased as `@kit-ui` (see web/vite.config.ts). Do not edit files under `lib/`
by hand — re-vendor from upstream instead (scripts/update-kit-ui.sh).
