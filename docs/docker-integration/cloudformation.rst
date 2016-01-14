.. _cloudformation:

.. raw:: html

    <style>
        .toctree-wrapper { display:none; }
    </style>

=========================================================
Installing Flocker with Swarm on AWS using CloudFormation
=========================================================

The steps in this guide enable you to quickly deploy a Flocker/Swarm cluster, which uses four AWS EC2 instances.

.. raw:: html
	
	<div style="width:60%; margin-left:auto; margin-right:auto; margin-bottom:2em;">
	
.. figure:: ../images/cloudformation.png
    :alt: A diagram illustrating a cluster of four AWS EC2 instances running Flocker with Docker Swarm.

.. raw:: html
	
	</div>

This diagram illustrates the cluster of four EC2 instances created by completing the CloudFormation steps below, and what each instance node in the cluster is running.

.. source material for this image: https://drive.google.com/open?id=0ByymF9bLBknGeXlPX1pTdXVZOGM

.. raw:: html
	
	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 1</h2>
			<p>Create an AWS Key Pair for secure login to your cluster.</p>
		</div>
		<div class="step-stages__step first">
			<img src="/_images/01-keys-menu.png" alt="AWS key pairs section in console"/>
            <span><a href="https://console.aws.amazon.com/ec2/v2/home?region=us-east-1#KeyPairs:sort=keyName" target="_blank">Log in to the AWS console</a>, "N. Virginia" region, "Key Pairs" section.</span>
		</div>
		<div class="step-stages__step">
			<img src="/_images/02-create-key.png" alt="Creating a new AWS key pair"/>
            <span>Give your key pair a meaningful name, like <strong>flocker-test</strong>. You'll need this later.</span>
		</div>
		<div class="step-stages__step">
			<img src="/_images/03-pem-downloaded.png" alt="A downloaded pem file"/>
            <span>The private key (.pem file) will be downloaded onto your computer.</span>
		</div>
	</div>
	
	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 2</h2>
			<p>Create a Flocker cluster using our CloudFormation template:
            <br />
			<a href="https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?templateURL=https:%2F%2Fs3.amazonaws.com%2Finstaller.downloads.clusterhq.com%2Fflocker-cluster.cloudformation.json" class="button" target="_blank" align="middle">Launch Flocker CloudFormation</a>
            <br />
			This button will open CloudFormation in a new tab.</p>
		</div>
		<div class="step-stages__step first">
			<img src="/_images/11-cloudformation-stackname.png" alt="Specifying the stack name"/>
			<span>Enter a <code>Stack name</code>. This can be any descriptive name.</span> 
		</div>
		<div class="step-stages__step">
			<img src="/_images/12-cloudformation-settings.png" alt="Fill in cloudformation settings"/>
			<span>Enter your AWS <code>AccessKeyID</code> and <code>SecretAccessKey</code> which you can access from <a href="https://console.aws.amazon.com/iam/home?nc2=h_m_sc#security_credential" target="_blank">here</a> and your <code>KeyName</code> from Step 1.</span>
		</div>
		<div class="step-stages__step">
			<img src="/_images/13-cloudformation-create.png" alt="Click create"/>
			<span>Click "Next" twice and then click "Create" to create your cluster.</span>
		</div>
	</div>

	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 3</h2>
			<p>Wait for the cluster to come up. This can take 5-10 minutes.</p>
		</div>
		<div class="step-stages__step first">
			<img src="/_images/21-refresh.png" alt="Refresh button on CloudFormation console"/>
			<span>The stack may not show up immediately. Click the refresh button a few times to see it show up.</span>
		</div>
		<div class="step-stages__step">
			<img src="/_images/22-create-in-progress.png" alt="Stack create in progress message"/>
			<span>Once the stack shows up, it will stay in CREATE_IN_PROGRESS state for 5-10 minutes. Wait for it to transition to...</span> 
		</div>
		<div class="step-stages__step">
			<img src="/_images/23-create-complete.png" alt="Stack create create complete message"/>
			<span>... CREATE_COMPLETE state. Then click the "Outputs" tab...</span> 
		</div>
	</div>
	
	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 4</h2>
			<p>Verify your installation.</p>
            <p>Click on the "Outputs" tab for your stack. These values will be used for connecting to your cluster both for the next step and for any tutorials you go through.</p>
			<img src="/_images/31-stack-outputs.png" alt="Stack outputs in CloudFormation" style="margin: 2em 0;"/>
            <p>Now follow along with these commands to log in and verify your cluster is working. Where a command has a value <code>&lt;LikeThis&gt;</code>, use the values from the Outputs tab as shown above.</p>
            <p>Where the commands have <code>&lt;KeyPath&gt;</code> which should be the path on your host to the <code>.pem</code> file you downloaded in Step 1, for example: <code>~/Downloads/flocker-test.pem</code>.</p>
            <div style="text-align: left; margin: 2em 0;">

.. prompt:: bash

   ssh -i <KeyPath> ubuntu@<ClientNodeIP>
   export DOCKER_HOST=<ControlNodeIP>:2376
   docker info |grep Nodes # should output "Nodes: 2"
   export FLOCKER_CERTS_PATH=/etc/flocker
   export FLOCKER_USER=user1
   export FLOCKER_CONTROL_SERVICE=<ControlNodeIP>
   flockerctl status # should show two nodes running
   flockerctl ls # should show no datasets yet
   # TODO make flockerctl work like this (with env vars)

.. raw:: html

            </div>
            <p>If the output matches, this shows that you have two nodes in your Swarm cluster and two nodes in your Flocker cluster!</p>            
		</div>
	</div>
	
	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">That's it!</h2>
			<p>Your cluster is now ready for workloads!</p>
		</div>
		<div class="step-stages__step first">
			<span> </span> 
		</div>
		<div class="step-stages__step">
			<a href="tutorial-swarm-compose.html" class="button">Try a Tutorial</a>
		</div>
		<div class="step-stages__step">
			<span> </span> 
		</div>
    </div>


.. raw:: html

   <div style="display:none;">

.. image:: /images/tutorial-swarm-compose/01-keys-menu.png
.. image:: /images/tutorial-swarm-compose/02-create-key.png
.. image:: /images/tutorial-swarm-compose/03-pem-downloaded.png
.. image:: /images/tutorial-swarm-compose/11-cloudformation-stackname.png
.. image:: /images/tutorial-swarm-compose/12-cloudformation-settings.png
.. image:: /images/tutorial-swarm-compose/13-cloudformation-create.png
.. image:: /images/tutorial-swarm-compose/21-refresh.png
.. image:: /images/tutorial-swarm-compose/22-create-in-progress.png
.. image:: /images/tutorial-swarm-compose/23-create-complete.png
.. image:: /images/tutorial-swarm-compose/31-stack-outputs.png

.. raw:: html

   </div>
