Code for generating an EC2 instance

Usage:
------

|
|
1. Set the following environment variables

|
|

   * AWS_INSTANCE_TYPE

   * AWS_KEY_PAIR

   * AWS_AMI

   * AWS_KEY_FILENAME

   * AWS_SECRET_ACCESS_KEY

   * AWS_REGION

   * AWS_ACCESS_KEY_ID
|
|
2. initialize a VirtualEnv:

.. code-block:: bash

    $ virtualenv2 venv
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

    $ fab rsync
|
|


5. ssh to it

.. code-block:: bash

    $ fab ssh
|
|


6. details about the EC2 instable are available through:

.. code-block:: bash

    $ fab status
|
|


6. When done:

.. code-block:: bash

    $ fab destroy
|
|


