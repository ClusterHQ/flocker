// vim: ai ts=2 sts=2 et sw=2 ft=groovy fdm=indent et foldlevel=0
/* jobs.groovy

  This Groovy file contains the jenkins job DSL plugin code to build all the
  required views, folders, and jobs for a particular project in the Jenkins
  interface.

  The easiest way to debug or experiment with changes to this is:
    * check them in to a branch
    * trigger a build of that branch on the setup_ClusterHQ-flocker job
    * ssh into the master (same hostname as the web ui)
    * compare the master configuration xml with the branch configuration xml:

        BASE=/var/lib/jenkins/jobs/ClusterHQ-flocker/jobs/
        A=master
        B=copy-artifacts-for-all-jobs-FLOC-3799
        for config in $(find ${BASE}/${A} -name config.xml | cut -d '/' -f 10- | sort); do
            if [ -e ${BASE}/${A}/${config} ] && [ -e ${BASE}/${B}/${config} ]; then
                diff -u ${BASE}/${A}/${config} <(sed -e "s,${B},${A}," ${BASE}/${B}/${config})
            fi
        done | less

      Certain changes will always be present.  For example, triggers for the
      cron-style jobs are only created for the master branch.

  The full Jenkins job DSL reference can be found on the URL below:
  https://github.com/jenkinsci/job-dsl-plugin/wiki/Job-reference

  The file is consumed by the Jenkins job setup_ClusterHQ_Flocker. This file
  is read by a build step of type 'Process Job DSL' which produces all the
  jenkins objects.

  A typical jenkins job contains the following sections, this is just an
  example of possible actions within a particular section:

   * Parameters:
        - parameters can be added to a job, these are used to pass environment
          variables to the build steps or any other step in the job.

   * Source Control defintions:
        - repository URL
        - what SCM tool git/svn/mercurial
        - operations to do prior/after a git update/close

    * Triggers:
        - When to execute the build ?
        - On a crontab style
        - by pooling the repository for changes
        - triggered by GitHub or others

   * Wrappers which 'decorate' the build steps of the job
        - adds stuff like timestamps to the log output
        - sets a timeout and aborts the build when exceeded

    * Build steps
        - Commonly shell based steps, as in the cli to execute

    * Post-Build actions also called Publishers:
        - Archiving produced files so that they are made available in other
          jobs
        - Running coverage or test reports
        - Triggering other jobs


    The structure of this file is as follows:

    A set of functions which implement the different sections of the job:

        - folder (creates a folder view in Jenkins to store the jobs)
        - wrappers
        - triggers
        - scm (sets the Source Control section)
        - publishers (set the post-build steps)
        - steps (consumes the contentes of the build.yaml build steps, and
            expands those as shell cli text'

    A full set of job blocks follows, these iterate over the build.yaml file for
    each job definition of a particular 'job_type' and create all the jobs
    related to that 'job_type':

        - run_trial
        - run_trial_for_storage_driver
        - run_sphinx
        - run_acceptance
        - run_client
        - omnibus

    Then we have the multijob block, which collects all the defined jobs based
    on 'job_type' and adds them to a 'multijob phase' that executes all the
    jobs in parallel.
    When a new 'job_type' is added to the configuration above, that job_type
    configuration should be added into the multijob block so that it gets run
    as part of the parallel execution phase.
    This multijob after executing the different jobs, collects all the produced
    artifacts (test reports, coverage reports) from the different jobs.
    So that a aggregated view of all the results is made available within the
    multijob details page for a completed job.

    The last section in this file defines cron style type jobs which are not
    executed as part of the main multijob.  These follow a similar structure to
    the common 'job_type' definitions above, except they include a trigger
    section specifying an daily schedulle.
*/

// Load the build.yaml, convert to JSON:
def processbuilder = new ProcessBuilder('python', '-c', 'import json, yaml, sys; sys.stdout.write(json.dumps(yaml.safe_load(sys.stdin.read()))); sys.stdout.flush()')
def process = processbuilder.redirectInput(ProcessBuilder.Redirect.PIPE).redirectOutput(
    ProcessBuilder.Redirect.PIPE).start()
// Aren't Java APIs awesome? Process.getOutputStream() is stdin.
def stdin = new java.io.PrintWriter(process.getOutputStream())
stdin.write(readFileFromWorkspace('build.yaml'))
stdin.flush()
stdin.close()
process.getOutputStream().close()
def jsonSlurper = new groovy.json.JsonSlurper()
// Java is the best! This is how you read file into a string:
GLOBAL_CONFIG = jsonSlurper.parseText(
    new Scanner(process.getInputStream(),"UTF-8").useDelimiter("\\A").next())

// --------------------------------------------------------------------------
// UTILITIES DEFINED BELOW
// --------------------------------------------------------------------------

def updateGitHubStatus(status, description, branch, dashProject,
                       dashBranchName, jobName) {
    return """#!/bin/bash
# Jenkins jobs are usually run using 'set -x' however we use 'set +x' here
# to avoid leaking credentials into the build logs.
set +x
# Set the GitHub credentials
""" + new File('/etc/slave_config/github_status.sh').text + """
# Send a request to Github to update the commit with the build status
REMOTE_GIT_COMMIT=`git rev-list --max-count=1 upstream/${branch}`
BUILD_URL="\$JENKINS_URL/job/${dashProject}/job/${dashBranchName}/job/${jobName}/"
PAYLOAD="{\\"state\\": \\"${status}\\", \\"target_url\\": \\"\$BUILD_URL\\", \\"description\\": \\"${description}\\", \\"context\\": \\"jenkins-${jobName}\\" }"
curl \\
  -H "Content-Type: application/json" \\
  -H "Authorization: token \$GITHUB_STATUS_API_TOKEN" \\
  -X POST \\
  --data "\$PAYLOAD" \\
  https://api.github.com/repos/${GLOBAL_CONFIG.project}/statuses/\$REMOTE_GIT_COMMIT
echo "Updating commit \$REMOTE_GIT_COMMIT with ${status} status."
"""
}

def folder_name(dashProject, dashBranchName) {
    /*
        Return the folder name (url path) given the constituent parts

        :param unicode dashProject: the name of the top-level project,
            escaped for use in a path.
        :param unicode dashBranchName: the name of the branch,
            escaped for use in a path.
        :return unicode: the folder name for the branch
    */
    return "${dashProject}/${dashBranchName}"
}


def full_job_name(dashProject, dashBranchName, job_name) {
    /*
        Return the full job name (url path) given the constituent parts

        :param unicode dashProject: the name of the top-level project,
            escaped for use in a path.
        :param unicode dashBranchName: the name of the branch,
            escaped for use in a path.
        :param unicode job_name: the sub-task name,
            escaped for use in a path.
        :return unicode: the full name
    */
    return folder_name(dashProject, dashBranchName) + "/${job_name}"
}


def escape_name(name) {
    /*
        Escape a name to make it suitable for use in a path.

        :param unicode name: the name to escape.
        :return unicode: the escaped name.
    */
    return name.replace('/', '-')
}


def make_view(path, description, make_jobs) {
    /*
        Make a view tab.

        :param unicode path: the url segment of the view, including project etc.
            e.g. "flocker/master/acceptance"
        :param unicode description: the description of the view.
        :param callable make_jobs: a callable that will return the
                the list of jobs to include when passed the view context,
                something like:
                    { context ->
                        context.jobs {
                            name("foo")
                            regex("bar.*")
                        }
                    }
    */

    listView(path) {
        delegate.description(description)
        filterBuildQueue()
        filterExecutors()
        make_jobs(delegate)
        columns {
            status()
            weather()
            name()
            lastSuccess()
            lastFailure()
            lastDuration()
            buildButton()
        }
    }
}


/* adds a list of common wrappers to the build jobs.

   param v:  dictionary containing the values from the job
   param list directories_to_delete: directory to clean up
*/
def build_wrappers(v, directories_to_delete) {
    directories_to_delete = directories_to_delete.join(" ")
    return {
        //    adds timestamps to the job log output
        timestamps()
        // colorizeOuptut allows for ascii coloured output in the logs of a job
        colorizeOutput()
        /* define the max duration a running job should take, this prevents stuck
           jobs for reserving jenkins slaves and preventing other jobs from running.
           These timeouts will have to be adjusted as we work on improving the
           execution time of the tests so that we can enforce a SLA of a maximum of
           'n' minutes.
           An improvement here (TODO) would be to receibe the timeout as a parameter
           so that we can have different timeouts for different job types. */
        timeout {
            absolute(v.timeout)
            failBuild()
        }
        /* Jobs that are executed with sudo can leave files behind that prevents
           Jenkins from cleaning the git repository before a git merge.
           The git cleanup process is run as the jenkins execution user which lacks
           the priviledges to remove the root owned files created by the sudo tests.
           To fix this issue, we use a preSCM plugin which allows us to execute a
           step before cloning/checking the git reposity.
           if the build.yaml contains a 'clean_repo' flag, then we will clean up
           old root files from the repo. */
        if (v.clean_repo) {
            preScmSteps {
                steps {
                    shell("sudo rm -rf ${directories_to_delete}")
                }
            }
        }
    }
}


/* adds a list of triggers to the build job

   param  _type: type of job
   param _value: the cron string

*/
def build_triggers(_type, _value, _branch ) {
    return {
        /* the job_type 'cron' is used by the docker_build jobs running every 24h
           but we only configure the scheduler if the jobs is for the master branch.
           If we were to schedule the job on every branch we would have multiple jobs
           running at the same time. */
        if (_type == "cron" && _branch == "master") {
            //  the cron  string below is a common crontab style string
            cron(_value)
        }
        /*  the job_type 'githubPush' is used by the multijob, we use it to
            configure that job so that builds on master are triggered automatically
            this block enables 'Build when a change is pushed to GitHub' */
        if (_type == "githubPush" && _branch == "master") {
            githubPush()
        }
    }
}


/* configures a remote git repository, and merges 'branch' before build

    param: git_url - example: https://github.com/clusterhq/flocker
    param: branch - remote branch name to configure
*/
def build_scm(git_url, branchName, isReleaseBuild) {
    return {
        git {
            // The default clone timeout is 10 minutes.  Lower this a bit
            // because checking out Flocker takes less than a minute (Jan 2016)
            // but completely stalls from time to time.  We want to hit the
            // timeout for the stalled case as quickly as we can so a retry
            // (which will hopefully succeed) can be attempted.  See the
            // checkoutRetryCount setting elsewhere.
            cloneTimeout(2)

            remote {
                // our remote will be called 'upstream'
                name("upstream")
                // the project name from the build yaml 'ClusterHQ/Flocker'
                github(GLOBAL_CONFIG.project)
            }
            //  configure the git user merging the branches.
            // the job dsl scm/git doesn't contain a method to specify the local git user
            // or email address, so we use a configure/node block to insert the XML block
            // into the jenkins job config
            configure { node ->
                node / gitConfigName('Jenkins')
                node / gitConfigEmail('jenkins@clusterhq.com')
            }
            // the branch to be built
            branch(branchName)
            // clean the repository before merging (git reset --hard)
            clean(true)
            createTag(false)
            if (!isReleaseBuild) {
                // merge our branch with the master branch
                mergeOptions {
                    remote('upstream')
                    branch('master')
                    // there are a few merge strategies available, recursive is the default one
                    strategy('recursive')
                }
            }
        }
    }
}


/* adds a publishers block to the jenkins job configuration, containing:
   an action for archiving artifacts
   an action for archiving junit results
   an action for publishing coverate reports

   param v: dictionary containing the job keys
*/
def build_publishers(v, branchName, dashProject, dashBranchName, job_name) {
    return {
        if (v.archive_artifacts) {
            for (artifact in v.archive_artifacts) {
                // v.archive_artifacts typically contain:
                // 'results.xml', 'coverage.xml', '_trial_temp/trial.log'
                archiveArtifacts(artifact)
            }
        }

        if (v.publish_test_results) {
            // archives the junit results and publish the test results
            archiveJunit('results.xml') {
                retainLongStdout(true)
                testDataPublishers {
                    allowClaimingOfFailedTests()
                    publishTestAttachments()
                    publishTestStabilityData()
                    publishFlakyTestsReport()
                }
            }
        }
        if (v.coverage_report) {
            // publishes a coverage report, using junit and the cobertura plugin
            cobertura('coverage.xml') {
                // don't publish coverage reports if the build is not stable.
                onlyStable(false)
                failUnhealthy(true)
                failUnstable(true)
                // fail the build if we were expecating a coverage report from a build and
                // that report is not available
                failNoReports(true)
            }
        }
        if (job_name) {
            /* Update the commit status on GitHub with the build result We use the
               flexible-publish plugin combined with the the any-buildstep plugin to
               allow us to run shell commands as part of a post-build step.  We also
               use the run-condition plugin to inspect the status of the build
               https://wiki.jenkins-ci.org/display/JENKINS/Flexible+Publish+Plugin
               https://wiki.jenkins-ci.org/display/JENKINS/Any+Build+Step+Plugin
               https://wiki.jenkins-ci.org/display/JENKINS/Run+Condition+Plugin */
            flexiblePublish {
                condition {
                    status('SUCCESS', 'SUCCESS')
                }
                step {
                    shell(updateGitHubStatus(
                              'success', 'Build succeeded',
                              branchName, dashProject, dashBranchName, job_name))
                }
            }
            flexiblePublish {
                condition {
                    status('FAILURE', 'FAILURE')
                }
                step {
                    shell(updateGitHubStatus(
                          'failure', 'Build failed',
                          branchName, dashProject, dashBranchName, job_name))
                }
            }
        }
    }
}


/*  builds a list of job steps based on the type of the job:
    ( 'shell', others )
    currently only shell has been implemented.

    params job: dictionary the job steps (``with_steps``) */
def build_steps(job) {
    return {
        for (_step in job.with_steps) {
            if (_step.type == 'shell') {
                shell(_step.cli.join("\n") + "\n")
            }
        }
    }
}


def list_jobs(dashProject, dashBranchName) {
    /*
        List all the jobs, accounting for modules to run etc.

        A common pattern is to loop over the jobs and
        extract particular information and act on it.

        The way the information is stored in build.yaml,
        and the varied rules for processing it mean that
        it's not a simple loop.

        This function performs the transformations and
        provides a simple list of all jobs with their
        basic information. It can be filtered and processed
        as needed.

        :param unicode dashProject: the name of the project, escaped
            for use in paths.
        :param unicode dashBranchName: the name of the branch, escaped
            for use in paths.
        :return List: a list of maps of job info, with keys:
            unicode type: the type of the job
            unicode name: the short name of the job
            unicode full_name: the full path of the job, including
                               project and branch
            unicode module: the test module to run, or null if this
                            doesn't apply to this job type
            Map values: the rest of the key/value pairs from the
                        build.yaml job definition
    */
    results = []
    GLOBAL_CONFIG.job_type.each { job_type, job_type_values ->
        job_type_values.each { job_name, job_values ->
            // Cron jobs are prefixed with an underscore
            if (job_type == 'cronly_jobs') {
                job_name = "_${job_name}"
            }
            if (job_values.with_modules) {
                for (module in job_values.with_modules) {
                    _job_name = job_name + '_' + escape_name(module)
                    full_name = full_job_name(
                        dashProject, dashBranchName, _job_name)
                    results.add([type: job_type, name: _job_name,
                                 module: module, values: job_values,
                                 full_name: full_name])
                }
            } else {
                full_name = full_job_name(
                    dashProject, dashBranchName, job_name)
                results.add([type: job_type, name: job_name, module: null,
                             values: job_values, full_name: full_name])
            }
        }
    }
    return results
}


// the project name from the build yaml 'ClusterHQ/Flocker'
project = GLOBAL_CONFIG.project
// the github https url for the project
git_url = GLOBAL_CONFIG.git_url
branches = []
/* grab the GitHub token from the jenkins homedir.
   this is the github api token for jenkins. We need to authenticate as github
   limits the number of API calls that can be done withouth authenticating   */
String token = new File('/var/lib/jenkins/.github_token').text.trim()

// Lets's call it ClusterHQ-Flocker instead of ClusterHQ/Flocker
dashProject = escape_name(project)

// Create a basefolder for our project, it should look like:
//   '<github username>-<git repository>'
println("Creating folder ${dashProject}...")
folder(dashProject) { displayName(dashProject) }

make_view(
    "${dashProject}/master", "Builds of master",
    { context ->
        context.jobs {
            name("master")
        }
    }
)

make_view(
    "${dashProject}/releases", "Release build",
    { context ->
        context.jobs {
            regex("release-.*")
        }
    }
)

// branches contains the passed parameter RECONFIGURE_BRANCH from jenkins
branches.add("${RECONFIGURE_BRANCH}")

// create tabs inside the branch folder
def build_tabs(dashBranchName) {
    for (entry in GLOBAL_CONFIG.views) {
        name = "${dashProject}/${dashBranchName}/${entry.key}"
        println("creating tab ${name}...")
        make_view(
            name, entry.value.description,
            { context ->
                context.jobs {
                    regex(entry.value.regex)
                }
            }
        )
    }
}


def define_job(dashProject, dashBranchName, branchName, job_type, job_name,
               full_name, job_values, module, isReleaseBuild) {

    if (job_type in ['run_trial', 'run_trial_for_storage_driver', 'run_acceptance']) {
        assert module != null
        job(full_name) {
            parameters {
                // we pass the 'MODULE' parameter as the flocker module to test with trial
                textParam("MODULE", module, "Module to test" )
                textParam("TRIGGERED_BRANCH", branchName,
                          "Branch that triggered this job" )
            }

            // Allow some attempts to checkout the source to fail, since
            // doing so depends on a third-party, network-accessible resource.
            //
            // Unfortunately, this *may* not actually work due to bugs in
            // Jenkins or the Git SCM plugin:
            //
            //     https://issues.jenkins-ci.org/browse/JENKINS-14575
            //
            checkoutRetryCount(5)

            // limit execution to jenkins slaves with a particular label
            label(job_values.on_nodes_with_labels)
            // _trial_temp and .hypothesis are for run_trial*
            // and repo is for run_acceptance, but they are removed
            // with rm -rf so we can get away with being overly broad
            directories_to_delete = ['${WORKSPACE}/_trial_temp',
                                     '${WORKSPACE}/.hypothesis',
                                     '${WORKSPACE}/repo']
            wrappers build_wrappers(job_values, directories_to_delete)
            scm build_scm(git_url, branchName, isReleaseBuild)
            steps build_steps(job_values)
            publishers build_publishers(job_values, branchName, dashProject, dashBranchName, job_name)
        }
    } else if (job_type == 'run_sphinx') {
        assert module == null
        job(full_name) {
            parameters {
                textParam("TRIGGERED_BRANCH", branchName,
                          "Branch that triggered this job" )
            }
            // See above.
            checkoutRetryCount(5)

            // limit execution to jenkins slaves with a particular label
            label(job_values.on_nodes_with_labels)
            wrappers build_wrappers(job_values, [])
            scm build_scm(git_url, branchName, isReleaseBuild)
            steps build_steps(job_values)
            publishers build_publishers(job_values, branchName, dashProject, dashBranchName, job_name)
        }
    } else if (job_type == 'run_client') {
        assert module == null
        job(full_name) {
            parameters {
                // the run_acceptance job produces a rpm/deb package which is
                // made available to the node/docker instance running in the at
                // a particular address on the jenkins slave (ex:
                // http://jenkins_slave/$RECONFIGURE_BRANCH/repo)
                textParam("TRIGGERED_BRANCH", branchName,
                          "Branch that triggered this job" )
            }
            // See above.
            checkoutRetryCount(5)

            // limit execution to jenkins slaves with a particular label
            label(job_values.on_nodes_with_labels)

            directories_to_delete = ['${WORKSPACE}/repo']
            wrappers build_wrappers(job_values, directories_to_delete)
            scm build_scm(git_url, branchName, isReleaseBuild)
            steps build_steps(job_values)
            publishers build_publishers(job_values, branchName, dashProject, dashBranchName, job_name)
        }
    } else if (job_type in ['omnibus', 'run_lint']) {
        assert module == null
        job(full_name) {
            // See above.
            checkoutRetryCount(5)
            // limit execution to jenkins slaves with a particular label
            label(job_values.on_nodes_with_labels)
            wrappers build_wrappers(job_values, [])
            scm build_scm(git_url, branchName, isReleaseBuild)
            steps build_steps(job_values)
            publishers build_publishers(job_values, branchName, dashProject, dashBranchName, job_name)
        }
    } else {
        throw new Exception("Don't know how to handle ${job_type} jobs")
    }

}


def trigger_sub_job(context, name) {
    /*
        Trigger a sub-job in a multijob without killing the parent on failure

        :param context: the multijob context to add the job to
        :param name: the name of the sub-job to trigger
    */
    context.phaseJob(name) {
        /* make sure we don't kill the parent multijob when we
           fail */
        killPhaseCondition("NEVER")
    }
}


def copy_artifacts_from(context, full_job_name, short_job_name, archive_artifacts) {
    /*
        Copy artifacts from another job to this one.

        :param context: the context of the job that receives the copied
            artifacts.
        :param unicode full_job_name: the full path of the job.
        :param unicode short_job_name: the name of the job without the full path.
        :param list[str] archive_artifacts: the artifacts to archive as a
             string glob patter.
    */
    for (artifact in archive_artifacts) {
        context.copyArtifacts(full_job_name) {
            optional(true)
            includePatterns(artifact)
            /* and place them under short_job_name/artifact on
               the multijob workspace, so that we don't
               overwrite them.  */
            targetDirectory(short_job_name)
            fingerprintArtifacts(true)
            buildSelector {
                workspace()
            }
        }
    }
}

PULL_REQUEST_JOB_TYPES = ['run_trial', 'run_trial_for_storage_driver',
                          'run_acceptance', 'run_sphinx', 'omnibus',
                          'run_lint', 'run_client']

def build_multijob(dashProject, dashBranchName, branchName, isReleaseBuild) {
    // -------------------------------------------------------------------------
    // MULTIJOB CONFIGURATION BELOW
    // --------------------------------------------------------------------------

    // the multijob is responsible for running all configured jobs in parallel
    multiJob(full_job_name(dashProject, dashBranchName, "__main_multijob")) {
        /* we don't execute any code from the mulitjob run, but we need to fetch
           the git repository so that we can track when changes are pushed upstream.
           We add a SCM block pointing to our flocker code base.
        */
        scm build_scm(git_url, branchName, isReleaseBuild)
        /* By adding a trigger of type 'github' we enable automatic builds when
           changes are pushed to the repository.
           This however only happens for the master branch, no other branches are
           automatically built when new commits are pushed to those branches.
        */
        triggers build_triggers('githubPush', 'none', branchName)
        wrappers {
            timestamps()
            colorizeOutput()
            /* lock down the multijob to 60 minutes so that 'stuck' jobs won't
               block future runs                                                  */
            timeout {
                absolute(60)
            }
        }

        /* the multijob runs on the jenkins-master only                             */
        label("master")
        steps {
            /* Set the commit status on GitHub to pending for each subtask we will run */
            list_jobs(dashProject, dashBranchName).findAll { it.type in PULL_REQUEST_JOB_TYPES }.each {
                shell(updateGitHubStatus('pending', 'Build started', branchName, dashProject, dashBranchName, it.name))
            }
            /* make sure we are starting with a clean workspace  */
            shell('rm -rf *')
            /* build 'parallel_tests' phase that will run all our jobs in parallel  */
            phase('parallel_tests') {
                /* and don't fail when a child job fails, as we want to collect the artifacts
                   from the jobs, especially those that have failed   */
                continuationCondition('ALWAYS')
                /*
                  in order for the different job_types to be executed as part of the multijob
                  a block entry for that particular job_type needs to be added to the
                  multijob configuration below.
                */
                context = delegate
                list_jobs(dashProject, dashBranchName).findAll { it.type in PULL_REQUEST_JOB_TYPES }.each {
                    trigger_sub_job(context, it.full_name)
                }
            } /* ends parallel phase */

            /* we've added the jobs to the multijob, we now need to fetch and
               archive all the artifacts produced by the different jobs
               Skip the cron jobs as they don't run from this multijob,
               so the copied artifacts could be from a build of a previous
               revision, which may confuse things. */
            list_jobs(dashProject, dashBranchName).findAll { it.type != 'cronly_jobs' }.each {
                if (it.values.archive_artifacts) {
                    copy_artifacts_from(
                        delegate, it.full_name,
                        it.name, it.values.archive_artifacts
                    )
                }
            }
        }

        /* do an aggregation of all the test results */
        publishers {
            archiveJunit('**/results.xml') {
                retainLongStdout(true)
                testDataPublishers {
                    /* allows a jenkins user to 'claim' a failed test, indicating
                       that user is 'looking into it' */
                    allowClaimingOfFailedTests()
                    publishTestAttachments()
                    /* publish a percentage of failures for a particular test */
                    publishTestStabilityData()
                    /* publish a report of tests that fail every so often */
                    publishFlakyTestsReport()
                }
            }
            /* do an aggregation of all the coverage results */
            cobertura('**/coverage.xml') {
                /* only produce coverage reports for stable builds */
                onlyStable(false)
                failUnhealthy(true)
                failUnstable(true)
                failNoReports(false)
            }
        }

    }
}


def generate_jobs_for_branch(dashProject, dashBranchName, branchName, isReleaseBuild) {
    /*
        Generate all the jobs for the specific branch.

        :param unicode dashProject: the project name escaped with dashes
        :param unicode dashBranchName: the branch name escaped with dashes
        :param unicode branchName: the name of the branch for display - spaces
             etc. allowed
        :param bool isReleaseBuild: whether to generate a release build that
             doesn't merge to master before performing operations.
    */

    // create a folder for every branch: /git-username/git-repo/branch
    folder(folder_name(dashProject, dashBranchName)) {
        displayName(branchName)
    }

    // create tabs
    build_tabs(dashBranchName)

    // create individual jobs
    list_jobs(dashProject, dashBranchName).findAll {
        it.type != 'cronly_jobs'
    }.each {
        define_job(
            dashProject, dashBranchName, branchName, it.type, it.name,
            it.full_name, it.values, it.module, isReleaseBuild
        )
    }

    // create multijob that aggregates the individual jobs
    build_multijob(dashProject, dashBranchName, branchName, isReleaseBuild)
}


/* --------------------
   MAIN ACTION:
   --------------------
*/
// Iterate over every branch, and create folders, jobs
branches.each { branchName ->
    println("iterating over branch... ${branchName}")
    dashBranchName = escape_name(branchName)
    // our convention for release branches is release/flocker-<version>
    isReleaseBuild = branchName.startsWith("release/*")

    generate_jobs_for_branch(dashProject, dashBranchName, branchName, false)

    if (isReleaseBuild) {
        generate_jobs_for_branch(
            dashProject, "release-" + dashBranchName, "Release " + branchName,
            true
        )
    }


    /* ------------------------------------------------------------------------- */
    /* CRON JOBS BELOW                                                           */
    /* --------------------------------------------------------------------------*/

    /* Configure cronly jobs, these are not part of the main branches loop       */
    /* As we only run them from the master branch, they get executed a few       */
    /* times a day based on a cron type schedule.                                */

    cronly_jobs = list_jobs(dashProject, dashBranchName).findAll {
        it.type == 'cronly_jobs'
    }.each {
        values = it.values
        job(it.full_name) {
            parameters {
                textParam("TRIGGERED_BRANCH", branchName,
                          "Branch that triggered this job" )
            }
            // See above.
            checkoutRetryCount(5)
            label(values.on_nodes_with_labels)
            wrappers build_wrappers(values, [])
            triggers build_triggers('cron', values.at, branchName)
            scm build_scm("${git_url}", "${branchName}", false)
            steps build_steps(values)
            publishers build_publishers(values, null, null, null, null)
        }
    }
}
