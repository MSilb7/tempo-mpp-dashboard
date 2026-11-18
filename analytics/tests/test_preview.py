import unittest
from unittest.mock import patch
from http.server import SimpleHTTPRequestHandler
from scripts.preview import PreviewHandler


class PreviewTests(unittest.TestCase):
    def test_only_synthetic_assets_reach_file_handler(self):
        handler = object.__new__(PreviewHandler)
        for path in ['/', '/index.html', '/app.js', '/style.css', '/data/demo.json?cache=1']:
            handler.path = path
            with patch.object(SimpleHTTPRequestHandler, 'send_head', return_value='asset') as serve:
                self.assertEqual(handler.send_head(), 'asset')
                serve.assert_called_once()
        for path in ['/.local/live-analytics/latest.json', '/.env', '/.git/config',
                     '/docs/', '/data/', '/data/../.local/private.json', '/%2elocal/private.json']:
            handler.path = path
            with patch.object(handler, 'send_error') as error, patch.object(SimpleHTTPRequestHandler, 'send_head') as serve:
                handler.send_head()
                error.assert_called_once_with(404)
                serve.assert_not_called()
