
"""GOIP status mappings and signal-strength conversion."""

NETWORK_LABEL: list[str] = ["NA", "", "2G", "3G", "4G", "5G"]

STATUS_MAP: dict[int, str] = {
    0: "No Card Detected",
    1: "Card Detected",
    2: "Registering Card",
    3: "Register OK",
    4: "Calling",
    5: "No Balance",
    6: "Register Failed",
    7: "Locked",
    8: "Locked By Operator",
    9: "SIM Problem",
    10: "Locked",
    11: "Card Inserted",
    12: "Locked By User",
    13: "Inter-Calling",
    14: "Inter-Calling Holding",
    15: "Access Mobile Network",
    16: "Response Timeout",
    99: "Module Problem",
}

# Preserve the existing lowercase name used by the application.
status_map = STATUS_MAP


def signal_to_level(signal_str: str) -> int:
    """Convert a GOIP signal value into a display level from 0 to 5.

    Return -1 when the signal value is empty.
    """
    if signal_str == "":
        return -1

    signal = int(signal_str)

    if signal <= 4 or signal > 31:
        return 0
    if signal <= 8:
        return 1
    if signal <= 13:
        return 2
    if signal <= 18:
        return 3
    if signal <= 24:
        return 4
    return 5
