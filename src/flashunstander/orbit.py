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

    def position(self, anomaly, expansion):
        axis = self.axis(expansion)
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
    return Orbit(lane, .052 + .055*lane, cos(node), sin(node),
                 cos(inclination), sin(inclination), motion)


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
