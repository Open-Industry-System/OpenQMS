# Fixed D4 receiver image for the isolation experiment.
#
# The base image is pinned by digest, never by tag: a floating tag would let the
# published image change under a reviewed recipe. The digest must be filled in
# from the environment receipt before this recipe is used; the placeholder below
# is deliberately invalid so an unfilled recipe fails loudly instead of building
# something unexpected.
#
# Only the already-reviewed receiver file is copied. No checkout, no HOME, no
# application code, no provider packages, no database directory.
ARG BASE_DIGEST=sha256:REPLACE_WITH_REVIEWED_DIGEST
FROM python@${BASE_DIGEST}

# The receiver is the only program. It is executed as a non-root identity and
# must remain byte-identical to the reviewed file.
COPY --chmod=0444 backend/examples/readonly_d4_text_receiver.py /receiver.py

# No additional packages are installed; the pinned base retains its utilities.
USER 2001:2001

# Read-only root filesystem is imposed by the runtime, not by this file; the
# non-root execution alone does not make the base filesystem read-only.
ENTRYPOINT ["python", "-I", "-S", "-B", "/receiver.py"]
