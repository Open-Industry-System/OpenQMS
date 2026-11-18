# Build from the reviewed repository and pass an approved Python base digest.
ARG BASE_DIGEST
FROM python@${BASE_DIGEST}

WORKDIR /opt/openqms-d4
COPY --chmod=0444 backend/examples/readonly_d4_text_receiver.py /opt/openqms-d4/
COPY --chmod=0444 deploy/d4-acceptance/revoke_wire.py deploy/d4-acceptance/revoke_receiver.py /opt/openqms-d4/
RUN echo '3a2dfa9712c2ffebc62c26da0c4c03192be4ec905d1ee83e3ae198bfab51fa21  readonly_d4_text_receiver.py' | sha256sum -c -

USER 2001:2001
ENTRYPOINT ["python", "-I", "-S", "-B", "/opt/openqms-d4/revoke_receiver.py"]
