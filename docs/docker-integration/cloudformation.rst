.. _cloudformation:

.. raw:: html

    <style>
        .toctree-wrapper { display:none; }
    </style>

=========================================================
Installing Flocker with Swarm on AWS using CloudFormation
=========================================================

The steps in this guide enable you to quickly deploy a Flocker/Swarm cluster, as illustrated below, which will create four EC2 instances on your AWS account:

.. raw:: html

	<div style="width:80%; margin-left:auto; margin-right:auto; margin-bottom:2em;">

.. figure:: ../images/cloudformation.png
    :alt: A diagram illustrating a cluster of four AWS EC2 instances running Flocker with Docker Swarm.

.. raw:: html

	</div>

Follow the steps below to create your cluster.
Once it's up and running we'll guide you through a tutorial to deploy a sample app.

.. source material for this image: https://drive.google.com/open?id=0ByymF9bLBknGeXlPX1pTdXVZOGM

.. raw:: html

	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 1</h2>
			<p>Create an AWS Key Pair for secure login to your cluster.</p>
		</div>
		<div class="step-stages__step first">
			<img src="../_images/01-keys-menu.png" alt="AWS key pairs section in console"/>
            <span><a href="https://console.aws.amazon.com/ec2/v2/home?region=us-east-1#KeyPairs:sort=keyName" target="_blank">Log in to the AWS console</a>. This will open "N. Virginia" region, "Key Pairs" section.</span>
		</div>
		<div class="step-stages__step">
			<img src="../_images/02-create-key.png" alt="Creating a new AWS key pair"/>
            <span>Click "Create Key Pair". Give your key pair a meaningful name, like <strong>flocker-test</strong>. You'll need this later.</span>
		</div>
		<div class="step-stages__step">
			<img src="../_images/03-pem-downloaded.png" alt="A downloaded pem file"/>
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
			This button will open CloudFormation in a new window.</p>
		</div>
		<div class="step-stages__step first">
			<img src="../_images/11-cloudformation-stackname.png" alt="Specifying the stack name"/>
			<span>Click "Next". Enter a <code>Stack name</code>. This can be any descriptive name.</span>
		</div>
		<div class="step-stages__step">
			<img src="../_images/12-cloudformation-settings.png" alt="Fill in cloudformation settings"/>
			<span>Enter your <code>KeyName</code> from Step 1. Then enter your AWS <code>AccessKeyID</code> and <code>SecretAccessKey</code> credentials.</span><span>If you don't know these, <a href="javascript:void(0);" onclick="$('#iam-instructions').show();">click here</a>.</span>
            <span>Optionally, <a href="https://clusterhq.com/volumehub/" target="_blank">register for a Volume Hub account</a> which provides a hosted web interface to see what's going on in your cluster, then once you're logged in, <a href="https://volumehub.clusterhq.com/v1/token" target="_blank">fetch the token from here</a> by copying the token, not including the quotes.</span>
            <div id="iam-instructions" style="text-align:left; display:none;">
                <span>You can generate new credentials on your <a href="https://console.aws.amazon.com/iam/home#users" target="_blank">IAM Users</a> page:</span>
                <span><ul><li>Click on your user and go to the "Security Credentials" tab.</li><li>Click "Create Access Key".</li><li>Click "Show User Security Credentials".</li></ul></span>
            </div>
		</div>
		<div class="step-stages__step">
			<img src="../_images/13-cloudformation-create.png" alt="Click create"/>
			<span>Click "Next" twice and then click "Create" to create your cluster.</span>
		</div>
	</div>

	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">The waiting bit!</h2>
			<p>Wait for the cluster to come up. This can take 5-10 minutes.</p>
		</div>
		<div class="step-stages__step first">
			<img src="../_images/21-refresh.png" alt="Refresh button on CloudFormation console"/>
			<span>The stack may not show up immediately. Click the refresh button a few times to see it show up.</span>
		</div>
		<div class="step-stages__step">
			<img src="../_images/22-create-in-progress.png" alt="Stack create in progress message"/>
			<span>Once the stack shows up, it will stay in CREATE_IN_PROGRESS state for 5-10 minutes. Wait for it to transition to...</span>
		</div>
		<div class="step-stages__step">
			<img src="../_images/23-create-complete.png" alt="Stack create create complete message"/>
			<span>... CREATE_COMPLETE state.</span>
		</div>
	</div>

	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 3</h2>
			<p>Verifying your installation.</p>
            <p>Click on the "Outputs" tab for your stack. If this is not visible, click the drop down icon on the current tab.</p>
            <p>The values displayed on this tab will be used for verifying your installation and also any tutorials you go through.</p>
			<img src="../_images/31-stack-outputs.png" alt="Stack outputs in CloudFormation" style="margin: 2em 0;"/>
            <p>Now open a Terminal window, and run the following commands to log in and verify your cluster is working.</p>
            <p>Where a command includes a string like <code>&lt;ClientNodeIP&gt;</code>, use the corresponding value from the Outputs tab.</p>
            <p>Where a command has <code>&lt;KeyPath&gt;</code> this should be the path on your machine to the <code>.pem</code> file you downloaded in Step 1, for example: <code>~/Downloads/flocker-test.pem</code>.</p>
            <div style="text-align: left; margin: 2em 0;">

.. prompt:: bash

   chmod 0600 <KeyPath>
   ssh -i <KeyPath> ubuntu@<ClientNodeIP> # enter "yes" if prompted
   export FLOCKER_CERTS_PATH=/etc/flocker
   export FLOCKER_USER=user1
   export FLOCKER_CONTROL_SERVICE=<ControlNodeIP> # not ClientNodeIP!
   flockerctl status # should list two servers (nodes) running
   flockerctl ls # should display no datasets yet
   export DOCKER_TLS_VERIFY=1
   export DOCKER_HOST=tcp://<ControlNodeIP>:2376
   docker info |grep Nodes # should output "Nodes: 2"
   exit

.. raw:: html

            </div>
            <p>If the commands succeeded, then your Flocker/Swarm cluster is up and running.</p>
		</div>
	</div>

	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">That's it!</h2>
			<p>Your cluster is now ready for workloads.</p>
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

.. image:: /images/installer-swarm-compose/01-keys-menu.png
.. image:: /images/installer-swarm-compose/02-create-key.png
.. image:: /images/installer-swarm-compose/03-pem-downloaded.png
.. image:: /images/installer-swarm-compose/11-cloudformation-stackname.png
.. image:: /images/installer-swarm-compose/12-cloudformation-settings.png
.. image:: /images/installer-swarm-compose/13-cloudformation-create.png
.. image:: /images/installer-swarm-compose/21-refresh.png
.. image:: /images/installer-swarm-compose/22-create-in-progress.png
.. image:: /images/installer-swarm-compose/23-create-complete.png
.. image:: /images/installer-swarm-compose/31-stack-outputs.png

.. raw:: html

   </div>
