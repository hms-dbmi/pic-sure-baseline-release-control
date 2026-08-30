# pic-sure-baseline-release-control

`build-spec.json` pins the banner-capable AIO release tuple to exact backend, frontend, migrations, and AIO workflow
commits. Jenkins resolves this release-control checkout to an exact commit before running migrations and records that
commit in `pipeline_git_commit.txt`; a release-control file cannot contain its own Git hash.

The rollout metadata mirrors the shared contract from `pic-sure` commit
`0178bbd2d1753e07dcead77a6d0e8ca37bf76dd8`. Forward rollout applies migrations, recreates PSAMA, verifies Operations
and Gateway, then publishes the frontend. Rollback retains the forward schema and prohibits down-migrations.

For cross-repository integration proof, run
`python3 tests/validate_aio_pin.py /path/to/pic-sure-all-in-one`. The validator requires the executing AIO checkout to
be clean at the pinned commit, proves descent from the integrated AIO base, and recomputes the manifest-bound workflow
digest from that checkout.
