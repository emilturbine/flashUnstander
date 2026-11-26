"""Regression checks for the orbit solver and directional sphere lighting."""
import math

import numpy as np
import pytest

from flashunstander.cosmic import RING_EXTENT, ring_for_conversation, sphere
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


def test_kepler_orbit_preserves_shape_when_its_axis_changes():
    orbit = orbit_for(0)
    for mean in (0., 1., math.pi, 2 * math.pi, 245.):
        angle = orbit.anomaly(mean)
        assert angle - orbit.eccentricity * math.sin(angle) == pytest.approx(mean)
        idle = np.array(orbit.position(angle, 61.))
        expanded = np.array(orbit.position(angle, 90.))
        assert np.linalg.norm(idle) > 50
        np.testing.assert_allclose(idle / 61., expanded / 90.)


def test_each_planet_material_can_render_a_fixed_ring():
    ids = [f"conversation-{i}" for i in range(32)]
    rings = [ring_for_conversation(identifier) for identifier in ids]
    assert None in rings
    ring = next(value for value in rings if value is not None)
    ring_for_conversation.cache_clear()
    assert rings == [ring_for_conversation(identifier) for identifier in ids]
    red, green, blue = ring[1]
    assert 166 <= red <= 221 and red >= green >= blue >= 89
    for kind in range(1, 5):
        image, extent = sphere(kind, 16, 1, (-1, 0, 0), 0, ring=ring)
        assert extent == pytest.approx(16 * RING_EXTENT)
        pixels = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.width(), 4)
        assert pixels[:, :image.width()//6, 3].max() > 0

def test_fixed_axis_closeup_uses_one_projection_for_the_whole_scene():
    from flashunstander.closeup import CloseupCamera

    subject = (7400., -2300., 4900.)
    camera = CloseupCamera(subject, 2., 58., 1., 220., subject, 3.66)
    depth, x, y, radius, _ = camera.project(subject, 2.)
    assert (x, y, radius) == pytest.approx((0., 0., 58.))

    # All celestial bodies share the exact same perspective and viewing axes.
    _, x, y, radius, _ = camera.project((7401., -2298., 4884.), 2.)
    assert (x, y, radius) == pytest.approx((14.5, 29., 29.))
    assert camera.project((7400., -2300., 4920.), 2.) is None

    next_subject = (-36000., 14000., 33000.)
    moving = CloseupCamera(subject, 2., 58., .65, 220., next_subject, 3.66)
    _, x, y, radius, _ = moving.project(next_subject, 3.66)
    assert math.hypot(x, y) + radius <= 220.001

def test_flight_accelerates_then_brakes_with_continuous_endpoints():
    from flashunstander.closeup import flight_progress

    samples = [flight_progress(i / 100) for i in range(101)]
    assert samples[0] == 0 and samples[-1] == 1
    assert samples == sorted(samples)
    assert samples[1] < samples[51] - samples[50]
    assert samples[-1] - samples[-2] < samples[51] - samples[50]
    assert flight_progress(.18) == pytest.approx(1 - flight_progress(.82))


def test_gpu_full_size_texture_gutters_wrap():
    from flashunstander.gpu_spheres import _surface_texture

    image = _surface_texture(1, 4)
    expected_width, expected_height = 2304, 1152
    gutter = expected_width // 32
    assert (image.width(), image.height()) == (expected_width + 2*gutter, expected_height)
    rgb = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine())
    color = rgb[:, :image.width()*3].reshape(image.height(), image.width(), 3)
    np.testing.assert_array_equal(color[:, :gutter], color[:, -2*gutter:-gutter])
    np.testing.assert_array_equal(color[:, -gutter:], color[:, gutter:2*gutter])


def test_earth_geography_and_weather_are_continuous_between_bake_strips():
    from flashunstander.earth_material import earth_tile

    color, weather = earth_tile(7, 96, 0, 96)
    top = earth_tile(7, 96, 0, 51)
    bottom = earth_tile(7, 96, 51, 96)
    np.testing.assert_array_equal(color, np.concatenate((top[0], bottom[0])))
    np.testing.assert_array_equal(weather, np.concatenate((top[1], bottom[1])))
    height, cloud, cirrus = weather.transpose(2, 0, 1)
    assert np.count_nonzero(height < 120) > height.size // 4
    assert np.count_nonzero(height > 132) > height.size // 5
    assert height[height > 132].max() > 158
    assert all(channel.max() - channel.min() > 90 for channel in (cloud, cirrus))
    assert not np.array_equal(cloud, cirrus)

def test_near_earth_map_adds_geography_and_cloud_detail_beyond_resampling():
    from flashunstander.earth_material import earth_tile, refine_earth_tile
    from flashunstander.gpu_spheres import _double_latitudes, _double_longitude

    color, weather = earth_tile(4, 96, 0, 96)
    broad_color = _double_latitudes(_double_longitude(color), 0, 192)
    broad_weather = _double_latitudes(_double_longitude(weather), 0, 192)
    refined_color, refined_weather = refine_earth_tile(
        4, 192, 0, broad_color.copy(), broad_weather / 255.,
    )
    assert np.count_nonzero(np.abs(refined_color - broad_color) > 2) > 100
    delta = np.abs(refined_weather - broad_weather)
    assert all(np.count_nonzero(delta[..., channel] > 2) > 100 for channel in (0, 1, 2))

def test_earth_weather_clock_stays_periodic_after_long_runs():
    from flashunstander.earth_material import earth_weather_phases

    rates = (.048, .074, .025)
    for elapsed in (0, 600, 3600, 24*3600, 7*24*3600):
        assert all(0 <= phase < math.tau for phase in earth_weather_phases(elapsed))
    for index, rate in enumerate(rates):
        turn = math.tau / rate
        before = earth_weather_phases(turn - .001)[index]
        after = earth_weather_phases(turn + .001)[index]
        assert (after - before) % math.tau == pytest.approx(2*.001*rate)

def test_storm_tracks_move_and_fade_independently():
    from flashunstander.earth_material import STORM_LIFECYCLES, earth_storm_motion, earth_storm_origin

    seed = 4
    offset = earth_storm_origin(seed) * .24
    for index, (rate, initial, _, _) in enumerate(STORM_LIFECYCLES):
        turn = (1 - initial - offset) / rate
        before = earth_storm_motion(turn - .001, seed)[index]
        after = earth_storm_motion(turn + .001, seed)[index]
        assert before[3] == after[3] == 0

        mid = turn + .42/rate
        mature = earth_storm_motion(mid, seed)[index]
        later = earth_storm_motion(mid + .13/rate, seed)[index]
        assert mature[3] > .99 and later[3] > .99
        assert mature[:2] != later[:2]
        assert later[2] > mature[2]
    assert len({round(state[3], 2) for state in earth_storm_motion(15., seed)}) > 1

def test_ring_profiles_vary_and_keep_the_stable_ring_assignment():
    from flashunstander.ring_material import ring_profile_for_conversation

    ids = [f"ring-owner-{i}" for i in range(80)]
    profiles = [ring_profile_for_conversation(identifier) for identifier in ids]
    assert [p is not None for p in profiles] == [
        ring_for_conversation(identifier) is not None for identifier in ids
    ]
    rings = [p for p in profiles if p]
    assert len({p.bands for p in rings}) >= 4
    assert {p.gaps for p in rings} == {1, 2, 3}
    assert max(p.outer - p.inner for p in rings) - min(p.outer - p.inner for p in rings) > .4
    assert all(1.1 < p.inner < p.outer < p.extent < 2.5 for p in rings)
    ring_profile_for_conversation.cache_clear()
    assert profiles == [ring_profile_for_conversation(identifier) for identifier in ids]
