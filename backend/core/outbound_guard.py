"""统一出站请求安全校验（ref #2）。

服务端会向用户可控的地址发起请求：LLM ``base_url``、企业微信/飞书
``webhook_url``、SMTP 主机。若不做校验，任意注册用户可把请求打向内网 /
云元数据，或把系统默认 LLM Key 带到自己的服务器。

策略：
  - URL 只允许 https；拒绝 URL 内嵌凭据、IP 字面量（除非显式列入白名单）
  - 实时解析 DNS，任一 A/AAAA 记录落到私网 / 环回 / 链路本地 / 保留地址即拒绝
  - 可选 ``OUTBOUND_HOST_ALLOWLIST`` 域名白名单（逗号分隔，支持 ``*.example.com``）
  - 调用方必须同时设置 ``allow_redirects=False``，否则重定向会绕过本校验

残留风险：DNS rebinding 的 TOCTOU 窗口无法仅靠应用层校验彻底消除，
彻底封堵需要出站代理或把连接固定到已校验 IP。本模块每次请求前实时解析，
把窗口压到最小，且不缓存解析结果。
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from urllib.parse import urlsplit, urlunsplit


class OutboundPolicyError(ValueError):
    """出站目标不满足安全策略。"""


_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
_DEFAULT_PORT = 443


def _allowlist() -> list[str]:
    raw = os.getenv("OUTBOUND_HOST_ALLOWLIST", "").strip()
    return [item.strip().lower().lstrip("*.") for item in raw.split(",") if item.strip()]


def _host_matches(host: str, entry: str) -> bool:
    return host == entry or host.endswith("." + entry)


def _is_public_ip(text: str) -> bool:
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return False
    return bool(
        addr.is_global
        and not addr.is_private
        and not addr.is_loopback
        and not addr.is_link_local
        and not addr.is_reserved
        and not addr.is_multicast
        and not addr.is_unspecified
    )


def _resolve_public_ips(host: str, port: int | None) -> list[str]:
    """实时解析并校验所有返回地址；解析失败一律拒绝（fail-closed）。"""
    try:
        infos = socket.getaddrinfo(host, port or _DEFAULT_PORT, 0, socket.SOCK_STREAM)
    except OSError as exc:
        raise OutboundPolicyError(f"目标主机 {host} 解析失败，已拒绝出站请求") from exc

    ips: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    if not ips:
        raise OutboundPolicyError(f"目标主机 {host} 无可用解析结果，已拒绝出站请求")
    for ip in ips:
        if not _is_public_ip(ip):
            raise OutboundPolicyError(f"目标主机 {host} 解析到受限网络地址，已拒绝出站请求")
    return ips


def _validate_host(host: str, port: int | None) -> str:
    host = (host or "").strip().lower().rstrip(".")
    if not host or len(host) > 253 or not _HOSTNAME_RE.match(host):
        raise OutboundPolicyError("目标主机格式无效")

    entries = _allowlist()
    try:
        ipaddress.ip_address(host)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False
    # IP 字面量可绕过域名白名单，且常用于内网/元数据探测，默认一律拒绝。
    if is_ip_literal and host not in entries:
        raise OutboundPolicyError("不接受 IP 字面量作为出站目标")
    if entries and not any(_host_matches(host, entry) for entry in entries):
        raise OutboundPolicyError(f"目标主机 {host} 不在出站白名单内")

    _resolve_public_ips(host, port)
    return host


def validate_outbound_host(host: str, port: int | None = None) -> str:
    """校验 SMTP / 自定义服务的主机名，返回规范化主机名。"""
    if port is not None and (not isinstance(port, int) or not 1 <= port <= 65535):
        raise OutboundPolicyError("目标端口无效")
    return _validate_host(host, port)


def validate_outbound_url(url: str) -> str:
    """校验 https 出站 URL，返回去掉 fragment 的规范化 URL。"""
    raw = (url or "").strip()
    if not raw:
        raise OutboundPolicyError("出站 URL 不能为空")
    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise OutboundPolicyError("出站 URL 格式无效") from exc

    if parts.scheme.lower() != "https":
        raise OutboundPolicyError("出站请求仅支持 https")
    if parts.username or parts.password:
        raise OutboundPolicyError("出站 URL 不允许内嵌凭据")
    try:
        port = parts.port
    except ValueError as exc:
        raise OutboundPolicyError("出站 URL 端口无效") from exc

    _validate_host(parts.hostname, port)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
