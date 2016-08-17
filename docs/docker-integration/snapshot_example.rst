=================================================
 A Jenkins Pipeline Using Docker Flocker Volumes
=================================================

An example of how Flocker's ability to create volumes from a snapshot might be used to run a Jenkins build pipeline for Flocker its self.

By storing the results of each build step in snapshot, the pipeline can be retried / resumed from the last successful step, in the event of a transient build failure.
e.g.
 * github was offline
 * Python package index (PyPI) was offline.
 * Build master was restarted
 * Build slave node went offline.

In this (pseudo code) example, a build is triggered for git commit ID ``aaabbbccc``

The ``docker`` CLI is talking to a Docker Swarm endpoint, which schedules the containers to the least loaded node in a cluster.

.. console:: sh

   GIT_COMMIT_ID="aaabbbccc"

   print "STEP 1: Clone the source code and checkout a branch"
   docker volume create \
       --name "build_aaabbbccc_1" \
       --driver flocker \
       --opt {size: 10GiB}

   # Run in foreground to wait for container to finish.
   docker run \
       --volume-driver flocker \
       --volume build_aaabbbccc_1:/artifacts \
       git clone --branch aaabbbccc \
           https://github.com/ClusterHQ/flocker.git /artifacts/source

   # Force a GCE snapshot of the volume.
   flocker-snapshot \
       --volume-name build_aaabbbccc_1 \
       --snapshot-name build_aaabbbccc_1

   # Delete the Docker Flocker volume
   # We can always recreate it later from the snapshot above.
   docker volume rm --name "build_aaabbbccc_1"



   print "STEP 2: Create a Python build environment installing all the Flocker requirements"
   docker volume create \
       --name "build_aaabbbccc_2" \
       --driver flocker \
       --opt {source_snapshot_name: build_aaabbbccc_1}
   docker run \
       --volume-driver flocker \
       --volume build_aaabbbccc_2:/artifacts \
       python-slim:2.7 -- \
         /bin/bash -c 'virtualenv /artifacts/venv && \
                       /artifacts/venv/bin/pip install --requirements /artifacts/source/dev-requirements.txt'
   flocker-snapshot \
       --volume-name build_aaabbbccc_2 \
       --snapshot-name build_aaabbbccc_2
   docker volume rm  --name "build_aaabbbccc_2"


   # Run unit tests for each of the Flocker sub packages in parallel
   # Each test runner will be run in an isolated container and *may* be
   # scheduled to separate nodes.
   # Temporary test state / output will be stored for later examination in case of test failures.

   unittest_tasks = AsyncTasks()
   for sub_package in [flocker.admin, flocker.common, flocker.control, flocker.node, ...]:
       with unittest_tasks.new() as task:
           print "STEP 3-${task.index}: trial ${sub_package}"
           docker volume create \
               --name "build_aaabbbccc_3-${task.index}" \
               --driver flocker \
               --opt "{source_snapshot_id: build_aaabbbccc_2}

           docker run \
               --volume-driver flocker \
               --volume build_aaabbbccc_3-${task.index}:/artifacts \
               python-slim:2.7
               sh -c "/artifacts/venv/bin/trial --temp-dir /artifacts/_trial_temp $sub_package"

           flocker-snapshot \
               --volume-name "build_aaabbbccc_3-${task.index}" \
               --snapshot-name "build_aaabbbccc_3-${task.index}"

           docker volume rm  --name "build_aaabbbccc_3-${task.index}"

   # Wait for all unit tests to pass
   unittest_tasks.wait()
