import os
import subprocess
from typing import Any

import psutil


class ProcessAdapter:
    def build_popen_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        return kwargs

    def start(self, command: list[str], cwd: str | None = None, env: dict[str, str] | None = None) -> subprocess.Popen[str]:
        return subprocess.Popen(command, cwd=cwd, env=env, **self.build_popen_kwargs())

    def stop(self, process: subprocess.Popen[str]) -> None:
        process.terminate()

    def poll(self, process: subprocess.Popen[str]) -> int | None:
        return process.poll()

    def kill_tree(self, pid: int) -> None:
        try:
            root = psutil.Process(pid)
        except psutil.Error:
            return
        for child in root.children(recursive=True):
            try:
                child.kill()
            except psutil.Error:
                continue
        try:
            root.kill()
        except psutil.Error:
            return
