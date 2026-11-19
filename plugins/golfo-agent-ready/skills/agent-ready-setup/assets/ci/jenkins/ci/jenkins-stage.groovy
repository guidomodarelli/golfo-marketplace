// Managed by agent-ready-setup (ci.provider: jenkins): an apply rewrites it.
// agent-ready-setup never edits the Jenkinsfile: copy this stage into its stages. For private
// packs, wrap the sh step in withCredentials with a string credential exposed as
// AGENT_READY_GIT_TOKEN, and set AGENT_READY_GIT_URL to the URL prefix of the packs.
stage('Agent Ready') {
  steps {
    sh 'sh .agents/ci/agent-ready-check.sh'
  }
}
