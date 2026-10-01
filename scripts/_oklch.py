"""OKLab <-> sRGB and WCAG contrast, with no third-party dependency.

The house UI derives every project accent from one hue at a fixed lightness and
chroma (D28). That only buys guaranteed contrast if something checks it, so the
same conversion the browser does is reproduced here and used by the audit.

Matrices: Bjoern Ottosson, "A perceptual color space for image processing" (2020).
Contrast: WCAG 2.x relative luminance on sRGB.
"""

from __future__ import annotations

import math

# The two stops every accent is generated at. Lightness is what makes the light
# stop legible on paper and the dark stop legible on ink; chroma is held constant
# so no project looks louder than another.
ACCENT_LIGHT = (0.48, 0.13)
ACCENT_DARK = (0.78, 0.13)
SOFT_LIGHT = (0.94, 0.045)
SOFT_DARK = (0.30, 0.055)


def oklch_to_hex(lightness: float, chroma: float, hue: float) -> str:
    """One OKLCH colour as a #rrggbb string, clipped to the sRGB gamut."""
    h = math.radians(hue)
    a, b = chroma * math.cos(h), chroma * math.sin(h)
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    bl = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
    return "#" + "".join(f"{_encode(c):02x}" for c in (r, g, bl))


def _encode(c: float) -> int:
    c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return max(0, min(255, round(c * 255)))


def _channel(c: int) -> float:
    x = c / 255
    return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two opaque sRGB colours, 1.0 to 21.0."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def accent_for(hue: int, theme: str) -> str:
    return oklch_to_hex(*(ACCENT_DARK if theme == "dark" else ACCENT_LIGHT), hue)


def accent_soft_for(hue: int, theme: str) -> str:
    return oklch_to_hex(*(SOFT_DARK if theme == "dark" else SOFT_LIGHT), hue)
