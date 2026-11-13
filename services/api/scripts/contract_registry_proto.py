"""Read the proto tree: services and rpc methods, with comments stripped.

A commented-out ``service`` or ``rpc`` is not a contract, so the text is cleaned
before it is parsed. Service bodies are brace-matched rather than regex-matched,
so a nested block cannot leak one service's rpcs into another's.

Standard library only; reads ``*.proto`` under the configured root.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

PROTO_PACKAGE_PATTERN: Final = re.compile(r"^package\s+([\w.]+)\s*;", re.MULTILINE)
PROTO_SERVICE_PATTERN: Final = re.compile(r"^service\s+(\w+)\s*\{", re.MULTILINE)
PROTO_RPC_PATTERN: Final = re.compile(r"\brpc\s+(\w+)\s*\(")
PROTO_BLOCK_COMMENT: Final = re.compile(r"/\*.*?\*/", re.DOTALL)
PROTO_LINE_COMMENT: Final = re.compile(r"//[^\n]*")


def proto_text(source: Path) -> str:
    """Read a proto file with comments removed, so a commented-out block is not a contract."""
    text = source.read_text(encoding="utf-8")
    without_blocks = PROTO_BLOCK_COMMENT.sub("", text)
    return PROTO_LINE_COMMENT.sub("", without_blocks)


def service_bodies(text: str) -> list[tuple[str, str]]:
    """Every ``service`` name with the text inside its braces (brace-matched)."""
    bodies: list[tuple[str, str]] = []
    for match in PROTO_SERVICE_PATTERN.finditer(text):
        start = match.end()
        depth = 1
        index = start
        while index < len(text) and depth:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1
        bodies.append((match.group(1), text[start : index - 1]))
    return bodies


def _proto_package(text: str) -> str:
    package_match = PROTO_PACKAGE_PATTERN.search(text)
    return package_match.group(1) if package_match else ""


def _service_name(package: str, name: str) -> str:
    return f"{package}.{name}" if package else name


def _file_services(source: Path) -> dict[str, Path]:
    text = proto_text(source)
    package = _proto_package(text)
    return {_service_name(package, name): source for name, _body in service_bodies(text)}


def proto_services(proto_root: Path) -> dict[str, Path]:
    """Map fully-qualified protobuf service name to its source file."""
    services: dict[str, Path] = {}
    if not proto_root.is_dir():
        return services
    for source in sorted(proto_root.rglob("*.proto")):
        services.update(_file_services(source))
    return services


def _service_rpc_keys(package: str, name: str, body: str) -> list[str]:
    service = _service_name(package, name)
    return [f"{service}.{rpc}" for rpc in PROTO_RPC_PATTERN.findall(body)]


def _file_rpc_methods(source: Path) -> dict[str, Path]:
    text = proto_text(source)
    package = _proto_package(text)
    methods: dict[str, Path] = {}
    for name, body in service_bodies(text):
        for key in _service_rpc_keys(package, name, body):
            methods[key] = source
    return methods


def proto_rpc_methods(proto_root: Path) -> dict[str, Path]:
    """Map a fully-qualified rpc name to the proto file that declares it."""
    methods: dict[str, Path] = {}
    if not proto_root.is_dir():
        return methods
    for source in sorted(proto_root.rglob("*.proto")):
        methods.update(_file_rpc_methods(source))
    return methods
