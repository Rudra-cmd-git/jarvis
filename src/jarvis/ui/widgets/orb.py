"""Animated JARVIS visualizer.

Pure QPainter: a soft core, three counter-rotating arcs and a reactive
waveform. Animations can be disabled for low-spec machines.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient, QPen
from PySide6.QtWidgets import QWidget

from jarvis.ui import theme

_STATE_COLORS = {
    "idle": theme.CYAN,
    "listening": theme.OK,
    "thinking": "#5aa9ff",
    "working": theme.WARN,
    "speaking": theme.CYAN,
    "stopped": theme.DANGER,
}


class OrbWidget(QWidget):
    def __init__(self, parent: QWidget | None = None, animations: bool = True) -> None:
        super().__init__(parent)
        self._state = "idle"
        self._level = 0.0
        self._phase = 0.0
        self._pulse = 0.0
        self._animations = animations
        self.setMinimumSize(180, 180)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33 if animations else 120)

    # ------------------------------------------------------------------- state
    def set_state(self, state: str) -> None:
        self._state = state if state in _STATE_COLORS else "idle"
        self.update()

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, float(level)))
        self.update()

    def set_animations(self, enabled: bool) -> None:
        self._animations = enabled
        self._timer.setInterval(33 if enabled else 120)

    @property
    def state(self) -> str:
        return self._state

    # ------------------------------------------------------------------ drawing
    def _tick(self) -> None:
        if self._animations:
            self._phase = (self._phase + 0.035) % (math.tau)
        self._pulse = (self._pulse + 0.05) % math.tau
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        width, height = self.width(), self.height()
        center_x, center_y = width / 2, height / 2
        base_radius = min(width, height) * 0.27
        color = QColor(_STATE_COLORS[self._state])

        # Ambient halo (three cheap concentric circles, no blur).
        for index, spread in enumerate((1.9, 1.55, 1.28)):
            alpha = 12 + index * 8
            halo = QColor(color)
            halo.setAlpha(alpha)
            painter.setBrush(halo)
            painter.setPen(Qt.NoPen)
            radius = base_radius * spread
            painter.drawEllipse(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2))

        # Core.
        pulse = 1.0 + (0.035 * math.sin(self._pulse) if self._animations else 0.0)
        if self._state in {"listening", "speaking"}:
            pulse += self._level * 0.08
        core_radius = base_radius * pulse
        gradient = QRadialGradient(center_x, center_y, core_radius)
        inner = QColor(color)
        inner.setAlpha(235)
        outer = QColor(color)
        outer.setAlpha(18)
        gradient.setColorAt(0.0, inner)
        gradient.setColorAt(0.55, QColor(color.red(), color.green(), color.blue(), 90))
        gradient.setColorAt(1.0, outer)
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(center_x - core_radius, center_y - core_radius, core_radius * 2, core_radius * 2))

        # Inner ring.
        painter.setBrush(Qt.NoBrush)
        ring_pen = QPen(QColor(color.red(), color.green(), color.blue(), 200))
        ring_pen.setWidthF(1.4)
        painter.setPen(ring_pen)
        ring_radius = base_radius * 0.62
        painter.drawEllipse(QRectF(center_x - ring_radius, center_y - ring_radius, ring_radius * 2, ring_radius * 2))

        # Counter-rotating arcs.
        arcs = ((1.22, 0.9, 70), (1.38, -0.6, 50), (1.55, 0.35, 34))
        pen = QPen(QColor(color.red(), color.green(), color.blue(), 210))
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        for index, (scale, speed, span) in enumerate(arcs):
            radius = base_radius * scale
            start = math.degrees(self._phase * speed + index * 40)
            painter.drawArc(
                QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2),
                int(start * 16),
                int(span * 16),
            )

        # Reactive waveform when the assistant is listening or speaking.
        if self._state in {"listening", "speaking"}:
            bars = 36
            bar_width = width / (bars * 1.8)
            gap = bar_width * 0.8
            total = bars * (bar_width + gap)
            left = center_x - total / 2
            baseline = height * 0.86
            painter.setPen(Qt.NoPen)
            for index in range(bars):
                wave = math.sin(self._phase * 2.2 + index * 0.55)
                amplitude = (0.25 + self._level * 0.9) * (0.4 + 0.6 * abs(wave))
                bar_height = max(2.0, base_radius * 0.28 * amplitude)
                shade = QColor(color)
                shade.setAlpha(120 + int(80 * abs(wave)))
                painter.setBrush(shade)
                x = left + index * (bar_width + gap)
                painter.drawRoundedRect(
                    QRectF(x, baseline - bar_height, bar_width, bar_height), bar_width / 2, bar_width / 2
                )

        painter.end()