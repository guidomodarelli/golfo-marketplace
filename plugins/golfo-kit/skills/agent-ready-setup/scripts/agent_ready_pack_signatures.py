"""Whether the revision of a pack source is signed by a key this machine knows (security.checks.signature).

Only SSH signatures count. Git verifies them against an allowed signers file that this module
writes from ``security.signers``, so the known keys live in the layered configuration and the
verdict is the same on every machine, with no keyring or agent. A Git source is signed when its
commit, or a tag of its origin that points at that commit, carries a good signature from a key
that covers the source. A path source lives in this repository and has no revision of its own,
so it is never signed.

Verifying reads the bare mirror of the pack cache (agent_ready_packs.py) and never uses the
network: an apply brings the tags of a source into the mirror when the check is on.
"""

import fnmatch
import os
import re
import tempfile

import agent_ready_packs as packs
import agent_ready_pack_tools as pack_tools

SIGNERS_KEY = "security.signers"
SIGNER_KEY_FIELD = "key"
SIGNER_SOURCE_FIELD = "source"
EVERY_SOURCE = "*"
# The principal and namespace of every line of the allowed signers file. Git signs commits and
# tags in the "git" namespace, and prints the principal of the key that verified a signature.
ALLOWED_SIGNER_PRINCIPAL = "agent-ready-signer"
SIGNATURE_NAMESPACE = "git"
# What ssh-keygen prints for a good signature of a key in the file; a GPG signature never prints it.
GOOD_SIGNATURE_TEXT = f'Good "{SIGNATURE_NAMESPACE}" signature for {ALLOWED_SIGNER_PRINCIPAL} '
TAG_OBJECT_TYPE = "tag"
# A public key as a .pub file writes it; the comment is dropped from the allowed signers file.
SSH_PUBLIC_KEY = re.compile(
    r"(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521|"
    r"sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com) ([A-Za-z0-9+/]+={0,3})( [^\r\n]*)?")


def is_ssh_public_key(text):
    return bool(SSH_PUBLIC_KEY.fullmatch(text))


def keys_for_source(source_name, signers):
    """The public keys (type and base64, without comment) that may sign one source."""
    keys = []
    for signer in signers:
        match = SSH_PUBLIC_KEY.fullmatch(signer.get(SIGNER_KEY_FIELD, ""))
        if match and fnmatch.fnmatchcase(source_name, signer.get(SIGNER_SOURCE_FIELD, EVERY_SOURCE)):
            keys.append(f"{match.group(1)} {match.group(2)}")
    return keys


def allowed_signers_text(keys):
    return "".join(f'{ALLOWED_SIGNER_PRINCIPAL} namespaces="{SIGNATURE_NAMESPACE}" {key}\n' for key in keys)


def has_good_signature(source_name, repository, subcommand, revision, allowed_signers_file):
    """True when ``git verify-commit`` or ``verify-tag`` finds a good SSH signature of a listed key."""
    completed = packs.run_git(source_name, [
        "-c", f"gpg.ssh.allowedSignersFile={allowed_signers_file}",
        "--git-dir", repository, subcommand, "--raw", revision,
    ])
    output = (completed.stdout + completed.stderr).decode("utf-8", "replace")
    return completed.returncode == 0 and GOOD_SIGNATURE_TEXT in output


def tags_pointing_at(source_name, repository, commit):
    """The annotated tags of the mirror whose target is the commit."""
    completed = packs.run_git(source_name, [
        "--git-dir", repository, "for-each-ref", "--points-at", commit,
        "--format=%(objecttype) %(refname)", packs.MIRROR_TAG_NAMESPACE,
    ])
    if completed.returncode != 0:
        return []
    tags = []
    for line in completed.stdout.decode("utf-8", "replace").splitlines():
        object_type, _, reference = line.partition(" ")
        if object_type == TAG_OBJECT_TYPE:
            tags.append(reference)
    return tags


def verify_source(source_name, source, signers):
    """(verified, reason): whether the revision a source resolved to is signed by one of its keys."""
    if source.get("type") == packs.SOURCE_TYPE_PATH:
        return False, (f"the source {source_name} lives in this repository and has no revision of its own to verify; "
                       f"turn {pack_tools.CHECK_SIGNATURE_KEY} off in the project to run its tools")
    keys = keys_for_source(source_name, signers)
    if not keys:
        return False, (f"no key of {SIGNERS_KEY} covers the source {source_name}; add the key its maintainers "
                       f"sign with: agent-ready trust add {source_name} --signer <public key file>")
    commit = source.get("resolvedCommit")
    repository = packs.mirror_repository(source.get("origin", ""))
    if not commit or not packs.mirror_has_commit(source_name, repository, commit):
        return False, f"the revision of {source_name} is not in the cache of this machine; an apply downloads it"
    descriptor, allowed_signers_file = tempfile.mkstemp(prefix="agent-ready-signers.", suffix=".txt")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as signers_file:
            signers_file.write(allowed_signers_text(keys))
        # Git reads the path from its configuration, where a forward slash works on every system.
        allowed_signers_file = allowed_signers_file.replace(os.sep, "/")
        if has_good_signature(source_name, repository, "verify-commit", commit, allowed_signers_file):
            return True, None
        for tag in tags_pointing_at(source_name, repository, commit):
            if has_good_signature(source_name, repository, "verify-tag", tag, allowed_signers_file):
                return True, None
    finally:
        os.unlink(allowed_signers_file)
    return False, (f"neither commit {commit[:12]} of {source_name} nor a tag of its origin that points at it has a "
                   f"good SSH signature from a key of {SIGNERS_KEY} for this source")


def verifier(configuration):
    """A function (source name, source) -> (verified, reason), once per source, for pack_tools.report."""
    signers = configuration.value(SIGNERS_KEY) or []
    verdicts = {}

    def verify(source_name, source):
        if source_name not in verdicts:
            verdicts[source_name] = verify_source(source_name, source, signers)
        return verdicts[source_name]

    return verify
