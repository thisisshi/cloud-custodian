Require Labels on Resources on Creation or Update
=================================================

Custodian can deny resources from being created or updated unless the resource
has the required labels. In the example below, we require that all deployments
contain the labels "app", "owner", and "environment":

.. code-block::

   policies:
     - name: require-labels-deployments
       resource: k8s.deployment
       mode:
        type: k8s-validator
        on-match: deny
        operations:
          - CREATE
          - UPDATE
        filters:
          - or:
            - metadata.labels.app: absent
            - metadata.labels.owner: absent
            - metadata.labels.environment: absent
