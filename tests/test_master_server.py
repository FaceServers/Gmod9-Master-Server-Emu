import contextlib
import io
import socket
import struct
import unittest
from unittest import mock

import master_server


class LegacyAddressTests(unittest.TestCase):
    def test_endpoint_selection(self):
        cases = (
            ({'addr': '203.0.113.10:27016', 'gameport': 27015},
             ('203.0.113.10', 27015)),
            ({'addr': '203.0.113.10:27016', 'gameport': '27015'},
             ('203.0.113.10', 27015)),
            ({'addr': '198.51.100.20:27015'}, ('198.51.100.20', 27015)),
            ({'addr': '192.0.2.30:27015', 'gameport': 27015},
             ('192.0.2.30', 27015)),
        )
        for server, expected in cases:
            with self.subTest(server=server):
                self.assertEqual(
                    master_server.extract_legacy_server_address(server), expected
                )

    def test_invalid_values_are_safe(self):
        invalid_gameports = (0, 70000, 'bad', -1, True, 27015.0)
        invalid_addresses = (
            None, {}, {'addr': None}, {'addr': 'bad'},
            {'addr': '203.0.113.10:0'}, {'addr': '203.0.113.10:70000'},
        )
        with contextlib.redirect_stdout(io.StringIO()) as warnings:
            for gameport in invalid_gameports:
                self.assertEqual(
                    master_server.extract_legacy_server_address({
                        'addr': '203.0.113.10:27016', 'gameport': gameport,
                    }),
                    ('203.0.113.10', 27016),
                )
            for server in invalid_addresses:
                self.assertIsNone(
                    master_server.extract_legacy_server_address(server)
                )
        self.assertIn('[API WARN]', warnings.getvalue())

    def test_deduplicates_and_encodes_gameplay_port(self):
        servers = master_server.build_legacy_server_list([
            {'addr': '203.0.113.10:27016', 'gameport': 27015},
            {'addr': '198.51.100.20:27015'},
            {'addr': '203.0.113.10:27017', 'gameport': '27015'},
        ])
        self.assertEqual(servers, [
            {'ip': '203.0.113.10', 'port': 27015},
            {'ip': '198.51.100.20', 'port': 27015},
        ])

        with mock.patch.object(
            master_server, 'GAME_SERVERS', [('203.0.113.10', 27015)]
        ):
            payload = master_server.build_server_list_payload()
        self.assertEqual(
            payload,
            socket.inet_aton('203.0.113.10') + struct.pack('>H', 27015)
            + socket.inet_aton('0.0.0.0') + struct.pack('>H', 0),
        )


if __name__ == '__main__':
    unittest.main()
