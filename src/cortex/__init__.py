"""Cortex: local-first MCP memory server.

Import from the submodules (``from cortex.sanitize import Sanitized, sanitize``). The package
root re-exports nothing on purpose: re-exporting the ``sanitize`` function would shadow the
``cortex.sanitize`` module (``import cortex.sanitize as m`` would return the function).
"""
