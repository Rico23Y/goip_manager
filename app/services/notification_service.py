from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.core.goip_status import NETWORK_LABEL, signal_to_level, status_map


class NotificationService:
    """Evaluate GOIP notification rules and suppress repeated alerts."""

    def __init__(
        self,
        notify_user: Callable[[str, str, int], None],
    ) -> None:
        self._notify_user = notify_user
        self._settings: dict[str, Any] = {}
        self._last_sim_status: dict[str, dict[int, Any]] = defaultdict(dict)
        self._last_network_count: dict[str, int | None] = defaultdict(
            lambda: None
        )
        self._last_signal_alert: dict[str, Any] = defaultdict(lambda: None)

    def update_settings(self, settings: dict[str, Any]) -> None:
        """Replace the active notification settings."""
        self._settings = settings

    def check_for_notifications(
        self,
        goip: str,
        data: list[list[Any]],
    ) -> None:
        """Evaluate the active rules against one GOIP device's port data."""
        settings = self._settings
        if not settings.get("enabled", False):
            return

        # SIM status alerts
        sim_config = settings.get("sim_status", {})
        if sim_config.get("enabled", False):
            sim_alerts = sim_config.get("values", [])
            for idx, row in enumerate(data):
                sim_status = row[0]
                if (
                    sim_status in sim_alerts
                    and sim_status != self._last_sim_status[goip].get(idx)
                ):
                    sim_text = status_map.get(
                        sim_status, f"Code {sim_status}"
                    )
                    self._notify_user(
                        f"{goip} port {idx + 1}{row[3]} - {sim_text}",
                        goip,
                        idx,
                    )
                    self._last_sim_status[goip][idx] = sim_status

        # Network type alerts
        net_config = settings.get("network_type", {})
        if net_config.get("enabled", False):
            values = net_config.get("values", [])
            operator = net_config.get("operator", ">")
            count_threshold = net_config.get("count", 0)
            match_count = sum(
                1 for row in data if NETWORK_LABEL[row[2]] in values
            )

            if match_count != self._last_network_count[goip]:
                if operator == ">" and match_count > count_threshold:
                    self._notify_user(
                        f"{goip} network {values} is greater than "
                        f"{count_threshold}: {match_count}/{len(data)}",
                        goip,
                        -1,
                    )
                elif operator == "<" and match_count < count_threshold:
                    self._notify_user(
                        f"{goip} network {values} is less than "
                        f"{count_threshold}: {match_count}/{len(data)}",
                        goip,
                        -1,
                    )
                self._last_network_count[goip] = match_count

        # Signal alerts
        signal_config = settings.get("signal", {})
        if signal_config.get("enabled", False):
            bar_conf = signal_config.get("bar", {})
            custom_conf = signal_config.get("custom", {})
            total_ports = len(data)

            # Bar mode
            if bar_conf.get("enabled", False):
                bar_values = bar_conf.get("values", [])
                for bar in bar_values:
                    count = sum(
                        1
                        for row in data
                        if signal_to_level(str(row[1])) == bar
                    )
                    # Preserve the existing configuration source.
                    op = custom_conf.get("operator", ">")
                    count_thresh = custom_conf.get("count", 0)
                    key = ("bar", bar, count)

                    if key != self._last_signal_alert[goip]:
                        if op == ">" and count > count_thresh:
                            self._notify_user(
                                f"{goip} bar {bar} signal > {count_thresh}: "
                                f"{count}/{total_ports}",
                                goip,
                                -1,
                            )
                            self._last_signal_alert[goip] = key
                        elif op == "<" and count < count_thresh:
                            self._notify_user(
                                f"{goip} bar {bar} signal < {count_thresh}: "
                                f"{count}/{total_ports}",
                                goip,
                                -1,
                            )
                            self._last_signal_alert[goip] = key

            # Custom signal mode
            if custom_conf.get("enabled", False):
                min_val = custom_conf.get("min", 0)
                max_val = custom_conf.get("max", 0)
                op = custom_conf.get("operator", ">")
                count_thresh = custom_conf.get("count", 0)
                match_count = 0

                for row in data:
                    try:
                        strength = int(row[1])
                        if min_val <= strength <= max_val:
                            match_count += 1
                    except Exception:
                        continue

                key = ("custom", min_val, max_val, match_count)
                if key != self._last_signal_alert[goip]:
                    if op == ">" and match_count > count_thresh:
                        self._notify_user(
                            f"{goip} Signal {min_val}-{max_val} > "
                            f"{count_thresh}: {match_count}/{total_ports}",
                            goip,
                            -1,
                        )
                        self._last_signal_alert[goip] = key
                    elif op == "<" and match_count < count_thresh:
                        self._notify_user(
                            f"{goip} Signal {min_val}-{max_val} < "
                            f"{count_thresh}: {match_count}/{total_ports}",
                            goip,
                            -1,
                        )
                        self._last_signal_alert[goip] = key