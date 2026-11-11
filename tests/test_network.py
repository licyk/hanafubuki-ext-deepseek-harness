"""Against the real nodejs.org and npm registry; run with ``HFX_NETWORK_TESTS=1``."""

from __future__ import annotations

import json
import os
import unittest
import urllib.request

import node_release
import spec

ONLINE = os.environ.get("HFX_NETWORK_TESTS") == "1"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


@unittest.skipUnless(ONLINE, "set HFX_NETWORK_TESTS=1 to reach nodejs.org and registry.npmjs.org")
class NetworkTest(unittest.TestCase):
    def test_latest_node_24_resolves_with_its_digest(self) -> None:
        index = json.loads(fetch(f"{node_release.DEFAULT_MIRROR}/index.json"))
        for platform, arch in (("linux", "x64"), ("macos", "arm64"), ("windows", "x64")):
            release = node_release.select(index, "24", platform, arch)
            self.assertGreaterEqual(spec.version_key(release.version)[:3], spec.MINIMUM_NODE)
            shasums = fetch(node_release.shasums_url(release)).decode()
            self.assertRegex(node_release.with_digest(release, shasums).sha256, r"^[0-9a-f]{64}$")
        self.assertTrue(node_release.select(index, "lts", "linux", "x64").version)

    def test_dsh_dist_tags(self) -> None:
        document = json.loads(fetch("https://registry.npmjs.org/@deepseek-ai%2Fdsh"))
        self.assertIn("latest", document["dist-tags"])
        self.assertIn(document["dist-tags"]["latest"], document["versions"])
        self.assertEqual(spec.issues({"version": document["dist-tags"]["latest"]}), {})


if __name__ == "__main__":
    unittest.main()
