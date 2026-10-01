# Problem Statement

Conventional IoT security often relies on static device authentication and fragmented monitoring, while AIoT
systems increasingly combine physical sensors, machine learning and network connectivity. A device that proved its
identity once can still be opened, reconfigured or used against its surroundings.

This creates a need for security architectures that can:
- Continuously evaluate device trust across cyber and physical signals.
- Remain resilient against future quantum threats where it matters for long-lived evidence.
- Detect compromised or manipulated devices from independent, authenticated evidence.
- Preserve trustworthy, tamper-evident security evidence.
- Contain a compromised device and recover it from defined classes of compromise.

## Solution

**Q-SHIELD** continuously re-scores every device from independent evidence:
- cryptographic identity
- the physical tamper switch
- sensor ranges
- configuration integrity
- network liveness
- signed camera observations

The gateway quarantines a device when that evidence turns against it, and records every decision in an ML-DSA-65
signed, SHA-256 linked evidence chain. The device is restored only after an operator-started, verified recovery
rebuilds its trust.

Post-quantum cryptography (ML-KEM-768 and ML-DSA-65) protects the vision-evidence path and the evidence chain. The
device path uses HMAC-SHA256, which is not post-quantum.
