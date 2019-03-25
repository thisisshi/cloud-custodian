from common_kube import KubeTest


class TestCustomResource(KubeTest):
    def test_custom_cluster_resource_query(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'custom-resources',
                'resource': 'k8s.custom-cluster-resource',
                'query': [
                    {
                        'group': 'stable.example.com',
                        'version': 'v1',
                        'plural': 'crontabscluster'
                    }
                ]
            },
            session_factory=factory
        )

        resources = policy.run()
        self.assertTrue(resources)

    def test_custom_namespaced_resource_query(self):
        factory = self.replay_flight_data()
        policy = self.load_policy(
            {
                'name': 'custom-resources',
                'resource': 'k8s.custom-namespaced-resource',
                'query': [
                    {
                        'group': 'stable.example.com',
                        'version': 'v1',
                        'plural': 'crontabs'
                    }
                ]
            },
            session_factory=factory
        )

        resources = policy.run()
        self.assertTrue(resources)
