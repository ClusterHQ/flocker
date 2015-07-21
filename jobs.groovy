def project = 'Azulinho/flocker'
def git_url = "https://github.com/${project}.git"
def dashProject = "${project}".replace('/','-')
def branchApi = new URL("https://api.github.com/repos/${project}/branches")
def branches = new groovy.json.JsonSlurper().parse(branchApi.newReader())


def aws_ubuntu_trusty(project, git_url, branch) {
  folder("${project}/${branch}") {
    displayName("${branch}")
  }


 job ("${project}/${branch}/aws_ubuntu_trusty_acceptance") {
      label('aws-ubuntu-trusty')
      wrappers {
          timestamps()
          colorizeOutput()
          timeout {
              absolute(25)
              failBuild()
          }
      }
      scm { git("${git_url}", "${branch}") }
      steps {
          shell("""#!/bin/bash
                  | set -e
                  | export PATH=/usr/local/bin:$PATH
                  | virtualenv -p python2.7 --clear flocker-admin/venv
                  | source flocker-admin/venv/bin/activate
                  | pip install .
                  | pip install Flocker[doc,dev,release]
                    pip install pytest
                  | py.test --junitxml results.xml flocker/acceptance
                  |""".stripMargin()
          )
      }
      publishers {
          archiveArtifacts('results.xml')
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
  }
  job ("${project}/${branch}/aws_ubuntu_trusty_cli") {
      label('aws-ubuntu-trusty')

      scm { git("${git_url}", "${branch}") }
      wrappers {
          timestamps()
          colorizeOutput()
          timeout {
              absolute(25)
              failBuild()
          }
      }

      steps {
          shell("""#!/bin/bash
                  | set -e
                  | export PATH=/usr/local/bin:$PATH
                  | virtualenv -p python2.7 --clear flocker-admin/venv
                  | source flocker-admin/venv/bin/activate
                  | pip install .
                  | pip install Flocker[doc,dev,release]
                    pip install pytest
                  | py.test --junitxml results.xml flocker/cli
                  |""".stripMargin()
          )
      }
      publishers {
          archiveArtifacts('results.xml')
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
  }
  job ("${project}/${branch}/aws_ubuntu_trusty_volume") {
      label('aws-ubuntu-trusty')
      wrappers {
          timestamps()
          colorizeOutput()
          timeout {
              absolute(25)
              failBuild()
          }
      }
      scm { git("${git_url}", "${branch}") }
      steps {
          shell("""#!/bin/bash
                  | set -e
                  | export PATH=/usr/local/bin:$PATH
                  | virtualenv -p python2.7 --clear flocker-admin/venv
                  | source flocker-admin/venv/bin/activate
                  | pip install .
                  | pip install Flocker[doc,dev,release]
                    pip install pytest
                  | py.test --junitxml results.xml flocker/volume
                  |""".stripMargin()
          )
      }
      publishers {
          archiveArtifacts('results.xml')
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
  }
  job ("${project}/${branch}/aws_ubuntu_trusty_common_plus_control") {
      label('aws-ubuntu-trusty')
      wrappers {
          timestamps()
          colorizeOutput()
          timeout {
              absolute(25)
              failBuild()
          }
      }
      scm { git("${git_url}", "${branch}") }
      steps {
          shell("""#!/bin/bash
                  | set -e
                  | export PATH=/usr/local/bin:$PATH
                  | virtualenv -p python2.7 --clear flocker-admin/venv
                  | source flocker-admin/venv/bin/activate
                  | pip install .
                  | pip install Flocker[doc,dev,release]
                    pip install pytest
                  | py.test --junitxml results.xml flocker/control
                  |""".stripMargin()
          )
      }
      publishers {
          archiveArtifacts('results.xml')
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
  }
  job ("${project}/${branch}/aws_ubuntu_trusty_restapi") {
      label('aws-ubuntu-trusty')
      wrappers {
          timestamps()
          colorizeOutput()
          timeout {
              absolute(25)
              failBuild()
          }
      }
      scm { git("${git_url}", "${branch}") }
      steps {
          shell("""#!/bin/bash
                  | set -e
                  | export PATH=/usr/local/bin:$PATH
                  | virtualenv -p python2.7 --clear flocker-admin/venv
                  | source flocker-admin/venv/bin/activate
                  | pip install .
                  | pip install Flocker[doc,dev,release]
                    pip install pytest
                  | py.test --junitxml results.xml flocker/restapi
                  |""".stripMargin()
          )
      }
      publishers {
          archiveArtifacts('results.xml')
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
  }
  job ("${project}/${branch}/aws_ubuntu_trusty_node") {
      label('aws-ubuntu-trusty')
      wrappers {
          timestamps()
          colorizeOutput()
          timeout {
              absolute(25)
              failBuild()
          }
      }
      scm { git("${git_url}", "${branch}") }
      steps {
          shell("""#!/bin/bash
                  | set -e
                  | export PATH=/usr/local/bin:$PATH
                  | virtualenv -p python2.7 --clear flocker-admin/venv
                  | source flocker-admin/venv/bin/activate
                  | pip install .
                  | pip install Flocker[doc,dev,release]
                    pip install pytest
                  | py.test --junitxml results.xml flocker/node
                  |""".stripMargin()
          )
      }
      publishers {
          archiveArtifacts('results.xml')
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
  }
  job ("${project}/${branch}/aws_ubuntu_trusty_provision") {
      label('aws-ubuntu-trusty')
      wrappers {
          timestamps()
          colorizeOutput()
          timeout {
              absolute(25)
              failBuild()
          }
      }
      scm { git("${git_url}", "${branch}") }
      steps {
          shell("""#!/bin/bash
                  | set -e
                  | export PATH=/usr/local/bin:$PATH
                  | virtualenv -p python2.7 --clear flocker-admin/venv
                  | source flocker-admin/venv/bin/activate
                  | pip install .
                  | pip install Flocker[doc,dev,release]
                    pip install pytest
                  | py.test --junitxml results.xml flocker/provision
                  |""".stripMargin()
          )
      }
      publishers {
          archiveArtifacts('results.xml')
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
  }
  job ("${project}/${branch}/aws_ubuntu_trusty_route") {
      label('aws-ubuntu-trusty')
      wrappers {
          timestamps()
          colorizeOutput()
          timeout {
              absolute(25)
              failBuild()
          }
      }
      scm { git("${git_url}", "${branch}") }
      steps {
          shell("""#!/bin/bash
                  | set -e
                  | export PATH=/usr/local/bin:$PATH
                  | virtualenv -p python2.7 --clear flocker-admin/venv
                  | source flocker-admin/venv/bin/activate
                  | pip install .
                  | pip install Flocker[doc,dev,release]
                    pip install pytest
                  | py.test --junitxml results.xml flocker/route
                  |""".stripMargin()
          )
      }
      publishers {
          archiveArtifacts('results.xml')
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

  }
  job ("${project}/${branch}/aws_ubuntu_trusty_test") {
      label('aws-ubuntu-trusty')
      wrappers {
          timestamps()
          colorizeOutput()
          timeout {
              absolute(25)
              failBuild()
          }
      }
      scm { git("${git_url}", "${branch}") }
      steps {
          shell("""#!/bin/bash
                  | set -e
                  | export PATH=/usr/local/bin:$PATH
                  | virtualenv -p python2.7 --clear flocker-admin/venv
                  | source flocker-admin/venv/bin/activate
                  | pip install .
                  | pip install Flocker[doc,dev,release]
                    pip install pytest
                  | py.test --junitxml results.xml flocker/test
                  |""".stripMargin()
          )
      }
      publishers {
          archiveArtifacts('results.xml')
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
  }
  job ("${project}/${branch}/aws_ubuntu_trusty_testtools") {
      label('aws-ubuntu-trusty')
      wrappers {
          timestamps()
          colorizeOutput()
          timeout {
              absolute(25)
              failBuild()
          }
      }
      scm { git("${git_url}", "${branch}") }
      steps {
          shell("""#!/bin/bash
                  | set -e
                  | export PATH=/usr/local/bin:$PATH
                  | virtualenv -p python2.7 --clear flocker-admin/venv
                  | source flocker-admin/venv/bin/activate
                  | pip install .
                  | pip install Flocker[doc,dev,release]
                    pip install pytest
                  | py.test --junitxml results.xml flocker/testtools
                  |""".stripMargin()
          )
      }
      publishers {
          archiveArtifacts('results.xml')
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
  }
}

folder("${dashProject}") {
    displayName("${dashProject}")
}

branches << ['name':'master']
branches.each {

  branchName = "${it.name}"
  dashBranchName = "${branchName}".replace("/","-")


  folder("${dashProject}/${branchName}") {
    displayName("${branchName}")
  }

  aws_ubuntu_trusty("${dashProject}", "${git_url}","${branchName}")

  multiJob("${dashProject}/${branchName}/_main_multijob") {
      steps {
          shell('rm -rf *')
          phase('parallel_tests') {
              continuationCondition('ALWAYS')
              job("${dashProject}/${branchName}/aws_ubuntu_trusty_acceptance" ) { killPhaseCondition('NEVER') }
              job("${dashProject}/${branchName}/aws_ubuntu_trusty_cli") { killPhaseCondition('NEVER') }
              job("${dashProject}/${branchName}/aws_ubuntu_trusty_volume")  { killPhaseCondition("NEVER") }
              job("${dashProject}/${branchName}/aws_ubuntu_trusty_common_plus_control")  { killPhaseCondition("NEVER") }
              job("${dashProject}/${branchName}/aws_ubuntu_trusty_restapi") { killPhaseCondition("NEVER") }
              job("${dashProject}/${branchName}/aws_ubuntu_trusty_node") { killPhaseCondition("NEVER") }
              job("${dashProject}/${branchName}/aws_ubuntu_trusty_provision")  { killPhaseCondition("NEVER") }
              job("${dashProject}/${branchName}/aws_ubuntu_trusty_route")  { killPhaseCondition("NEVER") }
              job("${dashProject}/${branchName}/aws_ubuntu_trusty_test")  { killPhaseCondition("NEVER") }
              job("${dashProject}/${branchName}/aws_ubuntu_trusty_testtools")  { killPhaseCondition("NEVER") }
          }
          copyArtifacts('Azulinho-flocker/master/aws_ubuntu_trusty_acceptance') {
              includePatterns('results.xml')
              targetDirectory('aws_ubuntu_trusty_acceptance')
              fingerprintArtifacts(true)
              buildSelector {
                  workspace()
              }
          }
          copyArtifacts('Azulinho-flocker/master/aws_ubuntu_trusty_cli') {
              includePatterns('results.xml')
              targetDirectory('aws_ubuntu_trusty_cli')
              fingerprintArtifacts(true)
              buildSelector {
                  workspace()
              }
          }
          copyArtifacts('Azulinho-flocker/master/aws_ubuntu_trusty_volume') {
              includePatterns('results.xml')
              targetDirectory('aws_ubuntu_trusty_volume')
              fingerprintArtifacts(true)
              buildSelector {
                  workspace()
              }
          }
          copyArtifacts('Azulinho-flocker/master/aws_ubuntu_trusty_common_plus_control') {
              includePatterns('results.xml')
              targetDirectory('aws_ubuntu_trusty_common_plus_control')
              fingerprintArtifacts(true)
              buildSelector {
                  workspace()
              }
          }
          copyArtifacts('Azulinho-flocker/master/aws_ubuntu_trusty_restapi') {
              includePatterns('results.xml')
              targetDirectory('aws_ubuntu_trusty_restapi')
              fingerprintArtifacts(true)
              buildSelector {
                  workspace()
              }
          }
          copyArtifacts('Azulinho-flocker/master/aws_ubuntu_trusty_node') {
              includePatterns('results.xml')
              targetDirectory('aws_ubuntu_trusty_node')
              fingerprintArtifacts(true)
              buildSelector {
                  workspace()
              }
          }
          copyArtifacts('Azulinho-flocker/master/aws_ubuntu_trusty_provision') {
              includePatterns('results.xml')
              targetDirectory('aws_ubuntu_trusty_provision')
              fingerprintArtifacts(true)
              buildSelector {
                  workspace()
              }
          }
          copyArtifacts('Azulinho-flocker/master/aws_ubuntu_trusty_route') {
              includePatterns('results.xml')
              targetDirectory('aws_ubuntu_trusty_route')
              fingerprintArtifacts(true)
              buildSelector {
                  workspace()
              }
          }
          copyArtifacts('Azulinho-flocker/master/aws_ubuntu_trusty_test') {
              includePatterns('results.xml')
              targetDirectory('aws_ubuntu_trusty_test')
              fingerprintArtifacts(true)
              buildSelector {
                  workspace()
              }
          }
          copyArtifacts('Azulinho-flocker/master/aws_ubuntu_trusty_testtools') {
              includePatterns('results.xml')
              targetDirectory('aws_ubuntu_trusty_testtools')
              fingerprintArtifacts(true)
              buildSelector {
                  workspace()
              }
          }
      }
      publishers {
          archiveJunit('**/results.xml') {
              retainLongStdout(true)
              testDataPublishers {
                  allowClaimingOfFailedTests()
                  publishTestAttachments()
                  publishTestStabilityData()
                  publishFlakyTestsReport()
              }
          }
      }
  }
}
