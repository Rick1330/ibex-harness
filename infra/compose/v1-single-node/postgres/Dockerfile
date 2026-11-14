# IBEX Harness — v1-single-node Postgres image with pgBackRest (ADR-0097 §5).
#
# The profile needs a Postgres that can archive WAL and take base backups
# without a second SSH-reachable host: pgBackRest runs *inside* this container
# as the local cluster, so the archive command and the backup job use the same
# config, the same repository, and the same credentials.
#
# The base image is pinned by digest only, matching every other Dockerfile in
# this repository (a tag beside a digest is ignored by the runtime and can drift
# from what is actually pulled). Readable identity: pgvector/pgvector:0.8.6-pg16.
# The pgBackRest package is pinned to the exact PGDG build Debian bookworm ships;
# the PGDG repository is already configured by the upstream postgres image, so no
# extra apt source is added here.
FROM pgvector/pgvector@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b

# One layer for both installs: --no-install-recommends keeps the runtime image
# from pulling in documentation and build tooling, and the apt lists are removed
# in the same layer so the image does not carry a stale index.
#
# /var/spool/pgbackrest is the synchronous archive-push spool. It must exist and
# belong to the postgres user before the server starts; creating it in the image
# keeps the data volume untouched.
#
# /var/log/pgbackrest is not created here on purpose: the pgbackrest package owns
# it (listed in `dpkg -L pgbackrest`) and installs it postgres:postgres 0750,
# which is what the default log-path needs. Verified on the built image as uid
# 999: `pgbackrest --stanza=ibex-main --log-level-file=info info` wrote
# /var/log/pgbackrest/ibex-main-info.log without a permission error. Re-check
# with `dpkg -L pgbackrest` before adding a duplicate install -d here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        pgbackrest=2.60.0-1.pgdg12+1 \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -o postgres -g postgres -m 0750 /var/spool/pgbackrest

# The stanza config is mounted at /etc/pgbackrest/pgbackrest.conf (read-only) by
# the compose file. Do not bake a config into the image: it carries credentials.
#
# Run as the postgres user rather than as root. The upstream entrypoint uses root
# only to chown PGDATA on first boot; that chown is done instead by the
# `postgres-volume-init` one-shot in the compose file, which is the only place
# that needs root. Starting the server as uid 999 directly means the long-running
# container never holds root, and the restore and backup one-shots that share
# this image write into the data volume as the same uid that owns it.
USER postgres
