"""Works out @ew_accent_pair: a second colour that stands out next to the accent.

The pair is a neighbouring hue at a clearly different lightness, measured in
OKLab, where equal steps look equal whatever the hue. It goes lighter on dark
cards and darker on light ones, so it also stands out from the bar's trough,
unless there is no room that way (banana on dark, say): then it goes the other.
https://bottosson.github.io/posts/oklab/ has the conversions.
"""

import math

RGB = tuple[float, float, float]  # sRGB, 0..1

HUE_SHIFT = math.radians(35)
LIGHTNESS_GAP = 0.27
MIN_LIGHTNESS_GAP = 0.2
# The lightness the pair keeps within, on (light, dark) cards: never close to
# the trough, nor so light or dark that its hue is lost.
LIGHTNESS_RANGE = ((0.35, 0.80), (0.50, 0.92))
GAMUT_STEP = 0.95  # chroma is cut by this until the colour fits in sRGB


def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gamma(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def to_oklab(rgb: RGB) -> tuple[float, float, float]:
    r, g, b = map(_linear, rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)  # noqa: E741
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def from_oklab(lightness: float, a: float, b: float) -> RGB:
    """The colour in sRGB, possibly outside 0..1."""
    l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3  # noqa: E741
    m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        _gamma(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
        _gamma(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
        _gamma(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s),
    )


def accent_pair(accent: RGB, dark: bool) -> RGB:
    lightness, a, b = to_oklab(accent)
    low, high = LIGHTNESS_RANGE[dark]
    step = LIGHTNESS_GAP if dark else -LIGHTNESS_GAP
    target = min(max(lightness + step, low), high)
    if abs(target - lightness) < MIN_LIGHTNESS_GAP:
        target = min(max(lightness - step, low), high)

    chroma, hue = math.hypot(a, b), math.atan2(b, a) + HUE_SHIFT
    while True:
        rgb = from_oklab(target, chroma * math.cos(hue), chroma * math.sin(hue))
        if all(-1e-4 <= c <= 1 + 1e-4 for c in rgb) or chroma < 1e-3:
            return (min(max(rgb[0], 0), 1), min(max(rgb[1], 0), 1), min(max(rgb[2], 0), 1))
        chroma *= GAMUT_STEP
