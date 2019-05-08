.. _deployment:

Deployment
==========

In this section we will cover a few different deployment options for
Cloud Custodian.

.. _compliance_as_code:

Compliance as Code
------------------
When operating Cloud Custodian, it is highly recommended to treat the policy
files as code, similar to that of Terraform or CloudFormation files. Cloud
Custodian has a built-in dryrun mode and policy syntax validation which when
paired with an automated CI system, can help you release policies with confidence.

This tutorial assumes that you have working knowledge of Github, Git, Docker,
and a continuous integration tool (Jenkins, Drone, Travis, etc.).

To begin, start by checking your policy files into a source control management
tool like Github. This allows us to version and enable collaboration through
git pull requests and issues. In this example, we will be setting up a new repo
in Github.

First, set up a new repo in Github and grab the reporistory url. You don't need
need to add a README or any other files to it first.

.. code-block:: bash

    $ mkdir my-policies 
    $ cd my-policies
    $ git init
    $ git remote add origin <github repo url>
    $ touch policy.yml

Next, we'll add a policy to our new ``policy.yml`` file.

.. code-block:: yaml

    policies:
      - name: aws-vpcs
        resource: aws.vpc

Once you've added the policy to your policy file we can stage our changes from our
working directory and push it up to our remote:

.. code-block:: bash

    # this should show your policy.yml as an untracked file
    $ git status

    $ git add policy.yml
    $ git commit -m 'init my first policy'
    $ git push -u origin master

Once you've pushed your changes you should be able to see your new changes inside
of Github. Congratulations, you're now ready to start automatically validating and
testing your policies!

.. _continuous_integration_of_policies:

Continuous Integration of Policies
----------------------------------

Next, enable a CI webhook back to your CI system of choice when pull requests
targeting your master branch are opened or updated. This allows us to constantly
test and validate the policies that are being modified. You can use the tool
c7n_policystream to generate diffs between the current master version and the
proposed change in the pull request.

In this example, we will be using Microsoft Azure Devops Pipelines.

First, navigate to https://azure.microsoft.com/en-us/services/devops/pipelines/ and
click the "Start pipelines free with Github" button and follow the flow to connect
your Github account with Devops Pipelines.

Next click on the Piplines section in the left hand side of the sidebar and connect
with Github. Once the pipeline is setup, we can add the following azure devops
configuration to our repo:

.. code-block:: yaml

    trigger:
    - master
    
    jobs: 
      - job: 'Validate'
        pool:
          vmImage: 'Ubuntu-16.04'
        strategy:
          matrix:
            Python37:
              python.version: '3.7'
              TOXENV: py37
        steps:
          - checkout: self
          - task: UsePythonVersion@0
            displayName: "Set Python Version"
            inputs:
              versionSpec: '$(python.version)'
              architecture: 'x64'
          - script: pip install --upgrade pip
            displayName: Upgrade pip
          - script: pip install c7n
            displayName: Install custodian
          - script: custodian validate policy.yml
            displayName: Validate policy file

This configuration will install Cloud Custodian and validate the policy.yml file
that we created in the previous step.

Finally, we can run the new policies against your cloud environment in dryrun mode.
This mode will only query the resources and apply the filters on the resources. Doing
this allows you to assess the potential blast radius of a given policy change.

Setting up the automated dryrun of policies is left as an exercise to the user-- this
requires hosting your cloud authentication tokens inside of a CI system or hosting your
own CI system and using Managed Service Identities (Azure) or Instance Profiles (AWS).

It's important to verify that the results of the dryrun match your expectations. Custodian
is a very powerful tool that will do exactly what you tell it to do! In this case, you should
always "measure twice, cut once".


Advanced Continuous Integration Tips
------------------------------------

When policy files reach a sufficiently large size it can cause dryruns to execute for a
significantly long period of time. In most cases, the only thing that actually needs
to be tested would be the policies that were changed.

The following example will download the cloudcustodian/policystream image and
generate a policy file containing only the policies that changed between the most
recent commit and master.

.. code-block:: bash

    # in your git directory for policies
    $ docker pull cloudcustodian/policystream
    $ docker run -v $(pwd):/home/custodian/policies cloudcustodian > policystream-diff.yml
    $ custodian run -s output -v --dryrun policystream-diff.yml

After running your new policy file (policystream-diff.yml), the outputs will be stored
in the output directory.

.. _single_node_usage:

Single Node Deployment
----------------------

Now that your policies are stored and available in source control, you can now
fill in the next pieces of the puzzle to deploy. The simplest way to operate
Cloud Custodian is to start with running Cloud Custodian against a single account
on a virtual machine.

To start, create a virtual machine on your cloud provider of choice.
It's recommended to execute Cloud Custodian in the same cloud provider
that you are operating against to prevent a hard dependency on one cloud
to another.

Then, log into the instance and set up Custodian, following the instructions
in the  :ref:`install-cc` guide.

Once you have Cloud Custodian installed, download your policies that you created
in the :ref:`compliance_as_code` section. If using git, just simply do a ``git clone``::

    $ git clone <repository-url>

You now have your policies and custodian available on the instance. Typically, policies
that query the extant resources in the account/project/subscription should be run
on a regular basis to ensure that resources are constantly compliant. To do this you
can simply set up a cron job to run custodian on a set cadence.

.. _multi_account_execution:

Multi Account Execution
-----------------------

For more advanced setups, such as executing Custodian against multiple accounts, we
distribute the tool c7n-org. c7n-org utilizes a accounts configuration file and
assume roles to operate against multiple accounts, projects, or subscriptions in
parallel. More information can be found in tools/c7n-org.
