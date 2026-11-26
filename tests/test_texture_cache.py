from PySide6.QtGui import QColor, QImage

from flashunstander import gpu_spheres
from flashunstander.texture_cache import DetailTextureCache


def test_saved_detail_pair_is_reused_after_restart_and_deleted_with_planet(tmp_path, monkeypatch):
    height = gpu_spheres.DETAIL_TEXTURE_HEIGHT
    width = height * 2 + (height * 2 // 32) * 2
    terrain = QImage(width, height, QImage.Format.Format_RGB888)
    terrain.fill(QColor("#415687"))
    weather = QImage(width, height, QImage.Format.Format_RGB888)
    weather.fill(QColor("#8b390a"))
    monkeypatch.setattr(gpu_spheres, "_earth_textures", lambda *_: (terrain, weather))

    first = DetailTextureCache(tmp_path)
    assert gpu_spheres.SurfaceTextures(first)._get_texture(1, 1, "surface", "planet-a") == terrain
    first._writer.shutdown(wait=True)
    assert len(list(tmp_path.rglob("*.png"))) == 2

    def fail_if_baked(*args):
        raise AssertionError("A persisted texture should not be generated again")

    monkeypatch.setattr(gpu_spheres, "_earth_textures", fail_if_baked)
    second = DetailTextureCache(tmp_path)
    provider = gpu_spheres.SurfaceTextures(second)
    assert provider._get_texture(1, 1, "surface", "planet-a").pixelColor(20, 12) == QColor("#415687")
    assert provider._get_texture(1, 1, "weather", "planet-a").pixelColor(20, 12) == QColor("#8b390a")
    second.delete("planet-a")
    # A request that started just before deletion must not put the files back.
    second.store("planet-a", (((1, 1, "surface"), terrain),))
    second._writer.shutdown(wait=True)
    assert not list(tmp_path.rglob("*.png"))


def test_cache_keeps_one_variant_and_cleans_unrestored_planets_on_launch(tmp_path):
    image = QImage(32, 24, QImage.Format.Format_RGB888)
    image.fill(QColor("#555555"))
    cache = DetailTextureCache(tmp_path)
    cache.store("saved", (((1, 1, "surface"), image), ((1, 1, "weather"), image)))
    cache.store("saved", (((2, 4, "surface"), image),))
    cache.store("ephemeral", (((1, 8, "surface"), image),))
    cache._writer.shutdown(wait=True)
    assert len(list(tmp_path.rglob("*.png"))) == 2

    restarted = DetailTextureCache(tmp_path)
    restarted.retain(["saved"])
    restarted._writer.shutdown(wait=True)
    assert [path.name for path in tmp_path.rglob("*.png")] == ["2-4-surface.png"]

def test_cache_evicts_entire_old_planet_when_capacity_is_reached(tmp_path, monkeypatch):
    from os import utime

    from flashunstander import texture_cache

    image = QImage(64, 32, QImage.Format.Format_RGB888)
    image.fill(QColor("#4060a0"))
    first = DetailTextureCache(tmp_path)
    entries = (((1, 1, "surface"), image), ((1, 1, "weather"), image))
    first.store("old", entries)
    first._writer.shutdown(wait=True)
    old_files = list(tmp_path.rglob("*.png"))
    for path in old_files:
        utime(path, (1, 1))
    monkeypatch.setattr(texture_cache, "CACHE_LIMIT_BYTES", sum(path.stat().st_size for path in old_files))

    cache = DetailTextureCache(tmp_path)
    cache.store("new", entries)
    cache._writer.shutdown(wait=True)
    assert all(not path.exists() for path in old_files)
    assert len(list(tmp_path.rglob("*.png"))) == 2
