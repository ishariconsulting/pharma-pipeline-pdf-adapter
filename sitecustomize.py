"""Optional startup hook for browser-only additive extensions.

Python imports sitecustomize automatically when present on sys.path. The main
adapter service does not install Playwright, so this hook is a no-op there.
Browser retrieval services do install Playwright, allowing the BMS rendered-text
route to register without changing their existing start command.
"""

from __future__ import annotations

import importlib.util

if importlib.util.find_spec("playwright") is not None:
    import browser_bms_extension  # noqa: F401,E402
