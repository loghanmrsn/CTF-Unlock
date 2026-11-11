from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image, PngImagePlugin
from ctf_unlock import text_tools as text, image_tools as image
from ctf_unlock.processes import Aborted


class TextTests(unittest.TestCase):
    def test_caesar_preserves_accents_case_and_26_choices(self):
        self.assertEqual(text.transform('César', 'Zebra été 42!', 1).text, 'Afcsb éué 42!')
        self.assertEqual(text.transform('ROT13', 'flag{CTF42}').text, 'synt{PGS42}')
        variants = text.transform('César · 26 décalages', 'abc').text.splitlines()
        self.assertEqual(len(variants), 26)
        self.assertEqual(variants[25], '25 : zab')

    def test_known_encoding_vectors_and_binary_kept(self):
        for encode, decode, expected in [
            ('Texte → hexadécimal','Hexadécimal → octets','68c3a9'),
            ('Texte → Base64','Base64 → octets','aMOp'),
            ('Texte → binaire','Binaire → octets','01101000 11000011 10101001'),
            ('Texte → URL','URL → octets','h%C3%A9'),
        ]:
            with self.subTest(encode=encode):
                encoded = text.transform(encode, 'hé').text
                self.assertEqual(encoded, expected)
                self.assertEqual(text.transform(decode, encoded).text, 'hé')
        raw = text.transform('Hexadécimal → octets', '00ff')
        self.assertIsNone(raw.text); self.assertEqual(raw.hex, '00ff')

    def test_strict_errors_and_limits(self):
        for operation, value in [('Base64 → octets','!!!!'), ('Base64 → octets','é'), ('Hexadécimal → octets','f'), ('Binaire → octets','101'), ('URL → octets','%zz')]:
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                text.transform(operation, value)
        with self.assertRaises(ValueError): text.transform('ROT13', 'a'*65537)
        with self.assertRaises(ValueError): text.transform('César · 26 décalages', 'a'*4097)

    def test_xor_known_key_and_rejects_empty_key(self):
        self.assertEqual(text.transform('XOR · clé hexadécimale', '040e0305', key='42').text, 'FLAG')
        with self.assertRaises(ValueError): text.transform('XOR · clé hexadécimale', '04', key='')


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='CTF pixels été ')
        self.root = Path(self.temp.name)
        self.path = self.root / 'image sans extension'
        source = Image.new('RGBA', (8, 2), (254, 0, 0, 255))
        for index, bit in enumerate(''.join(f'{item:08b}' for item in b'AB')):
            source.putpixel((index % 8, index // 8), (254 + int(bit), 0, 0, 255))
        metadata = PngImagePlugin.PngInfo(); metadata.add_text('Challenge', 'flag{metadata}')
        source.save(self.path, 'PNG', pnginfo=metadata)
        self.original = self.path.read_bytes()
        self.data = image.analyze_image(self.path)

    def tearDown(self):
        self.assertEqual(self.path.read_bytes(), self.original)
        self.temp.cleanup()

    def test_signature_metadata_palette_histogram_and_color(self):
        self.assertEqual(self.data.format, 'PNG')
        self.assertIn('flag{metadata}', self.data.metadata)
        self.assertEqual(self.data.sample_count, 16)
        self.assertEqual(sum(self.data.histograms[0]), 16)
        self.assertEqual(self.data.palette[0][0], '#FE0000')
        self.assertIn('21.00:1', image.color_info('#ffffff'))
        self.assertIn('21.00:1', image.color_info('#000000'))
        with self.assertRaises(ValueError): image.color_info('#ZZFFFF')

    def test_exact_bit_extraction_and_byte_order(self):
        self.assertEqual(image.extract_bits(self.data, 'R', 0, count=2), b'AB')
        self.assertEqual(image.extract_bits(self.data, 'R', 0, count=2, msb=False), b'\x82B')
        self.assertEqual(image.extract_bits(self.data, 'R', 0, start=8), b'B')
        self.assertEqual(image.extract_bits(self.data, 'R', 0, start=15), b'')
        with self.assertRaises(ValueError): image.extract_bits(self.data, count=65537)

    def test_views_channel_and_bitplane_preserve_original(self):
        inverted = image.view_image(self.data, 'Inversion')
        self.assertEqual(inverted.getpixel((0,0)), (1, 255, 255, 255))
        layer = image.view_image(self.data, 'Plan de bits', 'R', 0)
        self.assertEqual(layer.getpixel((0,0)), (0,0,0,255))
        self.assertEqual(layer.getpixel((1,0)), (255,255,255,255))
        alpha = image.view_image(self.data, 'Canal', 'A')
        self.assertEqual(alpha.getpixel((0,0)), (255,255,255,255))
        self.assertEqual(image.pixels(self.data).tobytes(), self.data.rgba)

    def test_transparency_and_jpeg_exif(self):
        transparent = self.root / 'transparent.png'
        Image.new('RGBA', (2,2), (200,0,0,0)).save(transparent)
        data = image.analyze_image(transparent)
        self.assertEqual(data.palette, ()); self.assertEqual(data.sample_count, 0)
        self.assertEqual(image.view_image(data, 'Inversion').getpixel((0,0))[3], 0)
        jpeg = self.root / 'photo.jpg'
        exif = Image.Exif(); exif[270] = 'CTF EXIF test'
        Image.new('RGB', (2,2), (1,2,3)).save(jpeg, exif=exif)
        self.assertIn('CTF EXIF test', image.analyze_image(jpeg).metadata)

    def test_new_png_export_no_overwrite_and_abort_cleanup(self):
        preview = image.view_image(self.data, 'Gris')
        target = self.root / 'nouveau.png'
        image.save_preview(preview, self.path, target)
        with Image.open(target) as actual: self.assertEqual(actual.tobytes(), preview.tobytes())
        for existing in [self.path, target]:
            with self.assertRaises(ValueError): image.save_preview(preview, self.path, existing)
        calls = []
        def abort():
            calls.append(1)
            return 'arrêt' if len(calls) > 1 else None
        cancelled = self.root / 'cancelled.png'
        with self.assertRaises(Aborted): image.save_preview(preview, self.path, cancelled, abort)
        self.assertFalse(cancelled.exists())

    def test_invalid_image_limits_and_cancellation(self):
        bad = self.root / 'invalid.png'; bad.write_bytes(b'not an image')
        with self.assertRaises(OSError): image.analyze_image(bad)
        with patch.object(image, 'MAX_FILE', 1), self.assertRaises(ValueError): image.analyze_image(self.path)
        with patch.object(image, 'MAX_PIXELS', 1), self.assertRaises(ValueError): image.analyze_image(self.path)
        with self.assertRaises(Aborted): image.analyze_image(self.path, lambda: 'arrêt')
        with self.assertRaises(Aborted): image.extract_bits(self.data, abort=lambda: 'arrêt')
