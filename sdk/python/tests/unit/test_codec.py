from codec_fixtures import codec, deny_network


def test_capabilities_has_no_body_or_query():
    import importlib.util
    assert importlib.util.find_spec('openqms_agent_sdk._codec') is not None
    encoded = codec().encode_request('capabilities', {})
    assert encoded.body is None
    assert encoded.query == ()
