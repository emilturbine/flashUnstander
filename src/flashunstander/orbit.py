"""Inclined Kepler ellipses projected into the desktop widget."""
from dataclasses import dataclass
from functools import lru_cache
from math import cos, pi, sin, sqrt


@dataclass(frozen=True)
class Orbit:
    eccentricity: float
    cos_node: float
    sin_node: float
    cos_inclination: float
    sin_inclination: float

    def position(self, anomaly, axis):
        major = axis * (cos(anomaly) - self.eccentricity)
        minor = axis * sqrt(1 - self.eccentricity**2) * sin(anomaly)
        vertical = minor * self.cos_inclination
        x = major*self.cos_node - vertical*self.sin_node
        y = major*self.sin_node + vertical*self.cos_node
        return x, y, minor*self.sin_inclination

    def anomaly(self, mean):
        # Newton solve of E - e sin(E) = M. Eccentricities are below 0.12.
        angle = mean
        for _ in range(3):
            angle -= (angle - self.eccentricity*sin(angle) - mean) / (1 - self.eccentricity*cos(angle))
        return angle


@lru_cache(maxsize=64)
def orbit_for(index):
    node = -.34 + .10*sin(2.1*index)
    inclination = 1.05 + .12*cos(1.8*index)
    return Orbit(.055, cos(node), sin(node), cos(inclination), sin(inclination))


@dataclass(frozen=True)
class PlanetMaterial:
    density: float  # Approximate bulk density in g/cm³.
    radius_scale: float
    growth_exponent: float


PLANET_MATERIALS = (
    PlanetMaterial(4.8, 2 / 3, .55),  # Earth-like ocean and continents
    PlanetMaterial(5.5, .96 * (2 / 3), .64),   # Dense rocky desert
    PlanetMaterial(1.1, 1.07 * 1.25, .48),  # Gas giant
    PlanetMaterial(1.7, 1.03, .51),  # Ice giant
)


EXPANDED_RADIUS_SCALE = 1.32


def planet_radius(tokens, expansion, material):
    tokens = min(100_000, max(0, tokens))
    exponent = material.growth_exponent
    growth = ((1 + tokens/8000)**exponent - 1) / (13.5**exponent - 1)
    standby_radius = material.radius_scale * (9 + 4.5*growth)
    return standby_radius * (1 + expansion * (EXPANDED_RADIUS_SCALE - 1))


def planet_mass_ratio(radius, material):
    """Planet mass in stylized stellar units, from bulk density × volume."""
    return (material.density / 4.8) * (radius / 9)**3 / 80


def orbital_speed(axis, mass_ratio):
    """Mean angular speed from Kepler's third law, including planet mass."""
    return .31 * sqrt(1 + mass_ratio) * (70 / axis)**1.5


def project(x, y, z, camera=620.):
    scale = camera / (camera - z)
    return x*scale, y*scale, scale


@lru_cache(maxsize=64)
def guide_points(index):
    """Cache a unit ellipse; hover scales it before perspective projection."""
    orbit = orbit_for(index)
    return tuple(orbit.position(i*pi/36, 1.) for i in range(73))

# Close-up coordinates are measured in Earth radii; overview uses screen units.
AU_IN_EARTH_RADII = 23_455.
PHYSICAL_STAR_RADIUS = 109.
_PHYSICAL_RADII = (1., .53, 11.2, 3.9)
_PHYSICAL_AXES_AU = (.39, .72, 1.52, 5.20, 9.58, 19.2, 30.1)


def physical_planet_radius(index, tokens):
    material = PLANET_MATERIALS[index % len(PLANET_MATERIALS)]
    growth = planet_radius(tokens, 0, material) / planet_radius(0, 0, material)
    return _PHYSICAL_RADII[index % len(_PHYSICAL_RADII)] * growth


def physical_orbit_axis(index):
    if index < len(_PHYSICAL_AXES_AU):
        return _PHYSICAL_AXES_AU[index] * AU_IN_EARTH_RADII
    return _PHYSICAL_AXES_AU[-1] * (1 + .45*(index - len(_PHYSICAL_AXES_AU) + 1)) * AU_IN_EARTH_RADII
