"""Experimental Qt Quick rendering layer for planet surfaces."""
from functools import lru_cache
from pathlib import Path

import numpy as np
from PySide6.QtCore import Property, QTimer, Signal, Slot, Qt, QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtQuick import QQuickImageProvider, QQuickView, QSGRendererInterface

from .cosmic import _generate_albedo
from .earth_material import earth_tile, refine_earth_tile
from .texture_cache import DetailTextureCache


DETAIL_TEXTURE_HEIGHT = 1152
TEXTURE_STRIP_ROWS = 96


def _padded_texture(rgb):
    # Periodic gutters survive bilinear filtering and the first mip levels.
    gutter = rgb.shape[1] // 32
    padded = np.concatenate((rgb[:, -gutter:], rgb, rgb[:, :gutter]), axis=1)
    height, width = padded.shape[:2]
    return QImage(padded.data, width, height, padded.strides[0], QImage.Format.Format_RGB888).copy()


def _double_longitude(field):
    field = field.astype(np.float32)
    wider = np.empty((field.shape[0], field.shape[1]*2, 3), dtype=np.float32)
    wider[:, ::2] = .75*field + .25*np.roll(field, 1, axis=1)
    wider[:, 1::2] = .75*field + .25*np.roll(field, -1, axis=1)
    return wider


def _double_latitudes(field, start, stop):
    rows = np.arange(start, stop)
    original = rows // 2
    adjacent = np.clip(original + 2*(rows % 2) - 1, 0, field.shape[0] - 1)
    return .75*field[original] + .25*field[adjacent]


@lru_cache(maxsize=4)
def _earth_textures(seed):
    height = DETAIL_TEXTURE_HEIGHT
    broad_height = height // 2
    color = np.empty((broad_height, broad_height*2, 3), dtype=np.uint8)
    weather = np.empty_like(color)
    for start in range(0, broad_height, TEXTURE_STRIP_ROWS):
        stop = min(broad_height, start + TEXTURE_STRIP_ROWS)
        color[start:stop], weather[start:stop] = earth_tile(seed, broad_height, start, stop)

    # Continental geometry is low-frequency. Bake it once, then compute
    # shoreline, terrain and cloud detail at the full map resolution.
    broad_color = _double_longitude(color)
    broad_weather = _double_longitude(weather)
    color = np.empty((height, height*2, 3), dtype=np.uint8)
    weather = np.empty_like(color)
    for start in range(0, height, TEXTURE_STRIP_ROWS):
        stop = min(height, start + TEXTURE_STRIP_ROWS)
        color[start:stop], weather[start:stop] = refine_earth_tile(
            seed, height, start, _double_latitudes(broad_color, start, stop),
            _double_latitudes(broad_weather, start, stop) / 255.,
        )
    return _padded_texture(color), _padded_texture(weather)


@lru_cache(maxsize=8)
def _surface_texture(kind, seed):
    if kind == 1:
        return _earth_textures(seed)[0]
    height = DETAIL_TEXTURE_HEIGHT
    rgb = np.empty((height, height*2, 3), dtype=np.uint8)
    for start in range(0, height, TEXTURE_STRIP_ROWS):
        stop = min(height, start + TEXTURE_STRIP_ROWS)
        rgb[start:stop] = _generate_albedo(kind, seed, height, gpu_texture=True, rows=(start, stop))
    return _padded_texture(rgb)


class SurfaceTextures(QQuickImageProvider):
    def __init__(self, cache=None):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._cache = DetailTextureCache() if cache is None else cache

    def requestImage(self, key, size, requested_size):
        kind, seed, _, *parts = key.split("/")
        kind, seed = int(kind), int(seed)
        channel = parts.pop() if parts and parts[-1] == "weather" else "surface"
        owner = parts[0] if parts else ""
        image = self._get_texture(kind, seed, channel, owner)
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image

    def _get_texture(self, kind, seed, channel, owner):
        height = DETAIL_TEXTURE_HEIGHT
        width = height * 2 + (height * 2 // 32) * 2
        cache_key = (kind, seed, channel)
        saved = self._cache.load(owner, cache_key, width, height) if owner else None
        if saved is not None:
            return saved
        if kind == 1:
            color, weather = _earth_textures(seed)
            if owner:
                self._cache.store(owner, (((1, seed, "surface"), color), ((1, seed, "weather"), weather)))
            return weather if channel == "weather" else color
        image = _surface_texture(kind, seed)
        if owner:
            self._cache.store(owner, ((cache_key, image),))
        return image


class GpuSphereLayer(QQuickView):
    frameChanged = Signal()
    orbitsChanged = Signal()
    preloadChanged = Signal()

    def __init__(self, cache=None):
        super().__init__()
        self._frame = []
        self._orbits = []
        self._preloads = []
        self._preload_plan = ()
        self._ready_preloads = set()
        self.setFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                      | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus
                      | Qt.WindowType.WindowTransparentForInput)
        surface_format = self.format()
        surface_format.setAlphaBufferSize(8)
        self.setFormat(surface_format)
        self.setColor(QColor(0, 0, 0, 0))
        self.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        self.engine().addImageProvider("planet", SurfaceTextures(cache))
        self.rootContext().setContextProperty("scene", self)
        self.setSource(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "GpuSphereScene.qml")))

    @Property("QVariantList", notify=frameChanged)
    def frame(self):
        return self._frame

    @Property("QVariantList", notify=orbitsChanged)
    def orbits(self):
        return self._orbits

    @Property("QVariantList", notify=preloadChanged)
    def preloads(self):
        return self._preloads

    def preload_detail(self, *keys):
        plan = tuple(dict.fromkeys(key for key in keys if key))
        if plan != self._preload_plan:
            self._preload_plan = plan
            self._ready_preloads.intersection_update(plan)
            self._update_preloads()

    @Slot(str)
    def detailReady(self, key):
        if key not in self._preload_plan or key in self._ready_preloads:
            return
        self._ready_preloads.add(key)
        QTimer.singleShot(0, self._update_preloads)

    def _update_preloads(self):
        keys = [key for key in self._preload_plan if key in self._ready_preloads]
        pending = next((key for key in self._preload_plan if key not in self._ready_preloads), None)
        if pending:
            keys.append(pending)
        if keys != self._preloads:
            self._preloads = keys
            self.preloadChanged.emit()

    def submit(self, frame, orbits):
        self._frame = frame
        if orbits != self._orbits:
            self._orbits = orbits
            self.orbitsChanged.emit()
        self.frameChanged.emit()

    def supported(self):
        api = self.rendererInterface().graphicsApi()
        return self.status() == QQuickView.Status.Ready and api not in (
            QSGRendererInterface.GraphicsApi.Software,
            QSGRendererInterface.GraphicsApi.Null,
            QSGRendererInterface.GraphicsApi.Unknown,
        )
