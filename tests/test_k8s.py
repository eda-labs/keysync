from __future__ import annotations

import unittest
from unittest.mock import Mock, call

from keysync.k8s import list_nodeusers


class ListNodeUsersTests(unittest.TestCase):
    def test_preserves_dashed_namespace(self) -> None:
        custom_api = Mock()
        custom_api.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "admin", "namespace": "fivestage-clos"},
                    "spec": {"username": "admin", "sshPublicKeys": []},
                }
            ]
        }

        result = list_nodeusers(custom_api, namespace=None)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].namespace, "fivestage-clos")
        self.assertEqual(result[0].name, "admin")
        self.assertEqual(result[0].username, "admin")

    def test_uses_trimmed_namespace_filter(self) -> None:
        custom_api = Mock()
        custom_api.list_namespaced_custom_object.return_value = {"items": []}

        _ = list_nodeusers(custom_api, namespace=" fivestage-clos ")

        custom_api.list_namespaced_custom_object.assert_called_once_with(
            group="core.eda.nokia.com",
            version="v1",
            namespace="fivestage-clos",
            plural="nodeusers",
        )
        custom_api.list_cluster_custom_object.assert_not_called()

    def test_follows_continue_pagination(self) -> None:
        custom_api = Mock()
        custom_api.list_cluster_custom_object.side_effect = [
            {
                "items": [
                    {
                        "metadata": {"name": "u1", "namespace": "ns-a"},
                        "spec": {"username": "u1", "sshPublicKeys": []},
                    }
                ],
                "metadata": {"continue": "token-1"},
            },
            {
                "items": [
                    {
                        "metadata": {"name": "u2", "namespace": "fivestage-clos"},
                        "spec": {"username": "u2", "sshPublicKeys": []},
                    }
                ],
                "metadata": {},
            },
        ]

        result = list_nodeusers(custom_api, namespace=None)

        self.assertEqual(
            [item.fq_name for item in result],
            ["fivestage-clos/u2", "ns-a/u1"],
        )
        self.assertEqual(
            custom_api.list_cluster_custom_object.mock_calls,
            [
                call(
                    group="core.eda.nokia.com",
                    version="v1",
                    plural="nodeusers",
                ),
                call(
                    group="core.eda.nokia.com",
                    version="v1",
                    plural="nodeusers",
                    _continue="token-1",
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
