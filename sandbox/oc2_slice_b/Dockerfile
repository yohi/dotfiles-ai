ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY --chmod=0555 opencode-v2.2.5 /opt/oc2/bin/opencode
COPY --chmod=0555 entrypoint.py /opt/oc2/slice-b/entrypoint
COPY --chmod=0444 offline_fixture.py /opt/oc2/slice-b/offline_fixture.py
WORKDIR /workspace
USER 10001:10001
ENTRYPOINT ["/opt/oc2/slice-b/entrypoint"]
CMD ["run"]
