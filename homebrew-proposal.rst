The initial design by Jon and me is the following prose:

Linking Travis-CI or Buildbot to the homebrew-tap repository would save:
   #. The release engineer from logging into the Mac Mini and testing the recipe.
   #. A reviewer of the PR to homebrew-tap’s master logging into the Mac mini and testing the recipe.

It would not provide the other benefits of Continuous Integration.
That is, CI should be able to tell you before you merge a commit into master whether that commit will break something.
This is not possible with the current Homebrew set up even if Homebrew builds were run from Flocker pushes, because the Homebrew recipe downloads the latest released .tar.gz from GCS and installs it.
Unless there is a release which uploads the .tar.gz file to GCS, the Homebrew recipe will not change.

Testing often with CI would test that the links to the dependencies have not gone down, and that a change to Homebrew itself does not interfere with our recipe.

This led to the conclusion that this issue should be covered by an admin script (perhaps put in the current ``admin/make-homebrew-recipe``).
This script would:
   * Log into the Mac mini.
   * Start an OS X VM with a script very similar to https://github.com/ClusterHQ/internal-tools/blob/master/bin/start_homebrew_machine.
   * Instead of just SSHing into the VM and leaving the user to test the recipe, the script would use fabric (or similar) to run the brew test commands on the VM.
   * It would merge the recipe into the homebrew-tap master if the test passes.
   * It would alert the release engineer to stop the release process if the test does not pass.

I don’t think that just because the tap is a git repository that it should be special in that it needs a human to push to master. 
The tap is no different to our other repositories which scripts upload artefacts to e.g. GCS.

This would fit into the broader vision where the release process  is run by Buildbot (see https://zulip.com/#narrow/stream/engineering/subject/release.20process.20improvements.20after.200.2E3.2E3dev7 for discussion). 
If we could do very regular releases because of that, we would achieve something closer to CI with Homebrew.
