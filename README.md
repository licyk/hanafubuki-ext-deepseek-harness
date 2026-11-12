# DeepSeek Harness for Hanafubuki

A [Hanafubuki](https://github.com/licyk/Hanafubuki) extension that installs
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (`dsh`,
the npm package `@deepseek-ai/dsh`) on a Node.js of its own (or one of
yours), isolated from your npm configuration and your `~/.dsh`, runs its web
UI and opens it in Hanafubuki's embedded browser, and switches its npm
versions.

Id `io.github.licyk.deepseek-harness`; it adds the instance type
`io.github.licyk.deepseek-harness:dsh`.

## What it does

- **Install**: an instance has two components, `core` (the npm prefix dsh is
  installed into) and `node` (Node.js). The backend reads where they are
  from the component map Hanafubuki gives each call. It resolves
  `nodeVersion` to a release for this platform and architecture from
  nodejs.org's `index.json` and its archive's SHA-256 from that release's
  `SHASUMS256.txt`; the host downloads and checks it into `node` (`strip = 1`
  drops the archive's top directory; `replace = true` unpacks it beside the
  old one and swaps it in whole, so a failed download keeps the working
  Node.js). The plan then writes `core/.npmrc` (the *npm registry*
  setting) and runs Node's own npm:
  `npm install --prefix <core> --no-fund --no-audit @deepseek-ai/dsh@<version>`.
  The last step writes `core/hanafubuki-install.txt` (the values used and
  the exact Node.js release installed).
- **Parameters**: `version` (`latest` by default; a dist-tag such as `next`
  or `alpha`, or an exact version), `nodeVersion` (`24` by default; a major,
  `lts`, `latest`, or an exact version such as `24.9.1`; dsh needs Node.js
  24.9.0 or later) and `home` (`instance` by default, or `user`;
  [Isolation](#isolation)).
- **Update**: runs npm again with the instance's (possibly replaced) values.
  `nodeVersion` is resolved again, and Node.js is downloaded only when it
  names another release than the one recorded: an update of `24` picks up a
  newer 24.x. Offline, an update whose `nodeVersion` did not change keeps
  the Node.js it has. A discovered global prefix is updated with its own npm
  only ([Discovery](#discovery)).
- **Your own Node.js**: in the instance's **Paths**, `node` may be an
  existing Node.js (pick its `bin/node`, or `node.exe` on Windows). It is
  then external: no plan downloads into it, and deleting or reinstalling
  the instance leaves it. Its `node --version` must be 24.9.0 or later and
  its npm must be where a Node.js release keeps it
  (`lib/node_modules/npm/bin/npm-cli.js`, `node_modules\npm\bin\npm-cli.js`
  on Windows); an install, an update or a change of values is refused
  otherwise, with why.
- **musl Linux** (Alpine and the like): the release is the mirror's
  `linux-<arch>-musl` build. nodejs.org publishes none, so set the *Node.js
  download mirror* to `https://unofficial-builds.nodejs.org/download/release`
  (or use your own Node.js); without one the install says so.
- **Start**: the `web` server role runs `launcher/launch.py` on Hanafubuki's
  managed Python; the instance is ready once dsh asks to open its page, and
  that page (with dsh's `?token=`) opens in the embedded browser
  ([How launching works](#how-launching-works)).
- **Terminal**: the instance's terminal opens in `core` with the instance's
  `dsh`, `npm` and `node` first on `PATH` ([Isolation](#isolation)).
- **Versions page**: the instance's management has a *DeepSeek Harness
  versions* section: the installed dsh and Node.js (the managed one, "your
  own (vX)", or "uses the system's Node.js and dsh (`<prefix>`)"), the npm
  dist-tags and versions, and **Switch**, which asks Hanafubuki to update the
  instance with that version (Hanafubuki asks you to confirm); dsh's home,
  a switch between the instance's and `~/.dsh`, and, once, **Copy from
  ~/.dsh**.
- **Copy from ~/.dsh** (also the instance's *Copy from ~/.dsh* operation):
  copies `~/.dsh` into `dsh-home` and `~/.agents` into `agents-home`, with
  the instance stopped. Nothing is moved, and a file the instance's home
  already has is kept.
- **Discovery**: Hanafubuki's discovery attaches what it recognizes
  ([Discovery](#discovery)): this extension's own layout, and a Node.js
  where dsh was installed with `npm install --global`.
- **Settings**: *npm registry* (for example `https://registry.npmmirror.com`)
  for installs and the version list, and *Node.js download mirror* (for
  example `https://cdn.npmmirror.com/binaries/node`). Both are empty by
  default: npmjs.org and nodejs.org.

## Requirements

- Hanafubuki 0.3.30 or later (below 0.4): backend-provided types with
  `preview`, component labels, `[environment]` (with `unset`), the
  `terminal` operation, `strip` and `replace`, `{host.python}`,
  `{extension.root}` and `{instance.root}`; external components and the
  component map in provider calls; `captured` readiness for a declared
  server role; `[[discovery]]` signatures with `external`;
  `sdWebuiAllInOne` for a Python backend; and the frame client's
  `updateInstance` for the **Switch** button.
- Windows, macOS or Linux on x64 or arm64 (the platforms Node.js publishes).
- Network access to nodejs.org and registry.npmjs.org (or the mirrors you
  set).

## Install

- **From an archive**: build one ([Packaging](#packaging)) or take a release's
  `io.github.licyk.deepseek-harness-<version>.zip`, then in Hanafubuki open
  **Settings > Extensions**, install it, confirm the unverified package and
  turn it on.
- **As a development link**: in **Settings > Extensions**, link this
  repository's folder. Hanafubuki reads it in place; **Reload** applies a
  change. A linked folder must hold no symbolic link anywhere, `web/node_modules`
  included: `web/.npmrc` sets `bin-links=false` for that, so do not install
  the web project's dependencies with another tool.

Then create a **DeepSeek Harness** instance, install it and start it.

## Isolation

The type's `[environment]` (`types/dsh.toml`) applies to the install's
steps, the `web` server and the terminal alike:

- **npm**: the inherited `npm_config_*` (and `NPM_CONFIG_*`), `NODE_OPTIONS`
  and `NODE_PATH` are removed. npm's user configuration is `core/.npmrc`
  (never your `~/.npmrc`: its registry, authentication, `ignore-scripts` or
  `global=true` do not apply), its global configuration `node/etc/npmrc`, its
  prefix `core` (so `npm install --global` in the terminal stays in the
  instance: `core/bin`, or `core` itself on Windows), its cache
  `<instance>/.npm-cache`, and the update notice is off.
- **dsh's home**: `DSH_HOME=<instance>/dsh-home` and
  `DSH_AGENTS_HOME=<instance>/agents-home`, so the instance has its own
  profiles, logins, sessions, plugins and agent configuration. **A new
  instance therefore starts without the login of a dsh you ran before**: use
  **Copy from ~/.dsh** on the versions page, or set `home = user` (the
  launch then empties both variables, which dsh reads as unset: `~/.dsh` and
  `~/.agents`, shared with every other dsh). An instance installed by an
  earlier version of this extension has no `home` value and so takes
  `instance` too.
- **PATH**: `core/node_modules/.bin` (dsh), then `core/bin` and `core` (what
  a global install there adds), then Node.js (`node`, `node/bin`). `dsh`,
  `npm` and `node` typed in the terminal, or in the shells dsh starts for its
  agents, are the instance's; the terminal puts these entries first again
  after your shell's startup files.

The `home` choice reaches the server only: the terminal's environment is the
type's, so `dsh` typed in the terminal of a `home = user` instance uses the
instance's `dsh-home`.

## How launching works

The `web` role's command is planned by the backend:

```text
{host.python} {extension.root}/launcher/launch.py --core {component.core} --node <node> --port {port}
```

with `readiness = { captured = true, timeoutSeconds = 180 }`, so Hanafubuki
gives the process a runtime broker session (`SD_WEBUI_ALL_IN_ONE_RUNTIME_*`)
and waits for its first `browser.open`.

1. `launch.py` starts `sd_webui_all_in_one`'s broker client
   (`DesktopBrokerClient.from_env().start()`), which connects and keeps the
   session's heartbeat for the launcher's life.
2. It runs `node launcher/start-dsh.mjs --core <core> -- web --host
   127.0.0.1 --port <port>` under `sd_webui_all_in_one.process_tree.run_process_tree`,
   so the whole dsh tree ends with the launcher (SIGTERM or SIGHUP, CTRL_BREAK
   on Windows; a watchdog or job object if the launcher dies). dsh's output
   is the launcher's. `start-dsh.mjs` reads `bin.dsh` from
   `<core>/node_modules/@deepseek-ai/dsh/package.json`, sets `process.argv`
   to that program and the dsh arguments, imports it and calls the `runCli`
   it exports (dsh's entry runs itself only as the main module); dsh runs in
   that process, so its exit code is the process's. When dsh is not
   installed there it says so and exits with 3; when `runCli` fails, with 1.
3. dsh's environment is the launcher's, which Hanafubuki composed
   ([Isolation](#isolation)); the launcher derives no path of its own and
   only drops its Python and broker variables (`PYTHON*`, `SD_WEBUI_ALL_IN_ONE_*`) and without
   `SSH_CONNECTION`/`SSH_TTY` (dsh does not open a browser over SSH; here
   the browser is Hanafubuki's, on this machine), plus
   `NODE_OPTIONS=--import=<launcher/intercept.mjs>` and
   `HFX_DSH_OPEN_CHANNEL` (a file the launcher follows).
4. dsh opens its page by resolving the npm `open` package
   (`import.meta.resolve('open')`) and importing it in a child
   `node --input-type=module --eval …` whose environment it scrubs of names
   matching `KEY|PASSWORD|SECRET|TOKEN` and `DSH_*`. `NODE_OPTIONS` and the
   `HFX_DSH_*` names survive the scrub, so `intercept.mjs` loads in both
   processes. Its resolve hook (`module.registerHooks`) replaces the `open`
   under dsh's prefix with `launcher/open-stub.mjs`, which appends the
   http(s) URL to the channel and returns a launcher object that has already
   exited. No browser starts. Other targets, and `open` outside dsh's prefix
   (a project's own, in a tool dsh runs), reach the real package. Every Node
   program dsh runs inherits `NODE_OPTIONS`: one older than 22.15 (a
   project's pinned Node) loads the hook and is left alone, but one older
   than 18.19 does not take `--import` there and refuses to start.
5. The launcher reports each URL with `emit_event("browser.open", {"url": url})`.
   Hanafubuki marks the role ready and opens that URL, token included, in
   the WebView.
6. Fallback: in dsh's own process the hook also watches stdout for
   `dsh web: <url>`. If no intercepted open follows within 5 seconds (dsh
   skipped its opener, for example because its configuration turns
   `openBrowser` off), the launcher reports that URL instead.

Outside Hanafubuki (no broker session) the launcher still runs dsh and
prints where its page is.

## Discovery

The type declares three `[[discovery]]` signatures (`types/dsh.toml`). The
scanner tries them in order at each directory it visits; every marker must
be a regular file or directory reached through no link.

| Signature | Markers (below the directory) | Instance root | `core` | `node` |
| --- | --- | --- | --- | --- |
| This extension's layout | `core/node_modules/@deepseek-ai/dsh/package.json`, `node` | the directory | `core` | `node` |
| A Unix global prefix | `bin/node`, `lib/node_modules/@deepseek-ai/dsh/package.json` | the prefix | the prefix (`.`) | `bin` |
| A Windows global prefix | `node.exe`, `node_modules/@deepseek-ai/dsh/package.json`, `node_modules/npm/package.json` | the prefix | the prefix (`.`) | `node_modules/npm` |

A global prefix is attached with the install parameters' defaults
(`version = "latest"`, `nodeVersion = "24"`) and `home = "user"`, so its dsh
keeps the `~/.dsh` it had: a signature is static, so it cannot read what is
installed. Both its components are recorded as external (the signatures'
`external = ["core", "node"]`): deleting the instance, with its files or
not, never deletes the prefix. The versions page shows the installed dsh,
asks that prefix's `node --version`, and says the instance "uses the
system's Node.js and dsh (`<prefix>`)".

Why `core` is the whole prefix rather than `lib` (where Unix keeps
`node_modules`): Hanafubuki refuses a component that equals or contains
the instance root unless it is `core`, refuses one component inside
another unless that one is `core` and `core` is the root, and refuses a
forced reinstall that would remove a `core` equal to the root. So `node`
cannot be the prefix itself; it is the prefix's `bin` (Unix) or its
bundled npm's directory (Windows, where `node.exe` sits at the prefix's
root and no directory below holds it). So the type's `executable` for
`node` (`bin/node`, `node.exe`), which is what a Node.js of yours chosen in
**Paths** holds, does not describe a prefix's `node`. The backend reads
which layout an instance has from its `core`: a node program there
(`bin/node`, `node.exe`) makes it a global prefix, with or without dsh, so
a prefix whose dsh was uninstalled is still never given a Node.js. It
addresses the prefix's Node.js through `core`:
`{component.core}/bin/node` with dsh in `{component.core}/lib`, or
`{component.core}/node.exe` with dsh in `{component.core}`. The type's
`PATH` holds `{component.core}/bin` and `{component.core}`, which put a
prefix's Node.js and global commands on it.

For a global prefix:

- **Update** (and **Switch**) runs the prefix's own npm,
  `node <npm-cli.js> install --global --prefix <prefix> @deepseek-ai/dsh@<version>`.
  Nothing else is planned: no Node.js is downloaded, replaced or emptied,
  whatever `nodeVersion` says, and nothing (no `hanafubuki-install.txt`, no
  `.npmrc`) is written into the prefix; the registry setting is the step's
  `npm_config_registry`. The versions page hides its Node.js control.
- A forced reinstall leaves it (its components are external).
- Deleting the instance never deletes the prefix. Its root is the prefix,
  so what the type's environment puts under `{instance.root}` (npm's cache
  during an update, `dsh-home` for a `home = instance` instance or its
  terminal) is created in the prefix.
- dsh's `open` is intercepted under the prefix: an http(s) page that
  another global package in it opens while dsh runs it is shown in
  Hanafubuki too.

What is not discovered:

- A `bin/node` or `node.exe` that is a link (Homebrew's `bin/node`, an
  nvm-windows or fnm "current" link), or a dsh installed with `npm link`.
- dsh installed with a global prefix away from its Node.js, as npm's
  default on Windows (`%APPDATA%\npm`, while the installer puts Node.js in
  `Program Files\nodejs`) or a version manager that keeps packages apart.
  A prefix holding both is found: an unpacked Node.js archive (checked on
  Linux) and, by their usual layouts, version managers' per-version folders
  such as nvm's `~/.nvm/versions/node/<version>` (not checked here, nor on
  Windows or macOS).
- A directory below one already recognized, and the filesystem's root as
  an instance root.

## Data

- The instance's directory: `core/` (dsh and its npm dependencies,
  `.npmrc`, `hanafubuki-install.txt`), `node/` (Node.js, unless it is yours),
  `dsh-home/` and `agents-home/` (dsh's profiles, credentials, sessions and
  agent configuration, with `home = instance`) and `.npm-cache/`. They are
  deleted with the instance; a reinstall keeps the homes and the cache.
- With `home = user`, dsh's data is in `~/.dsh` and `~/.agents`, shared with
  a dsh you run yourself, and kept when the instance is deleted.
- The extension's data directory: `cache/` (the release index for an hour,
  each release's `SHASUMS256.txt`, the npm registry's document for ten
  minutes) and `instances.json` (each instance's components and values as
  the last provider call gave them, for the versions page, whose calls carry
  only the instance's id; and whether `~/.dsh` was copied in).

## Development

| Path | What |
| --- | --- |
| `hanafubuki-extension.toml` | The manifest. |
| `types/dsh.toml` | The type: components, environment, parameters, operations, the `web` role, discovery. |
| `backend/` | The Python backend: `main.py` (the handler), `spec.py` (the parameters), `node_release.py` (the Node.js release), `layout.py` (the components and the layouts), `plans.py` (the steps and the command), `home.py` (dsh's homes and the copy), `known.py` (what the versions page knows of an instance), `remote.py` (fetching and caching). |
| `launcher/` | What the host runs: `launch.py`, `start-dsh.mjs`, `intercept.mjs`, `open-stub.mjs`. |
| `ui/versions/` | The built versions page (committed). |
| `web/` | Its Vue 3 + Vite source; not part of the package. |
| `locales/`, `schemas/`, `images/` | Strings (en, zh), the Settings form, the type's preview. |
| `tests/` | The tests; `scripts/package.py` builds the archive. |

The SDK and `sd_webui_all_in_one` come with Hanafubuki. The tests find them
through `HANAFUBUKI_SDK_PYTHON` (the directory holding `hanafubuki_extension`,
default `../Hanafubuki-dev/sdk/python`) and `SD_WEBUI_ALL_IN_ONE_PATH` (a
checkout of sd-webui-all-in-one or Hanafubuki's launcher code, default
`../sd-webui-all-in-one`), and skip what needs one they cannot find; the
intercept and launcher tests need `node` (24.9 or later) on `PATH`.

```sh
python -m pytest                       # or: python -m unittest discover -s tests -t .
HFX_NETWORK_TESTS=1 python -m pytest tests/test_network.py   # nodejs.org and npm, live
python -m ruff check . && python -m ruff format --check .
python -m ty check --extra-search-path . --extra-search-path <sdk> --extra-search-path <launcher code> \
  --extra-search-path <launcher code>/sd_webui_all_in_one/patcher backend launcher scripts tests
```

The versions page:

```sh
cd web
npm ci
npm run build      # type-checks, then writes ../ui/versions
```

The build keeps what a frame needs: relative URLs (`base: './'`), one flat
directory so the script's `../../__hanafubuki/frame.js` is the frame client
the host serves at the package root, no module-preload polyfill, no inline
script, and no network of its own (all data comes from the backend through
`call`).

## Packaging

```sh
python scripts/package.py            # dist/io.github.licyk.deepseek-harness-<version>.zip
```

The archive holds the manifest, `README.md`, `LICENSE`, `types/`,
`locales/`, `schemas/`, `images/`, `backend/`, `launcher/` and `ui/`;
`web/`, `tests/`, `scripts/` and caches stay out. Build the page first.

## 中文说明

这是 Hanafubuki 的扩展：在实例自带的（或你自己的）Node.js 上用 npm 安装
DeepSeek Harness（`@deepseek-ai/dsh`），与你的 npm 配置和 `~/.dsh` 隔离，启动它的
网页界面并在 Hanafubuki 内置浏览器中打开，并可在实例管理页的「DeepSeek Harness
版本」中切换 npm 版本。

- 参数：`version`（默认 `latest`，可填 `next`、`alpha` 或确切版本）、
  `nodeVersion`（默认 `24`，可填主版本号、`lts`、`latest` 或确切版本；dsh 需要
  Node.js 24.9.0 及以上；更新时重新解析，`24` 会升级到更新的 24.x）与
  `home`（默认 `instance`，或 `user`）。
- 隔离：类型的 `[environment]` 移除继承的 `npm_config_*`、`NODE_OPTIONS`、
  `NODE_PATH`，npm 的用户配置为 `core/.npmrc`（npm 源设置写在这里，不读取你的
  `~/.npmrc`），全局前缀为 `core`，缓存在实例的 `.npm-cache`；`DSH_HOME` 与
  `DSH_AGENTS_HOME` 为实例中的 `dsh-home`、`agents-home`。**因此新实例不带有你之前
  在 `~/.dsh` 中的登录**：可在版本页面使用「从 ~/.dsh 复制」（只复制、不移动、不覆盖
  已有文件），或把 `home` 设为 `user` 共用 `~/.dsh`（仅对服务器生效，终端仍使用
  实例的主目录）。终端和 dsh 启动的 shell 中，`dsh`、`npm`、`node` 都是实例自己的。
- 自己的 Node.js：在实例的「路径」中可把 `node` 指向已有的 Node.js（选择其
  `bin/node`，Windows 上为 `node.exe`）；它是外部组件，计划不会向其中下载，删除或
  重装实例也不会删除它；其版本须为 24.9.0 及以上且自带 npm。
- musl Linux：需把 Node.js 下载镜像设为
  `https://unofficial-builds.nodejs.org/download/release`（或使用自己的 Node.js），
  否则安装会说明原因。
- 启动：启动器在 Hanafubuki 的托管 Python 上运行，用 Node 执行
  `launcher/start-dsh.mjs`（按 dsh 的 `package.json` 中的 `bin.dsh` 找到并启动 dsh，
  未安装时给出明确错误，并转发 dsh 的退出码），通过
  `NODE_OPTIONS=--import` 加载钩子，拦截 dsh 打开浏览器的 `open` 包，把带
  token 的地址通过 `sd_webui_all_in_one` 的 broker 客户端上报为
  `browser.open`，由 Hanafubuki 在内置浏览器中打开；若 5 秒内没有拦截到，
  则改用 dsh 输出的 `dsh web: <url>` 行。
- 发现：除本扩展的目录结构外，还能识别用 `npm install --global` 安装了 dsh 的
  Node.js 前缀（Unix：`bin/node` 与 `lib/node_modules/@deepseek-ai/dsh`；Windows：
  `node.exe`、`node_modules/@deepseek-ai/dsh` 与 `node_modules/npm`），`core` 为该前缀，
  参数取默认值且 `home = user`，`core` 与 `node` 都记录为外部组件。对这类实例，
  更新只用该前缀自带的 npm 执行 `npm install --global`，从不下载、替换或清空其中的
  Node.js；删除实例不会删除该前缀。
- 数据：实例目录中的 `dsh-home`、`agents-home` 与 `.npm-cache` 随实例删除；
  `home = user` 时 dsh 的数据在 `~/.dsh`，删除实例不会删除它。
- 设置：可配置 npm 源（如 `https://registry.npmmirror.com`）和 Node.js 下载镜像
  （如 `https://cdn.npmmirror.com/binaries/node`）。
- 开发：`web/` 中执行 `npm ci && npm run build` 构建版本页面；以开发链接安装时，
  文件夹内不能有符号链接（`web/.npmrc` 已设置 `bin-links=false`）。
  `python scripts/package.py` 生成安装包。
