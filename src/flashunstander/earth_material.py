"""Procedural geography and weather maps for the GPU's terrestrial material."""
from functools import lru_cache
from math import cos, pi, sin, tau

import numpy as np

from .cosmic import _smooth


def earth_weather_phases(seconds):
    """Independent cyclic clocks for low clouds, cirrus and weather evolution."""
    return tuple((seconds * rate) % tau for rate in (.048, .074, .025))


@lru_cache(maxsize=64)
def earth_storm_origin(seed):
    # This is the same longitude offset used to bake the weather atlas.
    return float(np.random.default_rng(5953 + seed * 3191).uniform(-.5, .5))


# Turn rate, initial age, longitudinal travel and meridional drift.
STORM_LIFECYCLES = (
    (.0041, .23, .116, .044),
    (.0057, .49, .089, -.037),
    (.0033, .68, .137, .029),
)


def earth_storm_motion(seconds, seed):
    """Moving storm centers, rotation, and coverage for three local systems."""
    offset = earth_storm_origin(seed) * .24
    states = []
    for rate, initial, travel, bend in STORM_LIFECYCLES:
        age = (seconds * rate + initial + offset) % 1.
        growth = min(1., max(0., (age - .05) / .24))
        decay = min(1., max(0., (.94 - age) / .30))
        strength = growth*growth*(3 - 2*growth) * decay*decay*(3 - 2*decay)
        longitude = travel * (age - .5) + .013*sin(tau*age)
        latitude = bend * sin(pi*age) + .012*sin(tau*age)
        states.append((longitude, latitude, tau*1.35*age, strength))
    return tuple(states)


def _mix(a, b, weight):
    a, b = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    return a + (b - a) * weight[..., None]


def _noise(u, v, cells, rng):
    """Sample periodic weather and terrain in float32, including interpolation."""
    grid = rng.random((cells + 1, cells*2), dtype=np.float32)
    x = (u % 1) * (cells*2)
    y = np.clip(v, 0, .99999) * cells
    fx, ix = np.modf(x)
    fy, iy = np.modf(y)
    ix, iy = ix.astype(np.int32) % (cells*2), iy.astype(np.int32)
    jx = (ix + 1) % (cells*2)
    fx, fy = _smooth(fx), _smooth(fy)
    a = grid[iy, ix]
    b = grid[iy+1, ix]
    top = a + (grid[iy, jx] - a) * fx
    bottom = b + (grid[iy+1, jx] - b) * fx
    return top + (bottom - top) * fy


def earth_tile(seed, height, start, stop):
    width = height * 2
    u = (np.arange(width, dtype=np.float32)[None, :] + .5) / width
    v = (np.arange(start, stop, dtype=np.float32)[:, None] + .5) / height
    # Reinitialize for every strip so noise and climate fields match across rows.
    rng = np.random.default_rng(5953 + seed * 3191)
    rotation = rng.uniform(-.5, .5)
    lat = (v - .5) * 2
    polar = abs(lat)
    broad = _noise(u, v, 5, rng) - .5
    hills = _noise(u, v, 24, rng) - .5
    texture = _noise(u, v, 87, rng) - .5
    warped_u = u + .065 * broad
    warped_v = v + .035 * _noise(u, v, 9, rng) - .0175

    continental = np.zeros_like(broad)
    for lon, center_v, span, length, heading in (
        (.12, .35, .165, .18, .43), (.20, .62, .105, .23, -.48),
        (.47, .37, .19, .145, .28), (.50, .55, .10, .20, -.31),
        (.78, .65, .12, .11, .16), (.92, .33, .09, .13, -.48),
        (.69, .51, .043, .067, .39),
    ):
        dx = (warped_u - lon - rotation + .5) % 1 - .5
        dy = warped_v - center_v - rng.uniform(-.045, .045)
        x = dx*cos(heading) - dy*sin(heading)
        y = dx*sin(heading) + dy*cos(heading)
        lobe = np.exp(-((x/span)**2 + (y/length)**2))
        continental = np.maximum(continental, lobe)

    # Curved island chains are broken into separate landforms by the smaller
    # coastal scales below rather than drawn as a uniform strip.
    for lon, center_v, slope in ((.63, .68, -.52), (.83, .38, .61), (.30, .43, -.34)):
        dx = (warped_u - lon - rotation + .5) % 1 - .5
        dy = warped_v - center_v - slope*dx - .17*dx*dx
        arc = .56*np.exp(-((dx/.089)**2 + (dy/.013)**2))
        arc *= .87 + .36*_noise(u, v, 47, rng)
        continental = np.maximum(continental, arc)

    coast_grain = _noise(u + .019*hills, v + .013*broad, 132, rng) - .5
    fine_coast = _noise(u + .007*texture, v - .004*hills, 283, rng) - .5
    shelf_height = continental + .24*broad + .17*hills + .11*texture
    coastline = 1 - _smooth((abs(shelf_height - .57) - .018)*10)
    channels = 1 - abs(2*_noise(u + .055*broad, v + .015*hills, 62, rng) - 1)
    fjords = _smooth((polar - .44)*3) * coastline * _smooth((channels - .73)*3.3)
    shelf_height += coastline * (.065*coast_grain + .031*fine_coast - .033*fjords)
    land = _smooth((shelf_height - .57)*98)
    shelf = _smooth((shelf_height - .405)*7.4) * (1 - land)
    current = _noise(u + .075*broad, v + .08*np.sin(2*pi*u), 17, rng)
    water = _mix((11, 30, 65), (17, 50, 85), _smooth(current))
    ocean = _mix(water, (32, 117, 126), shelf)
    ocean *= (1 + .13*broad + .075*texture + .034*coast_grain)[..., None]

    distance = np.clip((shelf_height - .58)*2.8, 0, 1)
    mountain_noise = _noise(u + .06*broad, v, 14, rng)
    range_height = _smooth((mountain_noise - .42)*2.6) * distance
    ridge_noise = _noise(u + .03*broad, v + .025*hills, 49, rng)
    ridge = 1 - abs(2*ridge_noise - 1)
    cut = 1 - abs(2*_noise(u + .011*hills, v + .019*texture, 113, rng) - 1)
    rugged = .62*ridge*ridge + .26*channels + .12*fine_coast
    erosion = _smooth((cut - .53)*2.2) * (.5 + .5*channels)
    mountain = _smooth((range_height * (.52 + rugged) - .20) * 3.9)
    relief = _smooth(.16*distance + .68*mountain + .13*hills + .10*rugged
                     - .18*erosion*mountain)
    relief *= _smooth(distance*5.2)
    desert_belt = np.exp(-((polar - .38 - .13*broad) / .18)**2)
    aridity = _smooth(.86*desert_belt + .65*broad - .34*mountain)
    green = _mix((48, 89, 62), (106, 139, 77), _smooth(.5 + hills))
    ground = _mix(green, (181, 151, 105), aridity)
    rock = _mix((113, 104, 91), (171, 157, 140), _smooth(rugged))
    ground = _mix(ground, rock, mountain)
    ground *= (1 - .16*erosion*mountain + .11*coast_grain + .058*fine_coast)[..., None]
    snow = _smooth((polar + .33*mountain + .12*broad - .81)*8)
    ground = _mix(ground, (225, 230, 229), snow)
    shore = land * (1 - _smooth((shelf_height - .58)*40))
    ground = _mix(ground, (205, 181, 132), .46*shore)
    ice = _smooth((polar + .09*broad - .89)*12)
    albedo = _mix(_mix(ocean, ground, land), (206, 222, 230), ice)
    albedo *= (1 + .055*texture)[..., None]

    # Advect turbulent bands along latitude instead of scattering round blobs.
    phase = 2*pi*(u + rotation)
    wave = .035*np.sin(3*phase + 5*v) + .021*np.sin(5*phase - 4*v)
    flow_y = v + wave + .029*broad
    front = _noise(.5*u + .031*np.sin(4*pi*u), 2*flow_y - .5, 18, rng)
    front_wrapped = _noise(u + .035*np.sin(phase + 7*v), flow_y, 21, rng)
    belt = _noise(u, v + .048*np.sin(2*phase), 5, rng)
    fiber = _noise(u + .052*broad, v + 2.3*wave, 89, rng)
    temperate = np.exp(-((polar - .53 + 1.7*wave) / .19)**2)
    tropical = np.exp(-((lat + 2*wave) / .13)**2)
    # The elongated fronts repeat around the equator with a seamless blend.
    elongation = np.sin(pi*u)**2
    front = front_wrapped + (front - front_wrapped) * (.54*elongation)
    cover = .49*front + .32*belt + .15*fiber + .17*temperate + .10*tropical
    cloud = _smooth((cover - .55)*5.2) * (.72 + .28*fiber)

    # Frontal cyclones have curved broken arms and a quieter core.
    storm = np.zeros_like(cloud)
    for lon, latitude, direction in ((.13, .66, 1), (.48, .30, -1), (.80, .72, 1)):
        du = ((u - lon - rotation + .5) % 1 - .5) / .091
        dv = (v - latitude - rng.uniform(-.026, .026)) / .116
        radius = np.hypot(du, dv)
        heading = np.arctan2(dv, du)
        arms = .5 + .5*np.cos(2*heading + direction*(7.2*radius + 2.1*np.log(radius+.09))
                              + 1.1*(fiber - .5))
        eye = _smooth((radius - .10)*9)
        outer = 1 - _smooth((radius - .34)*1.5)
        broken = _smooth((belt + .27*fiber - .27)*3)
        storm = np.maximum(storm, _smooth((arms - .38)*1.86) * eye * outer * broken)
    cloud = np.maximum(cloud, .91*storm)
    # Erode the boundary at two scales and let small tendrils trail along the
    # same wind field, while leaving the dense cores and clear skies intact.
    cloud_fine = _noise(u + .032*broad, v + 2.75*wave + .007*fiber, 173, rng)
    cloud_fray = _noise(u + .019*hills, v + 3.1*wave + .004*cloud_fine, 299, rng)
    cloud_edge = 4*cloud*(1 - cloud)
    cloud = np.clip(cloud + cloud_edge*(.35*(cloud_fine - .5) + .16*(cloud_fray - .5)), 0, 1)
    cirrus = _noise(u + .11*np.sin(phase + 6*v), v + 1.46*wave, 35, rng)
    filament = .53*cirrus + .18*fiber + .17*cloud_fine + .07*cloud_fray + .13*temperate
    cirrus = _smooth((filament - .555)*5.1)

    # Red encodes height relative to sea level (.5), so the same texture can
    # drive shore masks and directional relief without a third GPU image.
    sea = .14 + .32*shelf
    height_map = sea + (.53 + .43*relief - sea)*land
    height_map += (.53 - height_map)*ice
    weather = np.stack((height_map, cloud, cirrus), axis=-1)
    return np.clip(albedo, 0, 255).astype(np.uint8), (weather*255).astype(np.uint8)

def refine_earth_tile(seed, height, start, albedo, weather):
    """Add native-resolution shore, relief and cloud detail over broad fields."""
    width = height * 2
    rows = albedo.shape[0]
    u = (np.arange(width, dtype=np.float32)[None, :] + .5) / width
    v = (np.arange(start, start + rows, dtype=np.float32)[:, None] + .5) / height

    rng = np.random.default_rng(1249 + seed * 671)
    elevation = weather[..., 0]
    cloud = weather[..., 1]
    cirrus = weather[..., 2]
    coast = 1 - _smooth((abs(elevation - .5) - .022)*15)
    land = _smooth((elevation - .52)*8)
    ridge = _noise(u + .009*np.sin(8*pi*v), v + .006*np.sin(10*pi*u), 191, rng) - .5
    granules = _noise(u + .002*ridge, v + .002*ridge, 347, rng) - .5
    mineral = .68*ridge + .32*granules
    elevation += .027*mineral*coast + .058*mineral*land
    albedo *= (1 + (.092*land + .12*coast)*mineral)[..., None]

    wind = .039*np.sin(6*pi*u + 4*v) + .012*np.sin(14*pi*u - 2*v)
    tendril = _noise(u, v + wind, 161, rng) - .5
    fray = _noise(u + .004*tendril, v + 1.45*wind, 307, rng) - .5
    edges = 4*cloud*(1 - cloud)
    cloud += edges*(.22*tendril + .13*fray)
    cirrus += 4*cirrus*(1 - cirrus)*(.18*tendril + .087*fray)
    return (np.clip(albedo, 0, 255).astype(np.uint8),
            np.clip(weather*255, 0, 255).astype(np.uint8))
