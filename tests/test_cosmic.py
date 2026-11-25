"""Regression checks for the orbit solver and directional sphere lighting."""
import math

import numpy as np
import pytest

from flashunstander.cosmic import RING_EXTENT, ring_state, sphere
from flashunstander.orbit import orbit_for


def test_planet_rotates_inside_a_silhouette_lit_by_the_star():
    def render(light, spin):
        image, _ = sphere(1, 32, 1, light, spin)
        return np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.width(), 4).copy()

    left = render((-1, 0, 0), 0)
    right = render((1, 0, 0), 0)
    turned = render((-1, 0, 0), .6)
    image_y = left.shape[0] // 2
    x_left, x_right = left.shape[1] // 6, left.shape[1] * 5 // 6
    assert left[image_y, x_left, :3].mean() > 2 * right[image_y, x_left, :3].mean()
    assert right[image_y, x_right, :3].mean() > 2 * left[image_y, x_right, :3].mean()
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


def test_each_planet_material_can_render_a_timed_ring():
    for kind in range(1, 5):
        states = [ring_state(kind, second / 2) for second in range(192)]
        assert any(opacity == 0 for opacity, _ in states)
        assert any(0 < opacity < 1 for opacity, _ in states)
        ring = next(state for state in states if state[0] == 1)
        red, green, blue = ring[1]
        assert 166 <= red <= 221 and red >= green >= blue >= 89
        image, extent = sphere(kind, 16, 1, (-1, 0, 0), 0, ring=ring)
        assert extent == pytest.approx(16 * RING_EXTENT)
        pixels = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.width(), 4)
        assert pixels[:, :image.width()//6, 3].max() > 0
