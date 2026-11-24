"""Exercise the installed MCP launcher with an optional real Blender roundtrip."""
import argparse
import asyncio
import hashlib
import json
import math
import os
import shlex
import shutil
import struct
import subprocess
import sysconfig
import tempfile
from pathlib import Path


async def call_tool(session, name, **arguments):
    subject = arguments.get("output", arguments.get("path", ""))
    print(f"MCP tool start: {name} {subject}", flush=True)
    result = await session.call_tool(name, arguments)
    assert not result.isError, (name, arguments, result)
    payload = result.structuredContent
    if payload is None:
        payload = json.loads(result.content[0].text)
    assert isinstance(payload, dict), (name, payload)
    print(f"MCP tool passed: {name} {subject}", flush=True)
    return payload


async def expect_error(session, name, message, **arguments):
    result = await session.call_tool(name, arguments)
    assert result.isError, (name, arguments, result)
    assert any(
        content.type == "text" and message in content.text
        for content in result.content
    ), (name, arguments, result)


async def publish(session, workspace, tool, operation, *, output, **arguments):
    payload = await call_tool(session, tool, output=output, **arguments)
    assert payload["ok"] is True and payload["operation"] == operation, payload
    assert Path(payload["output"]) == Path(output), payload
    content = (workspace / output).read_bytes()
    assert 0 < len(content) == payload["size_bytes"], payload
    geometry = payload["geometry"]
    assert geometry["mesh_objects"] == 1 and geometry["faces"] > 0, payload
    return content, geometry


async def blender_roundtrip(session, workspace):
    workflow = (
        ("create_primitive", "create", "cube.stl", {"kind": "cube", "size": 1.0}),
        ("convert_model", "convert", "cube.glb", {"source": "cube.stl"}),
        ("convert_model", "convert", "roundtrip.stl", {"source": "cube.glb"}),
        ("repair_mesh", "repair", "repaired.stl", {"source": "roundtrip.stl"}),
    )
    snapshots = {}
    for tool, operation, output, arguments in workflow:
        content, _ = await publish(
            session, workspace, tool, operation, output=output, **arguments,
        )
        snapshots[output] = content

    for name, content in snapshots.items():
        info = await call_tool(session, "inspect_model", path=name)
        assert info["name"] == name and info["size_bytes"] == len(content), info
        assert info["sha256"] == hashlib.sha256(content).hexdigest(), info
        if name.endswith(".stl"):
            assert info["format"] == "stl" and info["triangles"] == 12, info
            for key, expected in (("min", -0.5), ("max", 0.5)):
                bounds = info["bounds"][key]
                assert len(bounds) == 3 and all(
                    math.isclose(value, expected, rel_tol=0, abs_tol=0.005)
                    for value in bounds
                ), (name, info)
        else:
            assert info["format"] == "glb" and content.startswith(b"glTF"), info

    # Two adjacent triangles whose shared edge is split by less than the weld distance.
    seam = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nv 1.00005 0 0\nv 0.00005 1 0\nv 1 1 0\nf 1 2 3\nf 4 6 5\n"
    (workspace / "split-edge.obj").write_bytes(seam)
    snapshots["split-edge.obj"] = seam
    _, before = await publish(
        session, workspace, "convert_model", "convert", source="split-edge.obj", output="split-edge.stl",
    )
    _, after = await publish(
        session, workspace, "repair_mesh", "repair", source="split-edge.obj", output="welded.stl",
    )
    assert before["vertices"] == 6 and after["vertices"] == 4, (before, after)
    assert before["faces"] == after["faces"] == 2, (before, after)

    await expect_error(
        session, "repair_mesh", "Source files cannot be modified in place.",
        source="roundtrip.stl", output="roundtrip.stl",
    )
    await expect_error(
        session, "create_primitive", "Destination already exists",
        kind="cube", size=2.0, output="repaired.stl",
    )
    for name, content in snapshots.items():
        assert (workspace / name).read_bytes() == content, name

    print("MCP workflow: all four tools, STL -> GLB -> STL geometry, and repair passed.")
    print("MCP repair: split-edge fixture welded 6 vertices to 4 and kept both faces.")
    print("MCP file safety: in-place repair and destination overwrite denied; original bytes unchanged.")


async def obj_material_roundtrip(session, workspace):
    source = b"mtllib source.mtl\no Triangle\nv 0 0 0\nv 1 0 0\nv 0 1 0\nusemtl AuditRed\nf 1 2 3\n"
    material = b"newmtl AuditRed\nKd 1.0 0.0 0.0\n"
    (workspace / "source.obj").write_bytes(source)
    (workspace / "source.mtl").write_bytes(material)

    output = await call_tool(session, "convert_model", source="source.obj", output="red model.obj")
    assert output["material_library"] == "red model.mtl", output
    obj = (workspace / "red model.obj").read_bytes()
    mtl = (workspace / "red model.mtl").read_bytes()
    assert b"mtllib red model.mtl" in obj.splitlines() and b"usemtl AuditRed" in obj.splitlines(), obj
    assert b"newmtl AuditRed" in mtl.splitlines(), mtl

    # Convert the published OBJ with Blender, then read the material assigned in the resulting GLB.
    glb, _ = await publish(
        session, workspace, "convert_model", "convert", source="red model.obj", output="color.glb",
    )
    size, kind = struct.unpack_from("<I4s", glb, 12)
    assert glb[:4] == b"glTF" and kind == b"JSON"
    scene = json.loads(glb[20:20 + size])
    primitive, = scene["meshes"][0]["primitives"]
    restored = scene["materials"][primitive["material"]]
    color = restored["pbrMetallicRoughness"]["baseColorFactor"]
    assert restored["name"] == "AuditRed", restored
    assert len(color) == 4 and all(
        math.isclose(channel, expected, abs_tol=0.001)
        for channel, expected in zip(color, (1.0, 0.0, 0.0, 1.0))
    ), restored

    for suffix, missing_suffix in ((".obj", ".mtl"), (".mtl", ".obj")):
        existing = workspace / f"collision{suffix}"
        existing.write_bytes(b"keep existing destination")
        await expect_error(
            session, "convert_model", "Destination already exists",
            source="source.obj", output="collision.obj",
        )
        assert existing.read_bytes() == b"keep existing destination"
        assert not (workspace / f"collision{missing_suffix}").exists()
        existing.unlink()

    assert (workspace / "source.obj").read_bytes() == source
    assert (workspace / "source.mtl").read_bytes() == material
    print("MCP OBJ materials: Blender re-import preserved the assigned AuditRed color.")
    print("MCP OBJ collisions: existing OBJ and MTL preserved, with no partial output.")


async def reject_faceless_output(session, workspace):
    wire = b"v 0 0 0\nv 1 0 0\nl 1 2\n"
    (workspace / "wire.obj").write_bytes(wire)
    await expect_error(
        session, "convert_model", "No mesh faces are available for output.",
        source="wire.obj", output="faceless.stl",
    )
    assert not (workspace / "faceless.stl").exists()
    assert (workspace / "wire.obj").read_bytes() == wire
    print("MCP geometry: Blender rejected a wire-only OBJ without publishing an output.")


async def run_blender_fixture(blender, action, *paths):
    fixture = Path(__file__).with_name("blender_linked_fixture.py").resolve()
    command = [
        str(blender.resolve(strict=True)), "--background", "--factory-startup",
        "--disable-autoexec", "--python-exit-code", "17", "--python", str(fixture), "--",
    ]
    result = await asyncio.to_thread(
        subprocess.run, [*command, action, *(str(path) for path in paths)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (action, result.stdout, result.stderr)


async def verify_blend_dependency(session, workspace, blender):
    project = workspace / "source project" / "linked.blend"
    resource = project.parent / "deps" / "texture.png"
    destination = workspace / "published" / "linked.blend"
    destination.parent.mkdir()
    await run_blender_fixture(blender, "create", project, resource)
    original_project, original_resource = project.read_bytes(), resource.read_bytes()
    await publish(
        session, workspace, "convert_model", "convert",
        source="source project/linked.blend", output="published/linked.blend",
    )
    await run_blender_fixture(blender, "verify", destination, resource)
    assert project.read_bytes() == original_project and resource.read_bytes() == original_resource
    print("MCP BLEND export: published project reopened and loaded its original relative image.")


async def verify_shared_mesh_repair(session, workspace, blender):
    source = workspace / "shared.blend"
    output = workspace / "shared-repaired.blend"
    await run_blender_fixture(blender, "create_shared", source)
    original = source.read_bytes()
    result = await call_tool(session, "repair_mesh", source=source.name, output=output.name)
    assert result["ok"] and result["geometry"]["repaired_mesh_datablocks"] == 1, result
    await run_blender_fixture(blender, "verify_shared", output)
    assert source.read_bytes() == original
    print("MCP shared repair: one datablock repaired; both transforms, UVs, and material survived.")


async def verify_multi_scene_geometry(session, workspace, blender):
    source = workspace / "two-scenes.blend"
    await run_blender_fixture(blender, "create_multi_scene", source)
    original = source.read_bytes()

    def counts(result, scope, expected):
        assert result["ok"] and result["operation"] == "convert", result
        assert result["geometry_scope"] == scope, result
        geometry = result["geometry"]
        assert tuple(geometry[key] for key in ("mesh_objects", "vertices", "faces")) == expected, result
        assert result["size_bytes"] == (workspace / result["output"]).stat().st_size > 0, result

    for extension in ("stl", "obj", "fbx"):
        output = "active-scene." + extension
        result = await call_tool(session, "convert_model", source=source.name, output=output)
        counts(result, "pre_export_scene", (1, 3, 1))
        assert Path(result["output"]) == Path(output), result
        if extension == "stl":
            artifact = await call_tool(session, "inspect_model", path=output)
            assert result["artifact_validation"] == "structural_mesh", result
            assert artifact["triangles"] == 1, artifact
        elif extension == "obj":
            artifact = await call_tool(session, "inspect_model", path=output)
            assert result["artifact_validation"] == "structural_mesh", result
            assert artifact["vertices"] == 3 and artifact["faces"] == 1, artifact
        else:
            await call_tool(session, "convert_model", source=output, output="fbx-scene.stl")
            artifact = await call_tool(session, "inspect_model", path="fbx-scene.stl")
            assert artifact["triangles"] == 1, artifact

    result = await call_tool(session, "convert_model", source=source.name, output="all-scenes.blend")
    counts(result, "pre_export_file", (2, 11, 7))
    await run_blender_fixture(blender, "verify_multi_scene", workspace / "all-scenes.blend")

    result = await call_tool(session, "convert_model", source=source.name, output="all-scenes.glb")
    counts(result, "pre_export_file", (2, 11, 7))
    glb = (workspace / "all-scenes.glb").read_bytes()
    size, kind = struct.unpack_from("<I4s", glb, 12)
    assert glb[:4] == b"glTF" and kind == b"JSON"
    document = json.loads(glb[20:20 + size])
    assert {scene["name"] for scene in document["scenes"]} == {"Active Triangle", "Secondary Cube"}, document
    assert {mesh["name"] for mesh in document["meshes"]} == {"Triangle", "Cube"}, document
    assert source.read_bytes() == original, "The source blend file changed"
    print("MCP multi-scene geometry: STL/OBJ/FBX active scene; BLEND/GLB file scope; artifacts and source verified.")


async def verify_linked_repair_scope(session, workspace, blender):
    project = workspace / "repair-scope.blend"
    library = workspace / "repair-library.blend"
    active_linked = workspace / "repair-active-linked.blend"
    await run_blender_fixture(blender, "create_repair_scope", project, library, active_linked)
    original = {path: path.read_bytes() for path in (project, library, active_linked)}

    for extension in ("stl", "obj", "fbx"):
        output = "scoped-repair." + extension
        result = await call_tool(session, "repair_mesh", source=project.name, output=output)
        assert result["ok"] and result["operation"] == "repair", result
        assert result["geometry_scope"] == "pre_export_scene", result
        geometry = result["geometry"]
        assert tuple(geometry[key] for key in ("mesh_objects", "vertices", "faces", "repaired_mesh_datablocks")) == (1, 4, 2, 1), result
        assert result["size_bytes"] == (workspace / output).stat().st_size > 0, result
        if extension == "obj":
            artifact = await call_tool(session, "inspect_model", path=output)
            assert artifact["vertices"] == 4 and artifact["faces"] == 2, artifact
        else:
            if extension == "fbx":
                await call_tool(session, "convert_model", source=output, output="scoped-fbx.stl")
                output = "scoped-fbx.stl"
            artifact = await call_tool(session, "inspect_model", path=output)
            assert artifact["triangles"] == 2, artifact

    # Active-scene repair must reject a linked mesh inside that scene.
    # Whole-file repair must reject the same read-only mesh even when inactive.
    for source, extension in (
        (active_linked, "stl"), (active_linked, "obj"), (active_linked, "fbx"),
        (project, "blend"), (project, "glb"),
    ):
        output = "rejected-linked." + extension
        await expect_error(session, "repair_mesh", "Repair requires editable mesh datablocks.",
                           source=source.name, output=output)
        assert not (workspace / output).exists(), output
        if extension == "obj":
            assert not (workspace / "rejected-linked.mtl").exists()

    assert all(path.read_bytes() == content for path, content in original.items())
    print("MCP repair scope #69: inactive linked scene excluded; actual weld verified; in-scope read-only repair rejected; source and library bytes unchanged.")


async def verify_blender_scheduling(cli, blender, host_directory, workspace, env):
    from mcp import ClientSession, StdioServerParameters
    from mcp import types
    from mcp.client.stdio import stdio_client

    gate = host_directory / "allow-blender"
    wrapper = host_directory / "gated-blender"
    quoted_gate = shlex.quote(str(gate))
    marker = shlex.quote(str(host_directory / "started-"))
    executable = shlex.quote(str(blender.resolve(strict=True)))
    wrapper.write_text(
        f"#!/bin/sh\ntouch {marker}\"$$\"\n"
        f"while [ ! -f {quoted_gate} ]; do sleep 0.05; done\n"
        f"exec {executable} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    args = ["--workspace", str(workspace), "--blender", str(wrapper)]
    params = StdioServerParameters(command=cli, args=[*args, "mcp"], cwd=host_directory, env=env)
    async with asyncio.timeout(30), stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            async with asyncio.TaskGroup() as tasks:
                first = tasks.create_task(call_tool(session, "create_primitive", kind="cube", output="first.stl"))
                try:
                    async with asyncio.timeout(10):
                        while not list(host_directory.glob("started-*")):
                            await asyncio.sleep(0.05)
                    second = tasks.create_task(
                        call_tool(session, "create_primitive", kind="cube", output="second.stl"),
                    )
                    info = await asyncio.wait_for(call_tool(session, "inspect_model", path="mesh.obj"), timeout=5)
                    assert info["faces"] == 1 and not first.done() and not second.done()
                    assert len(list(host_directory.glob("started-*"))) == 1
                finally:
                    gate.touch()
            assert first.result()["ok"] and second.result()["ok"]
            assert len(list(host_directory.glob("started-*"))) == 2

            gate.unlink()
            # This fixture uses the v1 SDK's next request ID for a protocol-level cancellation.
            request_id = session._request_id
            interrupted = asyncio.create_task(
                call_tool(session, "create_primitive", kind="cube", output="cancelled.stl"),
            )
            try:
                async with asyncio.timeout(10):
                    while len(list(host_directory.glob("started-*"))) != 3:
                        await asyncio.sleep(0.05)
                await session.send_notification(types.ClientNotification(
                    types.CancelledNotification(params=types.CancelledNotificationParams(requestId=request_id)),
                ))
                await asyncio.wait_for(session.send_ping(), timeout=5)
            finally:
                interrupted.cancel()
                await asyncio.gather(interrupted, return_exceptions=True)
                gate.touch()
            afterward = await call_tool(session, "create_primitive", kind="cube", output="after-cancel.stl")
            assert afterward["ok"] and (workspace / "after-cancel.stl").is_file()
            assert not (workspace / "cancelled.stl").exists()
    gate.unlink()

    params = StdioServerParameters(command=cli, args=[*args, "--timeout", "1", "mcp"],
                                    cwd=host_directory, env=env)
    async with asyncio.timeout(20), stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            await expect_error(
                session, "create_primitive", "Blender operation exceeded its timeout.",
                kind="cube", output="timed-out.stl",
            )
            assert not (workspace / "timed-out.stl").exists()
            assert not any(path.is_dir() for path in workspace.glob(".blender-agent-*"))
    print("MCP scheduling: inspection replied during a blocked job, one Blender ran at a time, and timeout cleaned up.")
    print("MCP cancellation: a cancelled active request left no output; the subsequent request succeeded.")


async def smoke(blender):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    launcher = shutil.which("blender-agent-mcp", path=sysconfig.get_path("scripts"))
    assert launcher, "The installed blender-agent-mcp console script is missing"
    cli = shutil.which("blender-agent", path=sysconfig.get_path("scripts"))
    assert cli, "The installed blender-agent console script is missing"
    required_arguments = {
        "inspect_model": {"path"},
        "create_primitive": {"kind", "output"},
        "convert_model": {"source", "output"},
        "repair_mesh": {"source", "output"},
    }
    with tempfile.TemporaryDirectory() as directory:
        host_directory = Path(directory)
        workspace = host_directory / "asset workspace"
        workspace.mkdir()
        mesh = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
        source = workspace / "mesh.obj"
        source.write_text(mesh, encoding="utf-8")
        (host_directory / "outside.obj").write_text(mesh, encoding="utf-8")
        env = {**os.environ, "BLENDER_AGENT_WORKSPACE": str(workspace)}
        missing_env = {key: value for key, value in env.items() if key != "BLENDER_AGENT_WORKSPACE"}
        for command in ([launcher], [cli, "mcp"]):
            missing = subprocess.run(
                command, env=missing_env, cwd=host_directory, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=15,
            )
            assert missing.returncode == 2 and "BLENDER_AGENT_WORKSPACE" in missing.stderr, missing
            invalid = subprocess.run(
                command, env={**env, "BLENDER_AGENT_WORKSPACE": str(source)}, cwd=host_directory,
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15,
            )
            assert invalid.returncode == 2 and "existing directory" in invalid.stderr, invalid
        invalid_timeout = subprocess.run(
            [cli, "--timeout", "0", "mcp"], env=env, cwd=host_directory, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=15,
        )
        assert invalid_timeout.returncode == 2 and "between 1 and 900" in invalid_timeout.stderr, invalid_timeout
        if blender is not None:
            env["BLENDER_AGENT_BLENDER"] = str(blender.resolve(strict=True))
        params = StdioServerParameters(
            command=launcher,
            cwd=host_directory,
            env=env,
        )
        timeout = 180 if blender is not None else 60
        async with asyncio.timeout(timeout), stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "blender-agent", initialized
                assert initialized.capabilities.tools is not None, initialized
                available = await session.list_tools()
                schemas = {tool.name: tool.inputSchema for tool in available.tools}
                assert set(schemas) == set(required_arguments), schemas
                for name, expected in required_arguments.items():
                    assert set(schemas[name]["required"]) == expected, schemas[name]
                    assert "overwrite" not in schemas[name]["properties"], schemas[name]

                await expect_error(
                    session, "inspect_model", "Path must remain inside the configured workspace.",
                    path="../outside.obj",
                )
                payload = await call_tool(session, "inspect_model", path="mesh.obj")
                assert payload["faces"] == 1, payload
                assert source.read_text(encoding="utf-8") == mesh
                print("Installed MCP launcher handshake, tool schemas and workspace isolation: PASS")
                if blender is not None:
                    await blender_roundtrip(session, workspace)
                    await obj_material_roundtrip(session, workspace)
                    await reject_faceless_output(session, workspace)
                    await verify_blend_dependency(session, workspace, blender)
                    await verify_shared_mesh_repair(session, workspace, blender)
                    await verify_multi_scene_geometry(session, workspace, blender)
                    await verify_linked_repair_scope(session, workspace, blender)

        cli_params = StdioServerParameters(
            command=cli, args=["--workspace", str(workspace), "mcp"], cwd=host_directory,
            env={**env, "BLENDER_AGENT_WORKSPACE": str(source)},
        )
        async with asyncio.timeout(30), stdio_client(cli_params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                payload = await call_tool(session, "inspect_model", path="mesh.obj")
                assert payload["faces"] == 1, payload
        print("MCP configuration: both launchers reject missing or invalid workspaces; CLI flags take precedence.")
        if blender is not None and os.name == "posix":
            await verify_blender_scheduling(cli, blender, host_directory, workspace, env)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, help="Path to a real Blender executable for the roundtrip")
    asyncio.run(smoke(parser.parse_args().blender))
