# Blender-Agent Refinement Toolkit

*Give shape to an idea.*

**BART** is the agent for Blender-Agent Refinement Toolkit. Use it from a terminal or an MCP host to inspect an asset, create a primitive, convert a file, or repair a mesh on your own machine. Inspection runs with Python alone. Creation, conversion, and repair run Blender in the background.

The current [v0.0.3 pre-alpha](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/releases/tag/v0.0.3) is the source for the examples below. See the [changelog](CHANGELOG.md) for work on `main`.

[Quick start](#quick-start) · [MCP setup](#mcp-setup) · [Capabilities](#capabilities) · [Compatibility](#compatibility) · [Contributing](#contributing)

## Quick start

Use Git and Python 3.11 or newer. The example creates a local `Blender-Agent` folder. Run it from a directory where that name is available.

```sh
git clone -b v0.0.3 --single-branch https://github.com/vixttha/Blender-Agent-Refinement-Toolkit.git Blender-Agent
cd Blender-Agent
python -m venv .venv
```

### macOS or Linux

The examples use `python`. If your system exposes Python 3 as `python3`, use that in the clone block.

```sh
.venv/bin/python -m pip install .
.venv/bin/blender-agent version
mkdir -p readme-demo
cat > readme-demo/triangle.obj <<'OBJ'
v 0 0 0
v 1 0 0
v 0 1 0
f 1 2 3
OBJ
.venv/bin/blender-agent --workspace readme-demo inspect triangle.obj
```

### Windows PowerShell

Run this block after the clone block. It uses the virtual environment’s executables directly.

```powershell
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\blender-agent.exe version
New-Item -ItemType Directory -Path readme-demo -Force | Out-Null
@'
v 0 0 0
v 1 0 0
v 0 1 0
f 1 2 3
'@ | Set-Content -Encoding ascii readme-demo\triangle.obj
.\.venv\Scripts\blender-agent.exe --workspace readme-demo inspect triangle.obj
```

### Check your result

The version command reports `0.0.3`. The inspection JSON includes these fields:

```json
{
  "format": "obj",
  "vertices": 3,
  "faces": 1,
  "bounds": {
    "min": [0, 0, 0],
    "max": [1, 1, 0]
  }
}
```

The full result includes the file’s size and SHA-256 digest. The digest depends on the exact file bytes, including line endings.

![A solid triangle beside a wireframe triangle with three marked vertices](assets/triangle-inspection.webp)

*Concept illustration of the triangle from the walkthrough. The JSON above shows its inspected geometry.*

### Run a headless Blender job

Install Blender 4.1 or newer. Put the Blender executable on your command path or pass `--blender` with its path before the operation. Use `./.venv/bin/blender-agent` on macOS or Linux. In PowerShell, use `.\.venv\Scripts\blender-agent.exe` in place of the launcher below.

```sh
./.venv/bin/blender-agent --workspace readme-demo create cube cube.stl
./.venv/bin/blender-agent --workspace readme-demo convert cube.stl cube.glb
./.venv/bin/blender-agent --workspace readme-demo repair cube.stl repaired.stl
```

The input stays in place. Choose fresh output names when repeating the commands. The CLI accepts `--overwrite` for a separate convert or repair destination. MCP keeps overwrite disabled.

![Wireframe cube beside a solid orange cube on a neutral background](assets/wireframe-cube.webp)

*Concept illustration of cube geometry. The commands above produce files in `readme-demo`.*

## MCP setup

Complete the quick start, then install the optional MCP adapter in the same virtual environment. It requires MCP SDK 1.30 or later in the v1 series. The adapter requires MCP SDK `>=1.30.0,<2`.

```sh
.venv/bin/python -m pip install ".[mcp]"
```

```powershell
.\.venv\Scripts\python.exe -m pip install ".[mcp]"
```

Use your host’s stdio configuration format. Set `command` to the absolute launcher path inside your clone and set `BLENDER_AGENT_WORKSPACE` to the absolute path to its existing `readme-demo` directory.

```json
{
  "command": "/path/to/Blender-Agent/.venv/bin/blender-agent-mcp",
  "env": {
    "BLENDER_AGENT_WORKSPACE": "/path/to/Blender-Agent/readme-demo",
    "BLENDER_AGENT_BLENDER": "blender"
  }
}
```

On Windows the launcher ends in `.venv\Scripts\blender-agent-mcp.exe`. Use doubled backslashes in JSON or forward slashes. Set `BLENDER_AGENT_BLENDER` to the full executable path if your host needs it for Blender-powered operations. The inspection example runs without Blender.

### First tool call

After connecting, invoke `inspect_model` with the arguments below. The path is relative to the workspace you configured.

```json
{
  "name": "inspect_model",
  "arguments": {
    "path": "triangle.obj"
  }
}
```

Look for the same **3 vertices, 1 face, and bounds** as in the CLI result. The SHA-256 matches the CLI when both inspect the same file. The launcher also exposes `create_primitive`, `convert_model`, and `repair_mesh`. [Host configuration and troubleshooting](docs/HARNESS.md).

## Capabilities

| Task | What BART returns | Needs Blender |
| --- | --- | --- |
| Inspect STL or OBJ | Mesh counts, bounds, file size, and SHA-256 | No |
| Inspect GLB, FBX, or BLEND | File metadata and SHA-256 | No |
| Create | A cube, UV sphere, or cylinder written to a new file | Yes |
| Convert | A new STL, OBJ, GLB, FBX, or BLEND file | Yes |
| Repair | A new file with nearby vertices welded and face normals recalculated | Yes |

Check materials, textures, animation, and printability in your destination tool. The automated roundtrips verify the tested samples’ geometry. Keep an exported OBJ, its returned `material_library`, and any referenced textures together.

## Compatibility

| Area | Verified configuration |
| --- | --- |
| CLI | Python 3.11 and 3.12 on Linux and Windows |
| Installed MCP adapter | Launcher, tool schemas, and workspace-bounded inspection on Linux and Windows |
| Blender workflow | Blender 4.1.0 and 4.5.0 on Ubuntu, and Blender 4.5.0 on Windows. Tests exercise all four MCP tools with real Blender. |

The minimum supported Blender version is 4.1. Named MCP clients, macOS, and other format combinations require their own checks. [Release CI](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/actions/runs/44469831772) · [Detailed harness notes](docs/HARNESS.md)

## Troubleshooting

- **Blender isn’t found.** Check the executable path. For the CLI, put `--blender` before the operation. For MCP, set `BLENDER_AGENT_BLENDER` in the host environment.
- **MCP won’t start.** Use the virtual environment’s absolute launcher path and point `BLENDER_AGENT_WORKSPACE` at an existing absolute directory.
- **The output can’t be written.** Create its parent directory, choose a new filename, and keep the destination inside the workspace.
- **A BLEND file needs linked assets.** Keep original dependencies accessible. Blender can resolve secondary resource paths using the account’s filesystem permissions. A native BLEND output derived from a third-party project retains the input’s trust level. The worker disables script auto-execution for its session. Treat a later opening as a new trust decision. Use OS-level isolation for untrusted inputs. [Security and reporting](SECURITY.md)

## Contributing

Start with the [contributing guide](CONTRIBUTING.md), [repository instructions](AGENTS.md), and [architecture](docs/ARCHITECTURE.md). The [public CI workflow](.github/workflows/ci.yml) covers Python, the clean README walkthrough, MCP, and real Blender. Report problems in [GitHub Issues](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/issues).

[Changelog](CHANGELOG.md) · [v0.0.3 documentation map](https://github.com/vixttha/Blender-Agent-Refinement-Toolkit/blob/2faf3674a5470c369b30f0d55b6fd5ef56e1e710/versions/v0.0.3/README.md) · [MIT License](LICENSE)
