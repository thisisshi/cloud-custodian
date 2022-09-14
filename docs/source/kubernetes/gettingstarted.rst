.. _kubernetes_gettingstarted:

Getting Started (Alpha)
=======================

The Kubernetes Provider (Alpha) is an optional package which an be installed to enable writing
policies which interact with Kubernetes related resources.


.. kubernetes_install-cc:

Install Kubernetes Plugin
-------------------------

First, ensure you have :ref:`installed the base Cloud Custodian application
<install-cc>`. Cloud Custodian is a Python application and must run on an
`actively supported <https://devguide.python.org/#status-of-python-branches>`_
version. 

Once the base install is complete, you are now ready to install the Kubernetes provider package
using one of the following options:

Option 1: Install released packages to local Python Environment
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

.. code-block:: bash

    pip install c7n
    pip install c7n_kube


Option 2: Install latest from the repository
"""""""""""""""""""""""""""""""""""""""""""""

.. code-block:: bash

    git clone https://github.com/cloud-custodian/cloud-custodian.git
    pip install -e ./cloud-custodian
    pip install -e ./cloud-custodian/tools/c7n_kube

.. _kubernetes_authenticate:

Connecting to your Cluster
--------------------------

The Custodian Kubernetes provider automatically uses your kubectl configuration or the config
file set by the environment variable ``KUBECONFIG``. See the `Kubernetes Docs <https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/>`_
for more information.

.. _kube_write-policy:

Write Your First Policy
-----------------------
A policy is the primary way that Custodian is configured to manage cloud resources.
It is a YAML file that follows a predetermined schema to describe what you want
Custodian to do.

There are three main components to a policy:

* Resource: the type of resource to run the policy against
* Filters: criteria to produce a specific subset of resources
* Actions: directives to take on the filtered set of resources

In the example below, we will write a policy that filters for pods with a label "custodian"
and deletes it:

Filename: ``custodian.yml``

.. code-block:: yaml

    policies:
      - name: my-first-policy
        description: |
          Deletes pods with label name:custodian
        resource: k8s.pod
        filters:
          - type: value
            key: metadata.labels.name
            value: custodian
        actions:
          - type: delete

.. _kube_run-policy:

Run Your Policy
---------------
First, ensure you have :ref:`configured connectivity to your cluster <kubernetes_authenticate>`.

Next, run the following command to execute the policy with Custodian:

.. code-block:: bash

   custodian run --output-dir=output custodian.yml --cache-period 0 -v

If successful, you should see output similar to the following on the command line::

  2022-09-14 12:28:38,735: custodian.cache:DEBUG Disabling cache
  2022-09-14 12:28:38,735: custodian.commands:DEBUG Loaded file pod.yaml. Contains 1 policies
  2022-09-14 12:28:38,736: custodian.output:DEBUG Storing output with <LogFile file://output/my-first-policy/custodian-run.log>
  2022-09-14 12:28:38,737: custodian.policy:DEBUG Running policy:pod resource:k8s.pod region:default c7n:0.9.18
  2022-09-14 12:28:38,754: custodian.k8s.client:DEBUG connecting to https://127.0.0.1:61427
  2022-09-14 12:28:38,819: custodian.resources.pod:DEBUG Filtered from 17 to 1 pod
  2022-09-14 12:28:38,820: custodian.policy:INFO policy:pod resource:k8s.pod region: count:1 time:0.08
  2022-09-14 12:28:38,837: custodian.k8s.client:DEBUG connecting to https://127.0.0.1:61427
  2022-09-14 12:28:38,863: custodian.policy:INFO policy:pod action:deleteresource resources:1 execution_time:0.04
  2022-09-14 12:28:38,864: custodian.output:DEBUG metric:ResourceCount Count:1 policy:pod restype:k8s.pod scope:policy

You should also find a new ``output/my-first-policy`` directory with a log and other
files (subsequent runs will append to the log by default, rather than
overwriting it).

See :ref:`filters` for more information on the features of the Value filter used in this sample.
