Areas of potential future development
=====================================

Flocker is an ongoing project whose direction will be guided in large part by the community.  
The list below includes some potential areas for future development.  
It is not all encompassing or indicative of what definitely will be built.
Feedback welcome and encouraged.

- Support for application upgrades.
- Scale-out for stateless containers.
- API to support managing Flocker volumes programmatically.
- Statically configured continuous replication and manual failover.
- No-downtime migrations between containers.
- Automatically configured continuous replication and failover.
- Multi-data center support.
- Automatically balance load across cluster.
- Roll-back a container to a snapshot.

Here are some specific user stories which are under consideration:

"Application upgrades"
----------------------

**User stories:**

* A user has deployed their application using Flocker.
  A new version of one of the components has been pushed to the Docker index and now the user wishes to upgrade.
  They change their Dockerfile and build a new image with ``docker build`` for one of their services.
  They ``docker push`` the new version of their image to the Docker index and then want to upgrade their production deployment.
  This service is running in a single container.
  They run a CLI command and Flocker upgrades their application atomically with minimal failed requests.
  Upgrades are performed frequently so they must be as easy as possible.


"Scale-out for stateless containers"
------------------------------------

**User stories:**

* A user's application is designed with stateless web nodes.
  The web node containers must be deployed multiple times and have incoming web requests split even between the web containers.
  The user can describe how many containers to deploy on each server in their deployment file and Flocker creates the necessary containers.
* A user receives an increase or decrease in traffic to their application.
  They change the number of copies of the container configured in their deployment configuration and push the config.
  They also provision more servers and add them to the configured deployment config.
  Flocker automatically adds or removes containers when pushing the new deployment config.
* A user has deployed an application which consists of a stateless CPU-bound Python application in a container.
  The hardware this has been deployed on has a multicore CPU and the user wishes to take advantage of this.
  Python is incapable of effectively using multiple cores so the user decides to spin up multiple instances of the application in separate containers on the same machine.


"Change management - branching - for lightweight staging environments"
----------------------------------------------------------------------

**User story:**

* A user is a sysadmin (devops engineer) and works with a team of 10 developers and is responsible for providing them with realistic staging environments.
  The company builds a web application which primarily uses Ruby on Rails and PostgreSQL.
  It also uses ElasticSearch for search.
  Developers do work on feature branches which potentially include schema modifications.
* Currently the organisation is constrained by only having a single, manually configured staging environment.
  This means that every developer who wants to show someone else their work has to manually "lock" or "unlock" the staging environment by standing up in the office and asking.
  If someone leaves a staging environment for too long, someone else will have taken it over by the time they get to it.
  Staging servers are used to share in-progress work with internal and external stakeholders (so must be available externally, as well as internally).
* Every Monday morning, the user wants to be able to grab a copy of the production database from their nightly backups, and import it into the staging environment.
  The user uses this database import to populate a staging copy of the ElasticSearch cluster.
  The user then wants to make 10 clones of the entire staging copy of the application
  (ie, cloning each of the ruby, postgresql and elasticsearch components), one for each of the developers on the team.
  This way, each developer gets their own staging environment and this reduces contention over the single staging environment for all users, saving the company money.
* Individual developers want to be able to roll back their staging environments to the "fresh" (weekly import).
  They also want to be able to easily and cheaply change between different application configs,
  so for example they can test the latest version of a branch of their code against the "simulated live" ElasticSearch + PostgreSQL + Ruby configuration.
  Or they can test the impact of using a different release of ElasticSearch, either by running manual or automated tests against the staging environment.
