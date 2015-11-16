.. _clean-your-cluster:

========================
Cleaning up your Cluster
========================

If you have completed the steps in our :ref:`short tutorial <short-tutorial>`, you can run the following commands to clean up your volumes, your instances and your local files:

.. prompt:: bash $

    ssh -i $KEY root@$NODE2 docker rm -f app
    ssh -i $KEY root@$NODE2 docker rm -f redis
    uft-flocker-volumes list
    # Note the dataset id of the volume, then destroy it
    uft-flocker-volumes destroy --dataset=$DATASET_ID
    # Wait for the dataset to disappear from the list
    uft-flocker-volumes list
    # Once it's gone, go ahead and delete the nodes
    uft-flocker-destroy-nodes
    cd ~/clusters
    rm -rf test

.. note::

    If you wish to clean up your cluster manually, be sure to delete the instances that were created in your AWS console and the ``flocker_rules`` security group.
