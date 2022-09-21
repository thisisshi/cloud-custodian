from test_policy import TestAdmissionControllerMode


class TestEventDeployment(TestAdmissionControllerMode):
    def test_deployment_ensure_registry(self):
        factory = self.replay_flight_data()
        p = self.load_policy(
            {
                'name': 'ensure-image-registry',
                'resource': 'k8s.deployment',
                'mode': {
                    'type': 'k8s-validator',
                    'on-match': 'warn',
                    'operations': ['CREATE']
                },
                'actions': [
                    {
                        'type': 'event-ensure-registry',
                        'registry': 'myregistry.com',
                    }
                ]
            },
            session_factory=factory
        )
        event = self.get_event('create_deployment')
        result, resources = p.push(event)
        self.assertEqual(len(resources[0]['c7n:patches']), 1)
        self.assertEqual(
            resources[0]['c7n:patches'][0],
            {
                'op': 'replace',
                'path': '/spec/template/spec/containers/0/image',
                'value': 'myregistry.com/nginx'
            }
        )
