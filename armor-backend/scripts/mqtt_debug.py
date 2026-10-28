"""
ARMOR - MQTT Debug Utility
--------------------------
Subscribes to machinocare/v1/# and prints every message with timing so you can
verify the ESP is sending clean data and measure end-to-end latency.

Usage:
    python scripts/mqtt_debug.py                    # default broker localhost:1883
    python scripts/mqtt_debug.py 192.168.1.42 1883  # remote broker
    python scripts/mqtt_debug.py --log mqtt_debug.log

Output columns:
    [recv_ts]  topic  payload  inter_arrival_ms  latency_ms (recv - payload_ts)
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed. Run: pip install paho-mqtt")
    sys.exit(1)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_payload_ts(payload: dict) -> int | None:
    """Return epoch milliseconds, or None when the payload has no wall clock.

    Small integers are uptime counters (millis()), which cannot be compared
    against the receiver's clock and must not be reported as latency.
    """
    ts = payload.get("timestamp")
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        v = float(ts)
        if v > 1e12:       # epoch milliseconds
            return int(v)
        if v > 1e9:        # epoch seconds
            return int(v * 1000)
        return None        # uptime / millis -> not a wall-clock time
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except ValueError:
            try:
                v = float(ts)
            except ValueError:
                return None
            if v > 1e12:
                return int(v)
            if v > 1e9:
                return int(v * 1000)
            return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="ARMOR MQTT debug subscriber")
    parser.add_argument("broker", nargs="?", default="localhost", help="MQTT broker host")
    parser.add_argument("port", nargs="?", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--topic", default="machinocare/v1/#", help="Topic filter")
    parser.add_argument("--log", default=None, help="Append raw messages to a log file")
    args = parser.parse_args()

    last_recv: dict[str, int] = {}
    counts: dict[str, int] = {}
    log_fh = open(args.log, "a", encoding="utf-8") if args.log else None

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            print(f"[MQTT] Connected to {args.broker}:{args.port}")
            client.subscribe(args.topic, qos=1)
            print(f"[MQTT] Subscribed to {args.topic}")
            print("-" * 80)
        else:
            print(f"[MQTT] Connection failed, rc={rc}")

    def on_message(client, userdata, msg):
        now = _now_ms()
        topic = msg.topic
        raw = msg.payload.decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
            pretty = json.dumps(payload, separators=(",", ":"))
        except json.JSONDecodeError:
            payload = None
            pretty = raw

        # inter-arrival
        inter = now - last_recv.get(topic, now)
        last_recv[topic] = now

        # latency: recv - payload timestamp
        latency_str = ""
        if payload is not None:
            pts = _parse_payload_ts(payload)
            if pts is not None:
                lat = now - pts
                latency_str = f"  latency={lat}ms"

        counts[topic] = counts.get(topic, 0) + 1
        ts_str = datetime.fromtimestamp(now / 1000, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]

        line = f"[{ts_str}] {topic}  inter={inter}ms{latency_str}  #{counts[topic]}\n  {pretty}"
        print(line)
        if log_fh:
            log_fh.write(line + "\n")
            log_fh.flush()

    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="armor-mqtt-debug")
    else:
        client = mqtt.Client(client_id="armor-mqtt-debug")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, args.port, keepalive=60)

    print(f"[MQTT-DEBUG] Broker: {args.broker}:{args.port}  Topic: {args.topic}")
    print("Press Ctrl+C to stop.\n")

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[MQTT-DEBUG] Stopped.")
        print("Message counts:", counts)
    finally:
        if log_fh:
            log_fh.close()


if __name__ == "__main__":
    main()
