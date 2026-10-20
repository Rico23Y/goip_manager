import time

from app.models.goip_device import GoipDevice


def scrape_goip_data(device: GoipDevice, session):
    """Retrieve and parse port-status data from a GOIP device."""
    ip = device.ip_address
    data_url = f"http://{ip}/get_parameter.html"

    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = "type=updatePortStatusDetail"

    try:
        data_resp = session.post(
            data_url,
            headers=headers,
            data=payload,
            timeout=5,
        )
        data_json = data_resp.json()
    except Exception as e:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"({ip}) Failed to retrieve or parse port data: {e}"
        )
        return None

    result = []
    for row in data_json.get("data", []):
        try:
            signal = row[7]
            network = row[9]
            portChannel = row[2]
            simStatus = row[13]
            statusDuration = row[14]

            if signal == "":
                network = 0

            result.append(
                [simStatus, signal, network, portChannel, statusDuration]
            )
        except IndexError:
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"({ip}) Skipped malformed row: {row}"
            )
            continue

    return result
