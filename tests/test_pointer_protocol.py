"""Coordinate-only pointer and caret traffic through both public transports."""
import json
import socket
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from theater.service import Theater, UnixServer, make_http, request


class PointerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.theater = Theater(self.temp.name, seed=17)
        self.sock = Path(self.temp.name) / 'control.sock'
        self.server = UnixServer(self.sock, self.theater)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def layout(self, **extra):
        return dict(op='layout', layout_key='cursor-test', width_px=800, height_px=160) | extra

    def test_native_batch_preserves_move_click_release_order(self):
        events = [dict(kind=kind, x=.42, y=.5, button=0) for kind in ('move', 'down', 'up')]
        with patch.object(self.theater.world, 'pointer') as pointer:
            reply = request(self.sock, self.layout(pointer_events=events))
        self.assertTrue(reply['visible'])
        self.assertEqual([call.kwargs for call in pointer.call_args_list], events)

    def test_hidden_frame_releases_pointer_without_requiring_pixel_dimensions(self):
        with patch.object(self.theater.world, 'pointer') as pointer:
            reply = request(self.sock, {'op': 'layout', 'layout_key': 'hidden', 'visible': False})
        self.assertFalse(reply['visible'])
        pointer.assert_called_once_with('leave', 0, 0)

    def test_invalid_batch_applies_no_partial_click(self):
        events = [dict(kind='down', x=.4, y=.5), dict(kind='move', x=3.5, y=.2)]
        with patch.object(self.theater.world, 'pointer') as pointer:
            reply = request(self.sock, self.layout(pointer_events=events))
        self.assertFalse(reply['ok'])
        pointer.assert_not_called()

    def test_pointer_limits_and_malformed_coordinates_are_rejected(self):
        messages = [
            [],
            None,
            {'op': 'pointer', 'events': [dict(kind='move', x=float('nan'), y=.2)]},
            {'op': 'pointer', 'events': [dict(kind='move', x=10**1000, y=.2)]},
            {'op': 'pointer', 'events': [dict(kind='leave')]*65},
            {'op': 'pointer', 'kind': 'move', 'x': True, 'y': .4},
            {'op': 'pointer', 'kind': 'down', 'x': .4, 'y': .5, 'button': 42},
            self.layout(cursor={'x': 'draft text', 'y': 1.1}),
            self.layout(width_px=800.5),
        ]
        for message in messages:
            with self.subTest(message=message):
                reply = request(self.sock, message)
                self.assertFalse(reply['ok'])

    def test_caret_is_coordinate_metadata_and_text_is_not_retained(self):
        secret = 'input-stays-in-composer'
        with patch.object(self.theater.world, 'activity') as activity:
            reply = request(self.sock, self.layout(typing=True, cursor={'x': .32, 'y': 1.12}, draft=secret))
        self.assertTrue(reply['visible'])
        self.assertEqual(activity.call_args.kwargs['cursor'], {'x': .32, 'y': 1.12})
        state = request(self.sock, {'op': 'status'})
        self.assertNotIn(secret, json.dumps(state))

    def test_wide_multiline_caret_coordinates_are_preserved(self):
        with patch.object(self.theater.world, 'activity') as activity:
            reply = request(self.sock, self.layout(typing=True, cursor={'x': -8.0, 'y': 18.0}))
        self.assertTrue(reply['visible'])
        self.assertEqual(activity.call_args.kwargs['cursor'], {'x': -8.0, 'y': 18.0})

    def test_http_rejects_malformed_frame_query_and_negative_body_length(self):
        http = make_http(self.theater, 0)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(HTTPError) as raised:
                urlopen(f'http://127.0.0.1:{http.server_port}/api/frame?w=oops', timeout=2)
            self.assertEqual(raised.exception.code, 400)
            with socket.create_connection(('127.0.0.1', http.server_port), timeout=2) as client:
                client.sendall(b'POST /api/control HTTP/1.1\r\nHost: localhost\r\nContent-Length: -1\r\n\r\n')
                self.assertIn(b' 400 ', client.recv(1024).split(b'\r\n')[0])
        finally:
            http.shutdown()
            http.server_close()
            thread.join()

    def test_http_pointer_and_scaled_frame_use_same_geometry(self):
        http = make_http(self.theater, 0)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{http.server_port}'
        try:
            with urlopen(base+'/api/frame?w=1000&h=300') as response:
                self.assertEqual(response.headers['Content-Type'], 'image/png')
            body = {'op': 'pointer', 'width_px': 1000, 'height_px': 300,
                    'events': [dict(kind='move', x=.5, y=.25), dict(kind='leave')]}
            with patch.object(self.theater.world, 'pointer') as pointer:
                with urlopen(Request(base+'/api/control', data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})) as response:
                    self.assertTrue(json.load(response)['ok'])
            self.assertEqual([call.kwargs['kind'] for call in pointer.call_args_list], ['move', 'leave'])
        finally:
            http.shutdown()
            http.server_close()
            thread.join()
