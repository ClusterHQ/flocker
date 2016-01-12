.. _cloudformation:

.. raw:: html

    <style>
        .toctree-wrapper { display:none; }
    </style>

=========================================================
Installing Flocker with Swarm on AWS using CloudFormation
=========================================================

The steps in this guide enable you to quickly deploy a Flocker/Swarm cluster, which uses four AWS EC2 instances.

.. figure:: ../images/cloudformation.png
    :scale: 95%
    :align: center
    :alt: A diagram illustrating a cluster of four AWS EC2 instances running Flocker with Docker Swarm.

    This diagram illustrates the cluster of four EC2 instances created by completing the CloudFormation steps below, and what each instance node in the cluster is running.

.. source material for this image: https://drive.google.com/open?id=0ByymF9bLBknGeXlPX1pTdXVZOGM

.. raw:: html
	
	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 1</h2>
			<p><a href="https://console.aws.amazon.com/ec2/v2/home?region=us-east-1">Create and save an AWS EC2 Key Pair</a> in the target region for your Flocker cluster:</p>
		</div>
		<div class="step-stages__step first">
			<span> </span> 
		</div>
		<div class="step-stages__step">
			<img src="http://filldunphy.com/780/439" alt="Relevent alt tag"/>
			<span>The AWS Key Pair uses public-key cryptography to provide secure login to your AWS cluster.</span>
		</div>
		<div class="step-stages__step">
			<span></span>
		</div>
	</div>
	
	<div class="step-stages step-stages--3up">
		<div class="step-stages__excerpt">
			<h2 class="step-stages__heading">Step 2</h2>
			<p>Create a 2 node Flocker cluster:</p>
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
			<span>Under the <b>Outputs</b> tab, gather your <code>ClientIP</code> and <code>SwarmDockerHost</code> info.</span> 
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
