import ipaddress
import socket
import urllib.parse
from typing import Callable, Sequence
from hermes.domain.web_document import UnsafeWebUrl

DEFAULT_BLOCKED_SUFFIXES = (
    "shopee.vn",
    "shopee.com",
    "tiktok.com",
    "douyin.com",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "instagram.com",
)


def default_resolver(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, None)
        ips = set()
        for info in infos:
            sockaddr = info[4]
            if sockaddr:
                ips.add(sockaddr[0])
        return list(ips)
    except Exception as e:
        raise UnsafeWebUrl(f"DNS resolution failed for '{hostname}': {e}")


class PublicWebUrlPolicy:
    def __init__(
        self,
        resolver: Callable[[str], Sequence[str]] | None = None,
        blocked_suffixes: Sequence[str] = DEFAULT_BLOCKED_SUFFIXES,
    ):
        self.resolver = resolver or default_resolver
        self.blocked_suffixes = tuple(s.lower() for s in blocked_suffixes)

    def validate(self, url: str) -> str:
        if not url or not isinstance(url, str):
            raise UnsafeWebUrl("URL must be a non-empty string.")

        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as e:
            raise UnsafeWebUrl(f"Invalid URL structure: {e}")

        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            raise UnsafeWebUrl(f"Unsupported scheme '{scheme}'. Only http and https are allowed.")

        if parsed.username or parsed.password:
            raise UnsafeWebUrl("Credentials in URLs are not allowed.")

        port = parsed.port
        if port is not None:
            if scheme == "http" and port != 80:
                raise UnsafeWebUrl(f"Nonstandard port '{port}' for HTTP URL.")
            if scheme == "https" and port != 443:
                raise UnsafeWebUrl(f"Nonstandard port '{port}' for HTTPS URL.")

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise UnsafeWebUrl("Missing hostname in URL.")

        for suffix in self.blocked_suffixes:
            if hostname == suffix or hostname.endswith("." + suffix):
                raise UnsafeWebUrl(f"Host '{hostname}' is in blocked hosts policy.")

        # Resolve IP or parse if hostname is raw IP
        try:
            raw_ip = ipaddress.ip_address(hostname)
            ips = [str(raw_ip)]
        except ValueError:
            # It's a hostname, resolve via DNS
            resolved = self.resolver(hostname)
            if not resolved:
                raise UnsafeWebUrl(f"No IP addresses resolved for hostname '{hostname}'.")
            ips = list(resolved)

        for ip_str in ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
            except ValueError:
                raise UnsafeWebUrl(f"Invalid IP address '{ip_str}' resolved for host '{hostname}'.")

            if not ip_obj.is_global or ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved or ip_obj.is_unspecified:
                raise UnsafeWebUrl(f"Resolved IP '{ip_str}' for host '{hostname}' is not globally routable.")

        # Reconstruct normalized URL dropping fragment
        normalized_parts = (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "",
            parsed.params or "",
            parsed.query or "",
            "",  # drop fragment
        )
        return urllib.parse.urlunparse(normalized_parts)

    def validate_redirect(self, current_url: str, target_url: str) -> str:
        resolved_target = urllib.parse.urljoin(current_url, target_url)
        return self.validate(resolved_target)
