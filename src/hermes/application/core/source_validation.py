"""Validation for the small set of remote learning sources Hermes supports."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def validate_learning_source(source: str) -> str | None:
    """Return an error message, or None when a source is acceptable."""
    value = (source or "").strip()
    if not value.lower().startswith(("http://", "https://")):
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return "Link không hợp lệ."
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "Chỉ hỗ trợ link HTTP/HTTPS hợp lệ."
    if parsed.username or parsed.password:
        return "Link chứa thông tin đăng nhập và bị từ chối."
    if parsed.port not in (None, 80, 443):
        return "Link dùng cổng mạng không được hỗ trợ."
    return validate_public_url(value)


def validate_public_url(source: str) -> str | None:
    """Reject local/private network targets before any learning-source fetch."""
    try:
        parsed = urlparse((source or "").strip())
        host = (parsed.hostname or "").strip().lower()
    except ValueError:
        return "Link không hợp lệ."
    if parsed.scheme not in {"http", "https"} or not host:
        return "Chỉ hỗ trợ link HTTP/HTTPS hợp lệ."
    if parsed.username or parsed.password:
        return "Link chứa thông tin đăng nhập và bị từ chối."
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        return "Link trỏ vào máy nội bộ và bị từ chối."
    try:
        addresses = {
            item[4][0].split("%", 1)[0]
            for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        }
    except socket.gaierror:
        return "Không thể phân giải tên miền của link."
    if not addresses:
        return "Không thể xác định địa chỉ mạng của link."
    for address in addresses:
        try:
            if not ipaddress.ip_address(address).is_global:
                return "Link trỏ vào mạng nội bộ/private và bị từ chối."
        except ValueError:
            return "Link có địa chỉ mạng không hợp lệ."
    return None
