# Loaded via PYTHONPATH for runs of OLD code that lacks LLM_FORCE_IPV4.
# Same fix as ami/llm.py: prefer IPv4 (IPv6 to the proxy is black-holed here).
import socket
_orig = socket.getaddrinfo
def _ipv4_first(host, *a, **k):
    found = _orig(host, *a, **k)
    return [x for x in found if x[0] == socket.AF_INET] or found
socket.getaddrinfo = _ipv4_first
