"""Normalize rustic JSON progress and present shared Qt/Plasma live metrics.

bytes_done counts processed source bytes, including unchanged/deduplicated files.
It does not measure compressed repository writes or physical network traffic.
"""

import datetime as dt
import math
import re
import time
from collections import deque

from .i18n import language, tr

STALE_SECONDS = 3.0
COUNTERS = {
    "seconds_elapsed", "seconds_remaining", "percent_done", "total_bytes", "bytes_done",
    "files_new", "files_changed", "files_unmodified", "dirs_new", "dirs_changed", "dirs_unmodified",
    "data_blobs", "tree_blobs", "data_added", "data_added_packed", "total_files_processed",
    "total_bytes_processed", "total_duration",
}


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


class ProgressTracker:
    def __init__(self):
        self.started = time.monotonic()
        self.samples = deque([(self.started, 0)])
        self.value = {}

    def feed(self, event):
        kind = event.get("message_type")
        if kind not in ("status", "summary"):
            return None  # Diagnostic JSON must not replace the latest byte counters.
        # Only protocol metadata is persisted. Numbers and snapshot hashes are
        # not password text, and redacting them would corrupt legitimate progress
        # whenever a short password happens to match a digit or a JSON key.
        snapshot = event.get("snapshot_id")
        event = {key: value for key, value in event.items() if key in COUNTERS and number(value) is not None}
        event["message_type"] = kind
        if isinstance(snapshot, str) and re.fullmatch(r"[a-f0-9]{8,64}", snapshot):
            event["snapshot_id"] = snapshot
        stamp = time.monotonic()
        done = number(event.get("bytes_done"))
        total = number(event.get("total_bytes"))
        elapsed = number(event.get("seconds_elapsed"))
        if kind == "summary":
            done = total = number(event.get("total_bytes_processed"))
            elapsed = number(event.get("total_duration"))
        previous_done = number(self.value.get("bytes_done"))
        previous_elapsed = number(self.value.get("seconds_elapsed"))
        if kind == "status" and (
            (done is not None and previous_done is not None and done < previous_done)
            or (elapsed is not None and previous_elapsed is not None and elapsed < previous_elapsed)
        ):
            self.samples.clear()  # A new byte progress phase; never reuse its predecessor's rate.
            self.value = {}
        value = {**self.value, **event, "updated_at_epoch": time.time()}
        if done is not None:
            value["bytes_done"] = done
            self.samples.append((stamp, done))
            while len(self.samples) > 2 and self.samples[1][0] < stamp - 4:
                self.samples.popleft()
            age = stamp - self.samples[0][0]
            value["bytes_per_second"] = max(0, (done - self.samples[0][1]) / age) if age > 0 else None
        if total is not None:
            value["total_bytes"] = total
        # A summary retains the last status counters and snapshot confirmation.
        # No summary ever makes an operation successful by itself; Engine still
        # checks rustic's exit status and warnings before recording last_success.
        if kind == "summary" and done is not None:
            value["percent_done"] = 1.0
            value["bytes_per_second"] = 0
        else:
            percent = number(event.get("percent_done"))
            if percent is None and done is not None and total:
                percent = done / total
            if percent is not None:
                value["percent_done"] = min(1.0, percent)
        if elapsed is not None:
            value["seconds_elapsed"] = elapsed
        self.value = value
        return value


def human_size(value):
    if number(value) is None:
        return "–"
    value = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024


def duration(seconds):
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def progress_view(row, now_epoch=None):
    """Poll-time formatting keeps elapsed time live even while rustic is silent."""
    now_epoch = time.time() if now_epoch is None else now_epoch
    value = row.get("progress") or {}
    active = row.get("status") == "running" and row.get("phase") in ("backup", "dry-run", "restore", "check")
    percent = number(value.get("percent_done"))
    done, total = number(value.get("bytes_done")), number(value.get("total_bytes"))
    if percent is None and done is not None and total:
        percent = done / total
    if percent is not None:
        percent = min(1.0, percent)
    if done is None:
        detail = tr("Warte auf Fortschrittsdaten …")
    else:
        detail = tr("Verarbeitet: {p0} / {p1}", p0=human_size(done), p1=human_size(total)) if total is not None else tr("Verarbeitet: {p0} · Gesamtgröße wird ermittelt …", p0=human_size(done))
    if percent is not None:
        percentage = f"{percent * 100:.1f}"
        if language() == "de":
            percentage = percentage.replace(".", ",")
        detail = percentage + " % · " + detail
    updated = number(value.get("updated_at_epoch"))
    fresh = updated is not None and 0 <= now_epoch - updated <= STALE_SECONDS
    rate = number(value.get("bytes_per_second")) if fresh else None
    speed = tr("Verarbeitung: {p0}", p0=human_size(rate) + "/s" if rate is not None else "–")
    elapsed = number(value.get("seconds_elapsed")) or 0
    try:
        elapsed = max(0, now_epoch - dt.datetime.fromisoformat(row["started_at"]).timestamp())
    except (KeyError, TypeError, ValueError):
        if updated is not None:
            elapsed += max(0, now_epoch - updated)
    timing = tr("Verstrichen: {p0}", p0=duration(elapsed))
    remaining = number(value.get("seconds_remaining"))
    if fresh and remaining is not None and percent != 1 and total:
        timing += " · " + tr("Verbleibend: ca. {p0}", p0=duration(remaining))
    return {
        "active": active,
        "percent": percent,
        "detail": detail,
        "speed": speed,
        "timing": timing,
        "speed_hint": tr("Verarbeitete Quelldaten pro Sekunde, einschließlich unveränderter Dateien. Durch Deduplizierung und Kompression kann die tatsächliche Netzwerkübertragung kleiner sein."),
    }
