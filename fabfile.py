from fabric.api import task, run, local

@task
def brew():
    run("brew update")
    run("brew install https://raw.githubusercontent.com/ClusterHQ/homebrew-tap/release/flocker-0.3.3dev6/flocker-0.3.3dev6.rb")
    run("brew test flocker-0.3.3dev6")

