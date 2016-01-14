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
			<p><a href="https://console.aws.amazon.com/ec2/v2/home?region=us-east-1" target="_blank">Click here</a> to create a key pair in us-east-1.</p>
		</div>
		<div class="step-stages__step first">
			<img src="/_images/01-keys-menu.png" alt="AWS keys"/>
            <span>Click "Key Pairs" on the AWS console.</span>
		</div>
		<div class="step-stages__step">
			<img src="/_images/02-create-key.png" alt="AWS keys"/>
            <span>Give your Key Pair a meaningful name, like flocker-test. You'll need this later.</span>
		</div>
		<div class="step-stages__step">
			<img src="/_images/03-pem-downloaded.png" alt="AWS keys"/>
            <span>The private key (.pem file) will be downloaded onto your computer.</span>
		</div>
	</div>
	
	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 2</h2>
			<p>Create a Flocker cluster:</p>
			<a href="https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?templateURL=https:%2F%2Fs3.amazonaws.com%2Finstaller.downloads.clusterhq.com%2Fflocker-cluster.cloudformation.json" class="button" target="_blank" align="middle">Create Cluster</a>
			<p>(This button will open AWS CloudFormation in a new tab)</p>
		</div>
		<div class="step-stages__step first">
			<img src="http://filldunphy.com/780/439" alt="Relevent alt tag"/>
			<span>Enter a <code>Stack name</code>.</span>
			<span>This can be any descriptive name.</span> 
		</div>
		<div class="step-stages__step">
			<img src="http://filldunphy.com/780/439" alt="Relevent alt tag"/>
			<span>Enter your <code>KeyName</code>.</span>
			<span>This corresponds to the key you created in Step 1.</span> 
		</div>
		<div class="step-stages__step">
			<img src="http://filldunphy.com/780/439" alt="Relevent alt tag"/>
			<span>Enter your <code>AccessKeyID</code> and <code>SecretAccessKey</code>.</span> 
			<span>These are your AWS access credentials, which you can access from <a href="https://console.aws.amazon.com/iam/home?nc2=h_m_sc#security_credential" target="_blank">here</a></span>
		</div>
	</div>
	
	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 3</h2>
			<p>Monitor stack completion message.</p>
		</div>
		<div class="step-stages__step first">
			<span> </span> 
		</div>
		<div class="step-stages__step">
			<img src="http://filldunphy.com/780/439" alt="Relevent alt tag"/>
			<span> </span> 
		</div>
		<div class="step-stages__step">
			<span> </span> 
		</div>
	</div>
	
	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 4</h2>
			<p>Complete your installation.</p>
		</div>
		<div class="step-stages__step first">
			<img src="http://filldunphy.com/780/439" alt="Relevent alt tag"/>
			<span>Under the <b>Outputs</b> tab, gather your <code>ClientIP</code>, <code>DockerTLSCertDirectory</code> and <code>SwarmDockerHost</code> info.</span> 
		</div>
		<div class="step-stages__step">
			<img src="http://filldunphy.com/780/439" alt="Relevent alt tag"/>
			<span>Connect to the client IP, and check that <code>docker info</code> lists two hosts in the cluster.</span> 
		</div>
		<div class="step-stages__step">
			<img src="http://filldunphy.com/780/439" alt="Relevent alt tag"/>
			<span>Connect to the client IP, and check that <code>flockerctl</code> lists two nodes and zero datasets in the cluster. </span> 
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

.. raw:: html

   </div>
