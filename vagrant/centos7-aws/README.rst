Code for generating an EC2 instance

Usage:
------

|
|
1. Set the following environment variables

|
|

   * AWS_INSTANCE_TYPE (defaults to t2.micro)

   * AWS_KEY_PAIR (the EC2 key_pair used for your ec2 instance)

   * AWS_AMI (defaults to ami-c7d092f7)

   * AWS_KEY_FILENAME (this is the full path to your ssh private key file)

   * AWS_SECRET_ACCESS_KEY

   * AWS_REGION (defaults to us-west-2)

   * AWS_ACCESS_KEY_ID
|
|
2. initialize a VirtualEnv:

.. code-block:: bash

    $ virtualenv2 venv # it might be named 'virtualenv' in some distributions
    $ source venv/bin/activate
    $ pip2 install -r requirements.txt

|
|

3. Bring the box up

.. code-block:: bash

    $ fab it
|
|


4. Sync your code to the box

.. code-block:: bash

    $ export SOURCE_PATH=~/gits/flocker
    $ fab rsync
|
|

5. Run your tests from your laptop

.. code-block:: bash

    $ fab trial:flocker
    $ fab trial_as_root:flocker
|
|


6. ssh to it

.. code-block:: bash

    $ fab ssh
    $ fab ssh:'ls -l'
|
|


7. details about the EC2 instable are available through:

.. code-block:: bash

    $ fab status
|
|


8. When done:

.. code-block:: bash

    $ fab destroy
|
|


