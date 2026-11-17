ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
ARG SOURCE_REVISION
ARG ARTIFACT_SHA256
ARG RUNTIME_SHA256
ARG BUILD_CONTEXT_SHA256
LABEL dev.oc2.source-revision=${SOURCE_REVISION} dev.oc2.artifact-sha256=${ARTIFACT_SHA256} dev.oc2.runtime-sha256=${RUNTIME_SHA256} dev.oc2.base-image-ref=${BASE_IMAGE} dev.oc2.build-context-sha256=${BUILD_CONTEXT_SHA256}
COPY --chmod=0555 opencode-v2.2.5 /opt/oc2/bin/opencode
COPY --chmod=0555 entrypoint.py /opt/oc2/slice-b/entrypoint
COPY --chmod=0444 offline_fixture.py /opt/oc2/slice-b/offline_fixture.py
WORKDIR /workspace
USER 10001:10001
ENTRYPOINT ["/opt/oc2/slice-b/entrypoint"]
CMD ["run"]
