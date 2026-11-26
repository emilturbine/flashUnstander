"""Orthographic ray/sphere shading for the small translucent desktop widget.

Coordinates are in planet radii, with +Y down the screen and +Z toward the
observer. Only the static surface maps and view-space geometry are cached.
"""
from functools import lru_cache
from math import ceil, cos, pi, sin
from random import Random

import numpy as np
from PySide6.QtGui import QImage


def _smooth(x):
    t = np.clip(x, 0, 1)
    return t * t * (3 - 2 * t)


def _noise(u, v, cells, rng):
    """Bilinear value noise on a lattice that wraps at the date line."""
    grid = rng.random((cells + 1, cells * 2), dtype=np.float32)
    x, y = (u % 1) * grid.shape[1], np.clip(v, 0, .99999) * cells
    ix, iy = x.astype(np.int32), y.astype(np.int32)
    jx = (ix + 1) % grid.shape[1]
    fx, fy = _smooth(x - ix), _smooth(y - iy)
    top = grid[iy, ix] * (1 - fx) + grid[iy, jx] * fx
    bottom = grid[iy + 1, ix] * (1 - fx) + grid[iy + 1, jx] * fx
    return top + (bottom - top) * fy


def _mix(a, b, t):
    a, b = np.asarray(a), np.asarray(b)
    return a + (b - a) * t[..., None]


@lru_cache(maxsize=32)
def _albedo(kind, seed):
    return _generate_albedo(kind, seed, 192)


def _generate_albedo(kind, seed, height, *, gpu_texture=False, rows=None):
    width = 2 * height
    start, stop = (0, height) if rows is None else rows
    y, x = np.indices((stop - start, width), dtype=np.float32)
    y += start
    u, v = (x + (.5 if gpu_texture else 0)) / width, (y + .5) / height
    rng = np.random.default_rng(1871 + kind + 7919*seed)
    warp = _noise(u, v, 5, rng) - .5
    u = u + .055 * warp
    broad = _noise(u, v, 4, rng)
    terrain = (.48 * broad + .27 * _noise(u, v, 10, rng)
               + .16 * _noise(u, v, 23, rng) + .09 * _noise(u, v, 54, rng))
    fine = _noise(u, v, 75, rng)
    if kind == 0:
        # Bright granular cells, dark intergranular lanes and a few active regions.
        cells = _smooth((.64 * fine + .36 * _noise(u, v, 131, rng) - .12) / .7)
        spots = _smooth((.33 - terrain) * 13)
        base = _mix((251, 134, 43), (255, 234, 159),
                    np.clip(.56 * cells + .42 * terrain + .17 * broad, 0, 1))
        base *= (1 - .27 * spots[..., None])
    elif kind == 1:
        ocean = _mix((22, 58, 99), (63, 152, 168), _smooth((terrain - .23) * 3.6))
        land = _mix((85, 121, 98), (194, 170, 113), _smooth((terrain - .49) * 4))
        base = _mix(ocean, land, _smooth((terrain - .48) * 64))
        clouds = _noise(u + .14 * warp, v + .035 * np.sin(u * 4*pi), 18, rng)
        base = _mix(base, (220, 233, 233), .80 * _smooth((clouds - .53) * 3.5))
        base = _mix(base, (212, 231, 237), _smooth((abs(v - .5) - .39 + .05 * warp) * 18))
    elif kind == 3:
        bands = (.48 + .32 * np.sin(v*89 + 3*warp)
                 + .16 * np.sin(v*151 + 6*terrain))
        base = _mix((143, 100, 77), (246, 223, 172), bands)
        base *= (.88 + .21 * fine[..., None])
    else:
        colors = ((119, 65, 48), (231, 167, 123)) if kind == 2 else ((49, 91, 147), (146, 211, 224))
        base = _mix(*colors, _smooth((terrain - .25) * 2.3))
        base *= (.92 + .16 * fine[..., None])
    if kind:
        # Vary pigment balance independently from the terrain seed.
        pigment = rng.uniform(.76, 1.24, 3)
        base = np.clip(base * pigment, 0, 255)
    if gpu_texture:
        grain = .64 * _noise(u, v, 151, rng) + .36 * _noise(u, v, 257, rng)
        strength = .11 if kind in (1, 3) else .15
        base = np.clip(base * (1 + (grain - .5)*strength)[..., None], 0, 255)
    return base.astype(np.float32)


_RING_NORMAL = (-.26, -.91, .322)
RING_EXTENT = 1.83


@lru_cache(maxsize=32)
def _geometry(size, kind, ringed):
    extent = RING_EXTENT if ringed else 1.
    axis = ((np.arange(size, dtype=np.float32) + .5) / size * 2 - 1) * extent
    x, y = np.meshgrid(axis, axis)
    radial = np.hypot(x, y)
    z = np.sqrt(np.maximum(0, 1 - radial**2))
    coverage = np.clip((1 - radial) * size / (2*extent) + .5, 0, 1)
    tilt = (.13, -.21, .31, -.28, .20)[kind]
    local_x = x * cos(tilt) + y * sin(tilt)
    local_y = y * cos(tilt) - x * sin(tilt)
    # The gas giant's spin axis is perpendicular to its ring plane.
    axial_tip = -.328 if kind == 3 else .12
    local_y, local_z = (local_y*cos(axial_tip) + z*sin(axial_tip),
                        z*cos(axial_tip) - local_y*sin(axial_tip))
    u = (np.arctan2(local_x, local_z) / (2*pi) + .5).astype(np.float32)
    v = np.arcsin(np.clip(local_y, -1, 1)) / pi + .5
    height = 192
    row = np.clip(v * height - .5, 0, height-1)
    iy = row.astype(np.int32)
    return x, y, z, coverage, u, iy, np.minimum(iy+1, height-1), (row-iy).astype(np.float32)[..., None]


def _rings(rgb, alpha, x, y, z, light, size, opacity, color):
    nx, ny, nz = _RING_NORMAL
    ring_z = -(nx*x + ny*y) / nz
    distance = np.sqrt(x*x + y*y + ring_z*ring_z)
    edge = size / (2 * RING_EXTENT)
    density = (.69 + .10*np.cos(71*distance) + .07*np.sin(129*distance))
    density *= 1 - .90 * np.exp(-((distance - 1.54) / .025)**2)
    density *= opacity * _smooth((distance - 1.20)*edge) * _smooth((1.80 - distance)*edge)
    # A ray from the ring toward the star intersects the planet in its shadow.
    along = -(x*light[0] + y*light[1] + ring_z*light[2])
    shadow = (along > 0) * _smooth((1 - distance**2 + along**2)*10)
    # Intersect a ray from the visible globe with the ring plane for its shadow.
    slope = nx*light[0] + ny*light[1] + nz*light[2]
    if abs(slope) > .006:
        travel = -(nx*x + ny*y + nz*z) / slope
        crossing = np.sqrt((x+travel*light[0])**2 + (y+travel*light[1])**2
                           + (z+travel*light[2])**2)
        in_band = _smooth((crossing-1.2)*12) * _smooth((1.8-crossing)*12)
        rgb = rgb * (1 - .38*opacity*in_band*(travel > 0))[..., None]
    ring_light = (.54 + .40*abs(nx*light[0] + ny*light[1] + nz*light[2])) * (1 - .72*shadow)
    ring_rgb = np.array(color, dtype=np.float32) * ring_light[..., None]
    visible = density * np.where(ring_z > z, 1, 1-alpha)
    # Work premultiplied here so the ring's fractional opacity survives at the limb.
    underlying = alpha * (1 - density * (ring_z > z))
    out_alpha = underlying + visible
    combined = (rgb * underlying[..., None] + ring_rgb * visible[..., None])
    return combined / np.maximum(out_alpha[..., None], .0001), out_alpha


@lru_cache(maxsize=128)
def ring_for_conversation(conversation_id):
    if conversation_id is None:
        return None
    rng = Random(conversation_id)
    if rng.random() >= .30:
        return None
    warm = rng.random()
    pale = (221, 220, 214)
    brown = (166, 126, 89)
    color = tuple(round(a + (b-a)*warm) for a, b in zip(pale, brown))
    return 1., color


def sphere(kind, radius, pixel_ratio, light, spin, seed=0, *, brightness=1., shadow_light=.36, ring=None):
    """Render a rotating textured sphere, including analytic limb coverage."""
    ringed = ring is not None and ring[0] > 0 and kind != 0
    extent = RING_EXTENT if ringed else 1.
    # Bucket resolutions to reuse geometry throughout the expansion animation.
    size = min(320, max(32, 16 * ceil(2 * radius * extent * pixel_ratio * 1.4 / 16)))
    x, y, z, alpha, u, iy, jy, fy = _geometry(size, kind, ringed)
    texture = _albedo(kind, seed)
    column = ((u - spin / (2*pi)) % 1) * texture.shape[1]
    ix = column.astype(np.int32) % texture.shape[1]
    jx = (ix + 1) % texture.shape[1]
    fx = (column - np.floor(column))[..., None]
    left = texture[iy, ix] * (1-fy) + texture[jy, ix] * fy
    right = texture[iy, jx] * (1-fy) + texture[jy, jx] * fy
    rgb = left + (right - left)*fx
    if kind == 0:
        rgb *= (.745 + .28*z**.57)[..., None]
    else:
        lx, ly, lz = light
        incidence = x*lx + y*ly + z*lz
        # Keep the terminator narrow, with a resolution-aware transition at its edge.
        feather = max(.015, 1.5 * extent / size)
        terminator = _smooth((incidence + feather) / (2 * feather))
        diffuse = .14 * terminator + .86 * np.maximum(incidence, 0)**.72
        rgb *= (shadow_light + (1.055 - shadow_light)*diffuse)[..., None]
        rim = (1-z)**2.5 * (.12 + .88*_smooth((incidence+.30)*2))
        tint = (64, 137, 203) if kind in (1, 4) else (151, 93, 50)
        rgb += rim[..., None] * np.asarray(tint, dtype=np.float32)
        if ringed:
            rgb, alpha = _rings(rgb, alpha, x, y, z, light, size, *ring)
    pixels = np.empty((size, size, 4), dtype=np.uint8)
    pixels[..., :3] = np.clip(rgb * brightness, 0, 255)
    pixels[..., 3] = alpha * 255
    image = QImage(pixels.data, size, size, pixels.strides[0], QImage.Format.Format_RGBA8888)
    return image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied), radius * extent
