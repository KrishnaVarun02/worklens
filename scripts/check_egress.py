#!/usr/bin/env python3
"""Run INSIDE api and worker to verify direct outbound access is denied."""

import socket
import sys

unexpected = []
for host, port in [("1.1.1.1", 443), ("8.8.8.8", 53), ("2606:4700:4700::1111", 443)]:
    try:
        with socket.create_connection((host, port), timeout=2):
            unexpected.append(f"{host}:{port}")
    except OSError:
        pass
if unexpected:
    print("FAIL: unexpected direct egress:", ", ".join(unexpected))
    sys.exit(1)
print("PASS: tested IPv4/IPv6 outbound connections blocked. Also review host firewall/DNS policy.")
