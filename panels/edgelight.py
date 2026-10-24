"""Edge Light — Tahoe 26.2's ring light, kept for the machine.

The screen becomes a light: a soft glow around every edge of the
picture, the way a ring light would sit in front of the face during the
call.  The surface never takes the pointer or the keyboard, so the
windows underneath behave as if the light was not there.

The colour is warm at the cold end... the temperature is 0.0 warm and
1.0 cool, the intensity is the brightness of the glow, the width the
depth of the glow, and the radius the rounding of the ring."""

from __future__ import annotations

import time

from ..macui import state  # noqa: E402
from ..macui.panel import Panel  # noqa: E402

# the conference table: these names mean a call is going on
_CALL_APPS = ("zoom", "msedge-jitsi", "obs", "skype", "webex", "meet")


def conferencing():
    """Whether a call, a rec or the microphone means light would help."""
    if state.mic_active() or state.camera_active():
        return True
    apps = " ".join(
        f"{row.get('app_id','')} {row.get('title','')}"
        for row in state.toplevels()).lower()
    return any(name in apps for name in _CALL_APPS)


class EdgeLight(Panel):
    NAMESPACE = "mac-edgelight"

    def __init__(self, metrics):
        super().__init__(
            metrics,
            layer="top",
            anchors={"left": True, "right": True,
                     "top": True, "bottom": True},
            exclusive=0,
            keyboard=False,
        )
        # the surface covers the screen, the ring is drawn by the tick
        self.set_content_size(int(metrics.width or 1366),
                              int(metrics.height or 768))
        self._checked = None
        self._calling = False
        self.hide()

    # -- the knob ------------------------------------------------------------

    def _mode(self):
        return self.metrics.config.get("edge_light_mode", "off")

    def _wants(self):
        mode = self._mode()
        if mode == "auto" and self.metrics.config.get("edge_light_auto",
                                                      True):
            return self._conferencing()
        return mode == "on"

    def _conferencing(self):
        """The conference state, read at most once a second."""
        now = time.time()
        if self._checked is None or now - self._checked >= 1.0:
            self._checked = now
            self._calling = conferencing()
        return bool(self._calling)

    def refresh(self):
        if self._wants() != self.get_visible():
            if self._wants():
                self.show_all()
            else:
                self.hide()

    # -- painting ------------------------------------------------------------

    @staticmethod
    def _colour(temp):
        """White in the middle, warm and cool at the ends, in sRGB."""
        if temp <= 0.5:
            warm = (255, 199, 148)
            white = (255, 255, 255)
            factor = temp / 0.5
            return tuple(w + (wh - w) * factor for w, wh in zip(warm, white))
        white = (255, 255, 255)
        cool = (186, 218, 255)
        factor = (temp - 0.5) / 0.5
        return tuple(wh + (co - wh) * factor for wh, co in zip(white, cool))

    def paint(self, cr, width, height):
        if not self._wants():
            # does not happen while hidden, but paints nothing if forced
            return
        m = self.metrics
        cfg = self.metrics.config
        depth = max(12, int(cfg.get("edge_light_width", 64) * m.scale))
        intensity = max(0.0, min(1.0, float(cfg.get("edge_light_intensity",
                                                    0.8))))
        temp = max(0.0, min(1.0, float(cfg.get("edge_light_temp", 0.35))))
        radius = max(0.0, min(80.0, float(cfg.get("edge_light_radius",
                                                  22)))) * m.scale

        colour = self._colour(temp)
        layers = max(12, depth // 3)
        band = depth / layers

        # the glow is a stack of rounded rings: the edge of the screen is
        # the brightest band, and the layers fade like a light falloff
        cr.save()
        cr.set_antialias(2)  # best
        for i in range(layers):
            inset = i * band
            falloff = (1.0 - i / layers) ** 2.8
            # the first band glows, the rest fall like light does
            cr.new_sub_path()
            _ring(cr, inset, inset, width - inset * 2, height - inset * 2,
                  max(0.0, radius - inset))
            cr.set_source_rgba(colour[0], colour[1], colour[2],
                               min(0.9, intensity * falloff))
            cr.set_line_width(band * 1.02)
            cr.stroke()
        cr.restore()

    # -- input ---------------------------------------------------------------

    def input_rects(self):
        """The light is glass around the picture: the pointer goes through."""
        return []


def _ring(cr, x, y, w, h, radius):
    """A rounded rectangle path, four arced corners."""
    r = min(radius, w / 2, h / 2)
    if r <= 0:
        cr.rectangle(x, y, w, h)
        return
    cr.new_sub_path()
    cr.arc(x + r, y + r, r, 3.141592653589793, 1.5 * 3.141592653589793)
    cr.arc(x + w - r, y + r, r, 1.5 * 3.141592653589793, 2 * 3.141592653589793)
    cr.arc(x + w - r, y + h - r, r, 0, 0.5 * 3.141592653589793)
    cr.arc(x + r, y + h - r, r, 0.5 * 3.141592653589793, 3.141592653589793)
    cr.close_path()
