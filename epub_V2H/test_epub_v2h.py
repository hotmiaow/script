#!/usr/bin/env python3
"""
Unit and integration tests for epub_v2h.py
"""

import os
import sys
import tempfile
import zipfile
import unittest
import subprocess
from pathlib import Path

from epub_v2h import (
    EpubConverter,
    find_epub_files,
    determine_conversion_action,
    process_batch
)


class TestEpubConverter(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_mock_epub(self, path: Path, layout: str, include_css: bool = True, text_sample: str = ""):
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w') as zf:
            zf.writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)
            zf.writestr('META-INF/container.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>''')
            spine_attr = 'page-progression-direction="rtl"' if layout == "vertical" else 'page-progression-direction="ltr"'
            manifest_css = '<item id="css" href="style.css" media-type="text/css"/>' if include_css else ''
            css_link = '<link rel="stylesheet" type="text/css" href="style.css"/>' if include_css else ''

            zf.writestr('OEBPS/content.opf', f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test Book ({layout})</dc:title>
    <dc:creator>Author Name</dc:creator>
  </metadata>
  <manifest>
    {manifest_css}
    <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine {spine_attr}>
    <itemref idref="ch1"/>
  </spine>
</package>''')

            if include_css:
                wm = "vertical-rl" if layout == "vertical" else "horizontal-tb"
                zf.writestr('OEBPS/style.css', f'''
body {{
  writing-mode: {wm};
  -webkit-writing-mode: {wm};
  -epub-writing-mode: {wm};
  font-family: serif;
}}
''')

            html_dir = 'dir="rtl"' if layout == "vertical" else 'dir="ltr"'
            zf.writestr('OEBPS/ch1.xhtml', f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" {html_dir}>
<head>
  <title>Chapter 1</title>
  {css_link}
</head>
<body {html_dir}>
  <p>{text_sample}</p>
</body>
</html>''')

    def test_detect_vertical_epub(self):
        v_path = self.test_dir / "vertical.epub"
        self._create_mock_epub(v_path, layout="vertical")
        conv = EpubConverter(str(v_path))
        self.assertEqual(conv.title, "Test Book (vertical)")
        self.assertEqual(conv.author, "Author Name")
        self.assertEqual(conv.current_layout, "vertical")
        self.assertEqual(conv.get_opposite_layout(), "horizontal")

    def test_detect_horizontal_epub(self):
        h_path = self.test_dir / "horizontal.epub"
        self._create_mock_epub(h_path, layout="horizontal")
        conv = EpubConverter(str(h_path))
        self.assertEqual(conv.current_layout, "horizontal")
        self.assertEqual(conv.get_opposite_layout(), "vertical")

    def test_convert_vertical_to_horizontal(self):
        v_path = self.test_dir / "sample_v.epub"
        sample_text = "他說：「這是一本『直排』書。」"
        self._create_mock_epub(v_path, layout="vertical", text_sample=sample_text)

        conv = EpubConverter(str(v_path))
        out_path = self.test_dir / "sample_v_to_h.epub"
        result = conv.convert("horizontal", output_path=str(out_path), convert_punctuation=True)

        self.assertTrue(Path(result).exists())

        with zipfile.ZipFile(result, 'r') as zf:
            mime_info = zf.getinfo('mimetype')
            self.assertEqual(mime_info.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(zf.namelist()[0], 'mimetype')
            self.assertEqual(zf.read('mimetype'), b'application/epub+zip')

            opf = zf.read('OEBPS/content.opf').decode('utf-8')
            self.assertIn('page-progression-direction="ltr"', opf)

            css = zf.read('OEBPS/style.css').decode('utf-8')
            self.assertIn('writing-mode: horizontal-tb', css)

            xhtml = zf.read('OEBPS/ch1.xhtml').decode('utf-8')
            self.assertIn('dir="ltr"', xhtml)
            self.assertNotIn('dir="rtl"', xhtml)
            self.assertIn('他說：“這是一本‘直排’書。”', xhtml)

    def test_convert_horizontal_to_vertical(self):
        h_path = self.test_dir / "sample_h.epub"
        sample_text = "他说：“这是一本‘横排’书。”"
        self._create_mock_epub(h_path, layout="horizontal", text_sample=sample_text)

        conv = EpubConverter(str(h_path))
        out_path = self.test_dir / "sample_h_to_v.epub"
        result = conv.convert("vertical", output_path=str(out_path), convert_punctuation=True)

        self.assertTrue(Path(result).exists())

        with zipfile.ZipFile(result, 'r') as zf:
            opf = zf.read('OEBPS/content.opf').decode('utf-8')
            self.assertIn('page-progression-direction="rtl"', opf)

            css = zf.read('OEBPS/style.css').decode('utf-8')
            self.assertIn('writing-mode: vertical-rl', css)

            xhtml = zf.read('OEBPS/ch1.xhtml').decode('utf-8')
            self.assertIn('他说：「这是一本『横排』书。」', xhtml)

    def test_convert_no_css_injection(self):
        h_path = self.test_dir / "no_css.epub"
        self._create_mock_epub(h_path, layout="horizontal", include_css=False, text_sample="No external CSS")

        conv = EpubConverter(str(h_path))
        out_path = self.test_dir / "no_css_to_v.epub"
        result = conv.convert("vertical", output_path=str(out_path))

        with zipfile.ZipFile(result, 'r') as zf:
            xhtml = zf.read('OEBPS/ch1.xhtml').decode('utf-8')
            self.assertIn('writing-mode: vertical-rl !important', xhtml)

    def test_find_epub_files_recursive(self):
        # Create files in root and subdirectories
        self._create_mock_epub(self.test_dir / "root1.epub", "vertical")
        self._create_mock_epub(self.test_dir / "sub" / "nested.epub", "horizontal")
        (self.test_dir / "ignore.txt").write_text("not epub")

        flat_epubs = find_epub_files(self.test_dir, recursive=False)
        self.assertEqual(len(flat_epubs), 1)
        self.assertEqual(flat_epubs[0].name, "root1.epub")

        rec_epubs = find_epub_files(self.test_dir, recursive=True)
        self.assertEqual(len(rec_epubs), 2)
        names = {p.name for p in rec_epubs}
        self.assertEqual(names, {"root1.epub", "nested.epub"})

    def test_filter_only_v2h(self):
        # Folder with 2 vertical and 2 horizontal books
        v1 = self.test_dir / "v1.epub"
        v2 = self.test_dir / "v2.epub"
        h1 = self.test_dir / "h1.epub"
        h2 = self.test_dir / "h2.epub"

        self._create_mock_epub(v1, "vertical")
        self._create_mock_epub(v2, "vertical")
        self._create_mock_epub(h1, "horizontal")
        self._create_mock_epub(h2, "horizontal")

        epubs = [v1, v2, h1, h2]

        out_dir = self.test_dir / "out_v2h"
        conv_c, skip_c, fail_c = process_batch(epubs, mode="only_v2h", output_dir=out_dir)

        self.assertEqual(conv_c, 2)
        self.assertEqual(skip_c, 2)
        self.assertEqual(fail_c, 0)

        # Check that only v1 and v2 were converted
        self.assertTrue((out_dir / "v1_horizontal.epub").exists())
        self.assertTrue((out_dir / "v2_horizontal.epub").exists())
        self.assertFalse((out_dir / "h1_vertical.epub").exists())
        self.assertFalse((out_dir / "h2_vertical.epub").exists())

    def test_filter_only_h2v(self):
        v1 = self.test_dir / "v1.epub"
        h1 = self.test_dir / "h1.epub"
        h2 = self.test_dir / "h2.epub"

        self._create_mock_epub(v1, "vertical")
        self._create_mock_epub(h1, "horizontal")
        self._create_mock_epub(h2, "horizontal")

        epubs = [v1, h1, h2]

        out_dir = self.test_dir / "out_h2v"
        conv_c, skip_c, fail_c = process_batch(epubs, mode="only_h2v", output_dir=out_dir)

        self.assertEqual(conv_c, 2)
        self.assertEqual(skip_c, 1)
        self.assertEqual(fail_c, 0)

        self.assertTrue((out_dir / "h1_vertical.epub").exists())
        self.assertTrue((out_dir / "h2_vertical.epub").exists())
        self.assertFalse((out_dir / "v1_horizontal.epub").exists())

    def test_cli_folder_v2h(self):
        folder = self.test_dir / "books"
        v = folder / "vert.epub"
        h = folder / "horiz.epub"
        self._create_mock_epub(v, "vertical")
        self._create_mock_epub(h, "horizontal")

        # Run CLI with --dir and --only-v2h
        res = subprocess.run(
            ["python3", "epub_v2h.py", "--dir", str(folder), "--only-v2h"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("1 converted, 1 skipped, 0 failed", res.stdout)
        self.assertTrue((folder / "vert_horizontal.epub").exists())
        self.assertFalse((folder / "horiz_vertical.epub").exists())


if __name__ == '__main__':
    unittest.main()
