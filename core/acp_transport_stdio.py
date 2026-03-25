"""Async stdio transport for ACP JSON-RPC subprocesses."""

import asyncio
import json
from asyncio.subprocess import PIPE, Process
from contextlib import suppress
from typing import Any, Optional

from .acp_models import ACPStartupError, ACPTimeoutError, ACPTransportError


class ACPStdioTransport:
    """Owns the ACP stdio subprocess and raw JSON-RPC message flow."""

    def __init__(
        self,
        command: str,
        args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
        startup_timeout: float = 30.0,
        read_timeout: Optional[float] = None,
    ):
        self.command = command
        self.args = list(args or [])
        self.env = env
        self.cwd = cwd
        self.startup_timeout = startup_timeout
        self.read_timeout = read_timeout

        self._process: Optional[Process] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._stderr_chunks: list[str] = []
        self._read_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    @property
    def process(self) -> Optional[Process]:
        return self._process

    async def start(self) -> None:
        if self.is_running:
            return

        try:
            self._process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    self.command,
                    *self.args,
                    stdin=PIPE,
                    stdout=PIPE,
                    stderr=PIPE,
                    env=self.env,
                    cwd=self.cwd,
                ),
                timeout=self.startup_timeout,
            )
        except FileNotFoundError as exc:
            raise ACPStartupError(
                message=f"ACP command not found: {self.command}",
                command=self.command,
            ) from exc
        except asyncio.TimeoutError as exc:
            raise ACPTimeoutError(
                message=f"Timed out starting ACP command: {self.command}",
                timeout_seconds=self.startup_timeout,
            ) from exc
        except Exception as exc:
            raise ACPStartupError(
                message=f"Failed to start ACP command: {self.command}",
                command=self.command,
            ) from exc

        if (
            not self._process.stdin
            or not self._process.stdout
            or not self._process.stderr
        ):
            await self.aclose()
            raise ACPStartupError(
                message="ACP stdio pipes are unavailable.",
                command=self.command,
            )

        self._stderr_task = asyncio.create_task(self._drain_stderr())

        if self._process.returncode is not None:
            raise ACPStartupError(
                message="ACP process exited during startup.",
                command=self.command,
                exit_code=self._process.returncode,
                stderr_text=self.stderr_text,
            )

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def stderr_text(self) -> str:
        return "".join(self._stderr_chunks).strip()

    async def send(self, payload: dict[str, Any]) -> None:
        if not self.is_running or not self._process or not self._process.stdin:
            raise ACPTransportError("ACP transport is not running.")

        message = json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n"
        async with self._write_lock:
            self._process.stdin.write(message.encode("utf-8"))
            try:
                await self._process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                raise ACPTransportError(
                    "ACP stdin closed while sending message."
                ) from exc

    async def receive(self) -> dict[str, Any]:
        if not self.is_running or not self._process or not self._process.stdout:
            raise ACPTransportError("ACP transport is not running.")

        async with self._read_lock:
            try:
                if self.read_timeout is None:
                    line = await self._process.stdout.readline()
                else:
                    line = await asyncio.wait_for(
                        self._process.stdout.readline(), timeout=self.read_timeout
                    )
            except asyncio.TimeoutError as exc:
                raise ACPTimeoutError(
                    message="Timed out waiting for ACP response.",
                    timeout_seconds=self.read_timeout or 0.0,
                ) from exc

        if not line:
            exit_code = None if not self._process else self._process.returncode
            raise ACPStartupError(
                message="ACP process closed stdout.",
                command=self.command,
                exit_code=exit_code,
                stderr_text=self.stderr_text,
            )

        try:
            payload = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ACPTransportError(
                "Received invalid JSON-RPC payload from ACP."
            ) from exc

        if not isinstance(payload, dict):
            raise ACPTransportError("Received non-object JSON-RPC payload from ACP.")

        return payload

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self.send(payload)
        return await self.receive()

    async def aclose(self) -> None:
        process = self._process
        self._process = None

        if self._stderr_task:
            self._stderr_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._stderr_task
            self._stderr_task = None

        if not process:
            return

        if process.stdin:
            process.stdin.close()
            with suppress(Exception):
                await process.stdin.wait_closed()

        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def _drain_stderr(self) -> None:
        if not self._process or not self._process.stderr:
            return

        while True:
            line = await self._process.stderr.readline()
            if not line:
                return
            self._stderr_chunks.append(line.decode("utf-8", errors="replace"))
