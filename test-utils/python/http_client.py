from __future__ import annotations

import urllib.request


def get_json(url: str, token: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"x-botik-session-token": token})
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, response.read().decode("utf-8")
