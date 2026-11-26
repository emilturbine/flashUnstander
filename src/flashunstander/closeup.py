"""Fixed-axis perspective for the close-up view, in Earth radii."""
from math import hypot, log


def flight_progress(progress):
    """Cruise at a steady rate between short, smooth acceleration ramps."""
    progress = max(0., min(1., progress))
    ramp = .18
    if progress < ramp or progress > 1 - ramp:
        braking = progress > .5
        edge = (1 - progress if braking else progress) / ramp
        traveled = ramp * edge**3 * (1 - .5*edge) / (1 - ramp)
        return 1 - traveled if braking else traveled
    return (progress - ramp/2) / (1 - ramp)


class CloseupCamera:
    def __init__(self, aim, target_radius, screen_radius, progress, viewport_radius,
                 protected_position, protected_radius, initial_screen_radius=None):
        self.focal_pixels = 8 * screen_radius
        x, y, z = aim
        px, py, pz = protected_position
        fit_depth = (hypot(px - x, py - y) + protected_radius) * self.focal_pixels / viewport_radius
        start_radius = screen_radius / 9 if initial_screen_radius is None else initial_screen_radius
        zoom_ratio = max(1., screen_radius / start_radius)
        cruise_distance = 8 * target_radius * zoom_ratio**(1 - progress)
        distance = max(cruise_distance, pz - z + max(fit_depth, 2 * protected_radius))
        self.position = (x, y, z + distance)

    def project(self, position, radius):
        x, y, z = position
        cx, cy, cz = self.position
        depth = cz - z
        if depth <= radius * 1.01:
            return None
        scale = self.focal_pixels / depth
        distance = hypot(x, y, z)
        light = (-x/distance, -y/distance, -z/distance) if distance else (0., 0., 1.)
        return -log(depth), (x-cx)*scale, (y-cy)*scale, radius*scale, light
