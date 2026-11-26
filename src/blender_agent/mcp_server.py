"""Optional MCP stdio adapter; the core is usable without MCP or an LLM."""

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import BoundedSemaphore, Event

from .inspect import inspect_asset
from .jobs import DEFAULT_TIMEOUT, execute, validate_timeout
from .paths import root_path


def main(*, workspace: str | None = None, blender: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> int:
    workspace = workspace if workspace is not None else os.environ.get("BLENDER_AGENT_WORKSPACE")
    if not workspace:
        print("Set BLENDER_AGENT_WORKSPACE or pass --workspace before the mcp subcommand.", file=sys.stderr)
        return 2
    try:
        root = root_path(workspace)
        validate_timeout(timeout)
    except (ValueError, OSError) as exc:
        print(f"Invalid MCP configuration. {exc}", file=sys.stderr)
        return 2
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError('Install the MCP extra: pip install -e ".[mcp]"') from exc

    server = FastMCP("blender-agent")
    executable = blender if blender is not None else os.environ.get("BLENDER_AGENT_BLENDER", "blender")

    async def run_job(operation, **arguments):
        cancelled = Event()
        job = partial(
            execute, operation, workspace=root, blender=executable, timeout=timeout,
            cancelled=cancelled, **arguments,
        )
        try:
            return await asyncio.get_running_loop().run_in_executor(job_worker, job)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    @server.tool()
    async def inspect_model(path: str) -> dict:
        """Read-only structural inspection of an STL, OBJ, or other supported asset."""
        if not inspection_slot.acquire(blocking=False):
            raise RuntimeError("Inspection capacity exhausted; retry after the active inspection finishes.")
        cancelled = Event()
        try:
            future = inspection_worker.submit(inspect_asset, path, root, cancelled=cancelled)
        except BaseException:
            inspection_slot.release()
            raise
        future.add_done_callback(lambda _: inspection_slot.release())
        try:
            return await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    @server.tool()
    async def create_primitive(kind: str, output: str, size: float = 1.0) -> dict:
        """Make a cube, UV sphere or cylinder as STL/OBJ/GLB/FBX/BLEND."""
        return await run_job("create", kind=kind, output=output, size=size)

    @server.tool()
    async def convert_model(source: str, output: str) -> dict:
        """Convert a model with Blender without overwriting the source."""
        return await run_job("convert", source=source, output=output)

    @server.tool()
    async def repair_mesh(source: str, output: str) -> dict:
        """Merge near-duplicate vertices and recalculate face normals in a copy."""
        return await run_job("repair", source=source, output=output)

    # Cancellation of a caller must not free a Blender slot while its worker is still running.
    inspection_slot = BoundedSemaphore(1)
    with (ThreadPoolExecutor(max_workers=1, thread_name_prefix="blender-job") as job_worker,
          ThreadPoolExecutor(max_workers=1, thread_name_prefix="asset-inspection") as inspection_worker):
        server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
