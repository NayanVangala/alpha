"""Draws Alpha's logo: a lowercase alpha with a dithered aura rippling off it.

The letter is a round bowl with an upright stem and a small tail (no crossing
loop, so it can't be read as an infinity sign). The aura uses the same
three-tone 8x8 Bayer dither as the dashboard's head (clear, pale blue,
ultramarine), and follows the letter's outline in rings, like brainwaves
coming off the alpha. Writes:
  src/frontend/public/alpha-logo.svg  the full logo, for big placements
  src/frontend/public/alpha-mark.svg  just the letter, for the favicon and small sizes

Run: uv run python -m scripts.make_logo
"""

from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "src" / "frontend" / "public"
BLUE, PALE = "#0004F6", "#CDCCFF"
SIZE, CELL = 120, 2  # viewBox units; one dither cell
STROKE = 9
BAYER = np.array([0, 48, 12, 60, 3, 51, 15, 63, 32, 16, 44, 28, 35, 19, 47, 31, 8, 56, 4, 52, 11, 59, 7, 55,
                  40, 24, 36, 20, 43, 27, 39, 23, 2, 50, 14, 62, 1, 49, 13, 61, 34, 18, 46, 30, 33, 17, 45, 29,
                  10, 58, 6, 54, 9, 57, 5, 53, 42, 26, 38, 22, 41, 25, 37, 21]).reshape(8, 8) / 64

CX, CY, R = 55, 59, 19  # the bowl, centred so the whole letter sits in the middle of the box
STEM = ((81, 37), (76, 39), (74, 43), (74, 49)), ((74, 49), (74, 60), (74, 64), (74, 71)), \
       ((74, 71), (74, 77), (78, 81), (84, 81))  # hook at the top, stem tangent to the bowl, tail at the foot


def bezier(p0, p1, p2, p3, n=40):
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 3 * np.array(p0) + 3 * (1 - t) ** 2 * t * np.array(p1) + 3 * (1 - t) * t**2 * np.array(p2) \
        + t**3 * np.array(p3)


def outline():
    """Points along the letter's centreline, for measuring the aura's distance."""
    a = np.linspace(0, 2 * np.pi, 160)
    return np.vstack([np.stack([CX + R * np.cos(a), CY + R * np.sin(a)], axis=1), *(bezier(*s) for s in STEM)])


def letter(width):
    (x, y) = STEM[0][0]
    d = f"M{x} {y}" + "".join(f"C{a[0]} {a[1]} {b[0]} {b[1]} {c[0]} {c[1]}" for _, a, b, c in STEM)
    return (f'<g fill="none" stroke="{BLUE}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">'
            f'<circle cx="{CX}" cy="{CY}" r="{R}"/><path d="{d}"/></g>')


def aura_cells():
    """Two lists of cell origins (pale, blue): distance from the letter, fading out in rings, then dithered."""
    grid = np.arange(0, SIZE, CELL) + CELL / 2
    gx, gy = np.meshgrid(grid, grid)
    centres = np.stack([gx.ravel(), gy.ravel()], axis=1)
    d = np.min(np.linalg.norm(centres[:, None, :] - outline()[None, :, :], axis=2), axis=1)
    gap = STROKE / 2 + 3  # clear ring so the letter stays crisp
    r = np.clip(d - gap, 0, None)
    rings = 0.1 + 0.9 * (0.5 + 0.5 * np.cos(2 * np.pi * r / 12))  # a ring every 12 units
    fade = np.clip((58 - np.linalg.norm(centres - SIZE / 2, axis=1)) / 12, 0, 1)  # round, soft outer edge
    level = np.where(d < gap, 0, 2.2 * np.exp(-r / 16) * rings * fade)  # 0..2: clear, pale, blue
    ix, iy = (centres[:, 0] // CELL).astype(int), (centres[:, 1] // CELL).astype(int)
    threshold = BAYER[iy % 8, ix % 8]
    blue = level > 1 + threshold
    pale = ~blue & (level > threshold)
    origin = centres - CELL / 2
    return origin[pale], origin[blue]


def squares(origins):
    return "".join(f"M{x:g} {y:g}h{CELL}v{CELL}h-{CELL}z" for x, y in origins)


def main():
    pale, blue = aura_cells()
    (OUT / "alpha-logo.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" shape-rendering="crispEdges">'
        f'<title>Alpha</title><path fill="{PALE}" d="{squares(pale)}"/><path fill="{BLUE}" d="{squares(blue)}"/>'
        f'<g shape-rendering="geometricPrecision">{letter(STROKE)}</g></svg>\n')
    # the letter alone, cropped tight and heavier so it reads at 16 px
    (OUT / "alpha-mark.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="29 32 62 56"><title>Alpha</title>{letter(11)}</svg>\n')
    print(f"aura cells: {len(pale)} pale, {len(blue)} blue -> {OUT / 'alpha-logo.svg'}")


if __name__ == "__main__":
    main()
