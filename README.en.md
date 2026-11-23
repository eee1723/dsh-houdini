# dsh-houdini

[简体中文](README.md) · [Releases](https://github.com/eee1723/dsh-houdini/releases) · [Setup guide](docs/setup.md)

Use natural language in DeepSeek Harness Desktop to build and revise a real Houdini scene. The deliverable is an editable network, HIP file or digital asset. The plugin adds a **Houdini** mode; it does not replace Desktop or change your other conversations.

## Install or update

In Desktop, enable **Custom plugin indexes** under **Plugins → Experimental plugins**. In **Discover → Add index source**, paste the address below once per profile. Find **DSH-Houdini**, install the version recommended for your DSH, then enable it. The version list shows which releases accept your host.

```text
https://raw.githubusercontent.com/eee1723/dsh-houdini/main/market/index.json
```

If your Desktop has no Discover tab, use the exact package for your DSH version below.

**Windows x64 · DSH 0.2.2-rc.5 · Houdini 21.0 / 22.0**. Check your Desktop version first. On rc.3, use plugin **0.1.12**; on rc.1, use **0.1.11**.

1. In Desktop, open **Plugins → Add plugin**, choose the official npm registry or npmmirror, paste the package name, install and enable:

```text
dsh-houdini@0.1.13
```

2. Alternatively, paste the GitHub package URL into the same field, or download that file and enter its absolute path. Do not use the source archive. All three channels serve the same tarball.

```text
https://github.com/eee1723/dsh-houdini/releases/download/v0.1.13/dsh-houdini-0.1.13.tgz
```

3. Start a **Houdini** conversation and select your scene, or use **DSH-Houdini → Open Workspace** in Houdini. After updating, save and reopen the Houdini windows that need the new bridge.

## Try it

> Build a spiral staircase. Expose step count, width and total height on one node. Change the step count and check the landings still line up. Keep the network editable.

Use native procedural modeling or interchangeable parts; inspect and repair an existing network; turn a tutorial into an editable project; or [prepare an HDA for Unreal](skills/houdini-unreal-handoff/SKILL.md) with its dependencies. External generation is optional and uses the providers you configure.

[Setup and troubleshooting](docs/setup.md) · [Scene selection and recovery](docs/multi-instance.md) · [Tool reference](docs/tools.md) · [Skills](skills/) · [Development](docs/development.md) · [Report an issue](https://github.com/eee1723/dsh-houdini/issues)
