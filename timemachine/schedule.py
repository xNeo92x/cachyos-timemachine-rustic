"""Calendar controls for systemd user timers, preserving custom expressions."""

import re

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QSpinBox, QTimeEdit, QWidget

from .i18n import tr

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ALIASES = {
    "hourly": "*-*-* *:00:00",
    "daily": "*-*-* 00:00:00",
    "weekly": "Mon *-*-* 00:00:00",
    "monthly": "*-*-01 00:00:00",
    "yearly": "*-01-01 00:00:00",
    "annually": "*-01-01 00:00:00",
}


def parse_schedule(expression):
    """Recognize editable schedules; leave ranges, timezones and other syntax intact."""
    if not expression:
        return {"mode": "manual"}
    text = ALIASES.get(expression.strip(), expression.strip())
    match = re.fullmatch(
        r"(?:(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+)?\*-(\*|\d{1,2})-(\*|\d{1,2})"
        r"\s+(\*|\d{1,2}):(\d{1,2})(?::(\d{1,2}))?",
        text,
    )
    if match:
        weekday, month, day, hour, minute, second = match.groups()
        minute = int(minute)
        if 0 <= minute < 60 and int(second or 0) == 0:
            if hour == "*" and month == day == "*" and weekday is None:
                return {"mode": "hourly", "minute": minute}
            if hour != "*" and QTime(int(hour), minute).isValid():
                values = {"time": QTime(int(hour), minute)}
                if month == day == "*":
                    return (
                        dict(values, mode="weekly", weekday=WEEKDAYS.index(weekday))
                        if weekday
                        else dict(values, mode="daily")
                    )
                if weekday is None and day != "*":
                    if month == "*" and 1 <= int(day) <= 31:
                        return dict(values, mode="monthly", day=int(day))
                    if month != "*" and QDate(2000, int(month), int(day)).isValid():
                        return dict(values, mode="yearly", month=int(month), day=int(day))
    return {"mode": "custom"}


class ScheduleEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.loading = True
        self.dirty = False
        self.original = ""
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.frequency = QComboBox()
        for title, mode in [
            (tr("Nur manuell"), "manual"),
            (tr("Stündlich"), "hourly"),
            (tr("Täglich"), "daily"),
            (tr("Wöchentlich"), "weekly"),
            (tr("Monatlich"), "monthly"),
            (tr("Jährlich"), "yearly"),
            (tr("Benutzerdefiniert (systemd)"), "custom"),
        ]:
            self.frequency.addItem(title, mode)
        self.form.addRow(tr("Häufigkeit"), self.frequency)
        self.time = QTimeEdit(QTime(3, 0))
        self.time.setDisplayFormat("HH:mm")
        self.form.addRow(tr("Uhrzeit"), self.time)
        self.minute = QSpinBox()
        self.minute.setRange(0, 59)
        self.form.addRow(tr("Minute jeder Stunde"), self.minute)
        self.weekday = QComboBox()
        self.weekday.addItems(
            [tr("Montag"), tr("Dienstag"), tr("Mittwoch"), tr("Donnerstag"), tr("Freitag"), tr("Samstag"), tr("Sonntag")]
        )
        self.form.addRow(tr("Wochentag"), self.weekday)
        self.month = QComboBox()
        self.month.addItems(
            [
                tr("Januar"),
                tr("Februar"),
                tr("März"),
                "April",
                tr("Mai"),
                tr("Juni"),
                tr("Juli"),
                "August",
                "September",
                tr("Oktober"),
                "November",
                tr("Dezember"),
            ]
        )
        self.form.addRow(tr("Monat"), self.month)
        self.day = QSpinBox()
        self.day.setRange(1, 31)
        self.form.addRow(tr("Tag im Monat"), self.day)
        self.custom = QLineEdit()
        self.custom.setPlaceholderText(tr("z. B. Mon..Fri *-*-* 08:00:00"))
        self.form.addRow(tr("Kalenderausdruck"), self.custom)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.form.addRow(self.note)
        for signal in (
            self.frequency.currentIndexChanged,
            self.time.timeChanged,
            self.minute.valueChanged,
            self.weekday.currentIndexChanged,
            self.month.currentIndexChanged,
            self.day.valueChanged,
            self.custom.textChanged,
        ):
            signal.connect(self.changed)
        self.set_schedule("")

    def changed(self, *_):
        if not self.loading:
            self.dirty = True
        mode = self.frequency.currentData()
        self.day.setMaximum(
            QDate(2000, self.month.currentIndex() + 1, 1).daysInMonth() if mode == "yearly" else 31
        )
        for widget, visible in [
            (self.time, mode in ("daily", "weekly", "monthly", "yearly")),
            (self.minute, mode == "hourly"),
            (self.weekday, mode == "weekly"),
            (self.month, mode == "yearly"),
            (self.day, mode in ("monthly", "yearly")),
            (self.custom, mode == "custom"),
        ]:
            widget.setVisible(visible)
            self.form.labelForField(widget).setVisible(visible)
        note = tr("Uhrzeiten gelten in der lokalen Zeitzone.")
        if mode == "manual":
            note = tr("Sicherungen werden nur auf Anfrage gestartet.")
        elif mode == "custom":
            note = tr("Bestehende besondere Zeitpläne bleiben unverändert.")
        elif mode == "monthly" and self.day.value() > 28:
            note += tr(" In Monaten ohne diesen Tag entfällt der Lauf.")
        elif mode == "yearly" and self.month.currentIndex() == 1 and self.day.value() == 29:
            note += tr(" Der 29. Februar kommt nur in Schaltjahren vor.")
        self.note.setText(note)

    def set_schedule(self, expression):
        self.loading = True
        self.original = expression
        values = parse_schedule(expression)
        self.frequency.setCurrentIndex(self.frequency.findData(values["mode"]))
        self.time.setTime(values.get("time", QTime(3, 0)))
        self.minute.setValue(values.get("minute", 0))
        self.weekday.setCurrentIndex(values.get("weekday", 0))
        self.month.setCurrentIndex(values.get("month", 1) - 1)
        self.day.setValue(values.get("day", 1))
        self.custom.setText(expression)
        self.changed()
        self.loading = False
        self.dirty = False

    def schedule(self):
        if not self.dirty:
            return self.original
        mode = self.frequency.currentData()
        clock = self.time.time().toString("HH:mm") + ":00"
        if mode == "manual":
            return ""
        if mode == "custom":
            return self.custom.text().strip()
        if mode == "hourly":
            return f"*-*-* *:{self.minute.value():02}:00"
        if mode == "daily":
            return f"*-*-* {clock}"
        if mode == "weekly":
            return f"{WEEKDAYS[self.weekday.currentIndex()]} *-*-* {clock}"
        if mode == "monthly":
            return f"*-*-{self.day.value():02} {clock}"
        return f"*-{self.month.currentIndex() + 1:02}-{self.day.value():02} {clock}"
