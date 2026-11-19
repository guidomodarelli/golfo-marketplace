# A fake scheduler of the system for the tests of the scheduled learning sweep (156f2). Source it from
# a test with `source "$BATS_TEST_DIRNAME/fake-scheduler.bash"`; it needs $test_root.

# Fake crontab, schtasks and launchctl: each call goes to calls.log, and the crontab and the task of
# schtasks live in files of the test. A file named refuse makes every call fail, as a policy would.
fake_scheduler() {
  scheduler_bin="$test_root/scheduler-bin"
  export FAKE_SCHEDULER_STATE="$test_root/scheduler"
  mkdir -p "$scheduler_bin" "$FAKE_SCHEDULER_STATE"
  cat > "$scheduler_bin/fake-scheduler.py" <<'PY'
import os, sys
state = os.environ["FAKE_SCHEDULER_STATE"]
name, arguments = sys.argv[1], sys.argv[2:]
with open(os.path.join(state, "calls.log"), "a", encoding="utf-8") as log:
    log.write(" ".join([name] + arguments) + "\n")
if os.path.exists(os.path.join(state, "refuse")):
    sys.stderr.write("access denied by a policy of the machine\n")
    sys.exit(1)
if name == "crontab":
    path = os.path.join(state, "crontab.txt")
    if arguments == ["-l"]:
        if not os.path.exists(path):
            sys.stderr.write("no crontab for user\n")
            sys.exit(1)
        sys.stdout.write(open(path, encoding="utf-8").read())
    elif arguments == ["-"]:
        open(path, "w", encoding="utf-8").write(sys.stdin.read())
elif name == "schtasks":
    path = os.path.join(state, "schtasks.txt")
    if arguments[0] == "/Create":
        open(path, "w", encoding="utf-8").write(" ".join(arguments))
    elif arguments[0] == "/Delete":
        os.remove(path)
    elif arguments[0] == "/Query":
        sys.exit(0 if os.path.exists(path) else 1)
PY
  for name in crontab schtasks launchctl; do
    printf '#!/bin/bash\nexec python3 "%s/fake-scheduler.py" %s "$@"\n' "$scheduler_bin" "$name" > "$scheduler_bin/$name"
    chmod +x "$scheduler_bin/$name"
    # Windows Python finds commands by PATHEXT: a .cmd twin of each one.
    printf '@python3 "%%~dp0fake-scheduler.py" %s %%*\r\n' "$name" > "$scheduler_bin/$name.cmd"
  done
  export PATH="$scheduler_bin:$PATH"
  export AGENT_READY_LEARNING_SCHEDULER="${1:-crontab}"
  unset CI AGENT_READY_SETUP_REVIEW_MODE
}
