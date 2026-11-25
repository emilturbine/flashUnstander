"""Regression checks for the orbit solver and directional sphere lighting."""
import math

import numpy as np
import pytest

from flashunstander.cosmic import sphere
from flashunstander.orbit import orbit_for


def test_planet_rotates_inside_a_silhouette_lit_by_the_star():
    def render(light, spin):
        image, _ = sphere(1, 32, 1, light, spin)
        return np.frombuffer(image.constBits(), np.uint8).reshape(64, 64, 4).copy()

    left = render((-1, 0, 0), 0)
    right = render((1, 0, 0), 0)
    turned = render((-1, 0, 0), .6)
    assert left[30, 10, :3].mean() > 2 * right[30, 10, :3].mean()
    assert right[30, 52, :3].mean() > 2 * left[30, 52, :3].mean()
    np.testing.assert_array_equal(left[..., 3], turned[..., 3])
    assert np.abs(left.astype(float) - turned).mean() > 1


def test_kepler_motion_is_continuous_through_hover():
    orbit = orbit_for(0)
    for mean in (0., 1., math.pi, 2 * math.pi, 245.):
        angle = orbit.anomaly(mean)
        assert angle - orbit.eccentricity * math.sin(angle) == pytest.approx(mean)
        idle = np.array(orbit.position(angle, 0.))
        expanded = np.array(orbit.position(angle, 1.))
        assert np.linalg.norm(idle) > 50
        np.testing.assert_allclose(idle / orbit.axis(0), expanded / orbit.axis(1))
