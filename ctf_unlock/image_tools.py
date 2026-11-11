"""Observation d'images et extraction explicite de bits, sans décryptage automatique."""
import colorsys
from dataclasses import dataclass
from pathlib import Path
import warnings
from PIL import Image, ImageOps, PngImagePlugin
from .processes import Aborted

MAX_PIXELS, MAX_FILE = 4000000, 20 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
PngImagePlugin.MAX_TEXT_CHUNK = 1024 * 1024
PngImagePlugin.MAX_TEXT_MEMORY = 4 * 1024 * 1024


def check(abort):
    reason = abort()
    if reason:
        raise Aborted(reason)


@dataclass(frozen=True)
class ImageData:
    source: Path
    width: int
    height: int
    format: str
    mode: str
    rgba: bytes
    metadata: str
    palette: tuple
    histograms: tuple
    sample_count: int


def color_info(value):
    value = value.lstrip('#')
    if len(value) != 6 or any(char not in '0123456789abcdefABCDEF' for char in value):
        raise ValueError('Couleur attendue : #RRGGBB.')
    rgb = tuple(int(value[i:i+2], 16) for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(*(item / 255 for item in rgb))
    linear = [item / 255 / 12.92 if item / 255 <= .04045 else ((item / 255 + .055) / 1.055) ** 2.4 for item in rgb]
    luminance = sum(item * weight for item, weight in zip(linear, (.2126, .7152, .0722)))
    return f'#{value.upper()} · RGB {rgb} · HSV {h*360:.1f}° / {s*100:.1f}% / {v*100:.1f}%\nLuminance sRGB {luminance:.4f} · contraste noir {(luminance+.05)/.05:.2f}:1 · blanc {1.05/(luminance+.05):.2f}:1'


def analyze_image(path, abort=lambda: None):
    source = Path(path).resolve(strict=True)
    if source.stat().st_size > MAX_FILE:
        raise ValueError('Image limitée à 20 Mio.')
    check(abort)
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(source, formats=['PNG', 'JPEG', 'BMP', 'GIF', 'WEBP']) as image:
            if image.width * image.height > MAX_PIXELS or image.mode not in ('1', 'L', 'LA', 'P', 'RGB', 'RGBA', 'CMYK'):
                raise ValueError('Image limitée à 4 millions de pixels et aux modes 8 bits usuels.')
            fmt, mode = image.format, image.mode
            metadata = [f'{key}: {str(value)[:1000]}' for key, value in image.info.items() if key not in ('icc_profile', 'exif')][:64]
            exif = image.getexif()
            metadata += [f'EXIF {key}: {str(value)[:1000]}' for key, value in list(exif.items())[:64]]
            rgba = image.convert('RGBA'); raw = rgba.tobytes()
    check(abort)
    step = max(1, (rgba.width * rgba.height + 65535) // 65536)
    histograms = [[0] * 256 for _ in range(3)]
    buckets, count = {}, 0
    for pixel in range(0, rgba.width * rgba.height, step):
        if pixel % 4096 == 0:
            check(abort)
        r, g, b, a = raw[pixel*4:pixel*4+4]
        if not a:
            continue
        count += 1
        for histogram, channel in zip(histograms, (r, g, b)):
            histogram[channel] += 1
        key = (r >> 4, g >> 4, b >> 4)
        bucket = buckets.setdefault(key, [0, 0, 0, 0])
        for i, channel in enumerate((r, g, b)):
            bucket[i] += channel
        bucket[3] += 1
    palette = tuple(('#' + ''.join(f'{round(channel / bucket[3]):02X}' for channel in bucket[:3]), bucket[3] / max(count, 1)) for bucket in sorted(buckets.values(), key=lambda item: item[3], reverse=True)[:8])
    return ImageData(source, rgba.width, rgba.height, fmt, mode, raw, '\n'.join(metadata) or 'Aucune métadonnée lisible.', palette, tuple(tuple(row) for row in histograms), count)


def pixels(data):
    return Image.frombytes('RGBA', (data.width, data.height), data.rgba)


def view_image(data, mode='Original', channel='R', bit=0, abort=lambda: None):
    check(abort)
    image = pixels(data)
    if mode == 'Inversion':
        rgb = ImageOps.invert(image.convert('RGB')).convert('RGBA'); rgb.putalpha(image.getchannel('A')); image = rgb
    elif mode == 'Gris':
        gray = ImageOps.grayscale(image).convert('RGBA'); gray.putalpha(image.getchannel('A')); image = gray
    elif mode in ('Canal', 'Plan de bits'):
        if channel not in 'RGBA' or len(channel) != 1 or not 0 <= bit <= 7:
            raise ValueError('Canal/bit invalide.')
        layer = image.getchannel(channel)
        if mode == 'Plan de bits':
            layer = layer.point([255 if (item >> bit) & 1 else 0 for item in range(256)])
        image = layer.convert('RGBA')
    elif mode != 'Original':
        raise ValueError('Vue image non prise en charge.')
    check(abort)
    return image


def extract_bits(data, channels='RGB', bit=0, start=0, count=1024, msb=True, abort=lambda: None):
    if channels not in ('R', 'G', 'B', 'A', 'RGB', 'RGBA') or not 0 <= bit <= 7 or not 0 <= start < data.width * data.height or not 1 <= count <= 65536:
        raise ValueError('Paramètres d’extraction invalides (64 Kio maximum).')
    indexes = ['RGBA'.index(char) for char in channels]
    output, value, filled = bytearray(), 0, 0
    for pixel in range(start, data.width * data.height):
        if pixel % 4096 == 0:
            check(abort)
        for index in indexes:
            digit = (data.rgba[pixel*4+index] >> bit) & 1
            value |= digit << ((7-filled) if msb else filled)
            filled += 1
            if filled == 8:
                output.append(value); value = filled = 0
                if len(output) >= count:
                    check(abort); return bytes(output)
    check(abort)
    return bytes(output)


def save_preview(image, original, path, abort=lambda: None):
    target = Path(path).resolve()
    if target == Path(original).resolve() or target.exists():
        raise ValueError('Choisissez un nouveau fichier PNG, sans remplacer un fichier existant.')
    check(abort)
    created = False
    try:
        with target.open('xb') as stream:
            created = True
            image.save(stream, format='PNG')
        check(abort)
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise
    return str(target)
