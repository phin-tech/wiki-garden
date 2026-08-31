# web — the `garden tend` UI

The local web UI opened by `garden tend`. Vite + Svelte 5, consuming a **vendored**
copy of [`@kenn-io/kit-ui`](https://github.com/kenn-io/kit-ui) (Apache-2.0) under
`vendor/kit-ui/` (see `vendor/kit-ui/VENDORED.md` for the pinned commit).

## Why the build output is committed

End users install Wiki Garden as a Claude Code skill (`npx skills add …`), which
copies **only** `skills/wiki-garden/`. So the compiled UI is built **into**
`skills/wiki-garden/wiki_garden/web-dist/` and committed — `garden tend` serves it with a
stdlib HTTP server, and users need no JS toolchain. This `web/` tree is for
contributors only and is not shipped.

## Build

```sh
cd web
bun install
bun run build        # -> ../skills/wiki-garden/wiki_garden/web-dist   (commit the result)
```

`base` is `./` (relative) because the server mounts the assets at an arbitrary
path; `outDir` points into the skill. Always commit the regenerated `web-dist/`
alongside your source change.

## Dev

```sh
garden tend --no-open          # run the API server (port 8787) in one shell
cd web && bun run dev          # Vite dev server; proxies /api -> 127.0.0.1:8787
```

## Backend

The server + JSON API live in `skills/wiki-garden/wiki_garden/_web.py` (stdlib only),
wired as the `garden tend` subcommand. Read endpoints parse the store directly;
`accept`/`reject` call the in-process gate functions in `_skills` / `_tools`, so
gating logic stays single-sourced with the CLI.

## Re-vendoring kit-ui

Re-copy upstream `src/lib` into `vendor/kit-ui/lib` and update the commit hash in
`vendor/kit-ui/VENDORED.md`. Don't hand-edit files under `vendor/`.
