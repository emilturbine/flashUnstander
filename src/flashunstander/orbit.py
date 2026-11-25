"""Inclined Kepler ellipses projected into the desktop widget."""
from dataclasses import dataclass
from functools import lru_cache
from math import cos, pi, sin, sqrt


@dataclass(frozen=True)
class Orbit:
    lane: float
    eccentricity: float
    cos_node: float
    sin_node: float
    cos_inclination: float
    sin_inclination: float
    mean_motion: float

    def axis(self, expansion):
        return 61 + 24*self.lane + (1 + 22*self.lane)*expansion

    def position(self, anomaly, expansion, axis=None):
        axis = self.axis(expansion) if axis is None else axis
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
    # A low-discrepancy sequence gives new sessions stable, distinct lanes.
    lane = (.25 + index * .61803398875) % 1
    node = -.34 + .10*sin(2.1*index)
    inclination = 1.05 + .12*cos(1.8*index)
    motion = .31 * (62 / (62 + 46*lane))**1.5
    return Orbit(lane, .055, cos(node), sin(node),
                 cos(inclination), sin(inclination), motion)


@dataclass(frozen=True)
class PlanetMaterial:
    density: float  # Approximate bulk density in g/cm³.
    radius_scale: float
    growth_exponent: float


PLANET_MATERIALS = (
    PlanetMaterial(4.8, 2 / 3, .55),  # Earth-like ocean and continents
    PlanetMaterial(5.5, .96 * (2 / 3), .64),   # Dense rocky desert
    PlanetMaterial(1.1, 1.07 * 1.25, .48),  # Ringed gas giant
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


def project(x, y, z):
    scale = 620 / (620 - z)
    return x*scale, y*scale, scale


@lru_cache(maxsize=64)
def guide_points(index):
    """Cache a unit ellipse; hover scales it before perspective projection."""
    orbit = orbit_for(index)
    axis = orbit.axis(0)
    return [tuple(value / axis for value in orbit.position(i*pi/36, 0))
            for i in range(73)]
