"""No credentials or provider authority may leak into ordinary/browser children."""
from tests.e2e.capa_outcome_runner import provider_environment, child_environment


def test_ordinary_child_rejects_ambient_provider_and_proxy_authority():
    env = child_environment({'PATH': '/safe', 'HOME': '/owned', 'LLM_API_KEY': 'ambient',
        'ANTHROPIC_AUTH_TOKEN': 'ambient', 'HTTPS_PROXY': 'unapproved', 'NODE_OPTIONS': '--require unsafe'})
    assert env == {'PATH': '/safe', 'HOME': '/owned', 'NO_PROXY': '*', 'no_proxy': '*'}


def test_live_profile_never_expands_or_passes_arbitrary_environment(tmp_path):
    profile = tmp_path / '.env.e2e'
    profile.write_text('LLM_PROVIDER=openai\nLLM_API_KEY=test-secret\nLLM_MODEL=test-model\n'
        'LLM_BASE_URL=https://test.invalid\nLLM_TIMEOUT=30\nDATABASE_URL=do-not-use\n'
        'ANTHROPIC_AUTH_TOKEN=do-not-use\nNODE_OPTIONS=do-not-use\n')
    env, diagnostic = provider_environment(profile)
    assert diagnostic == 'authorized_test_profile'
    assert set(env) == {'LLM_PROVIDER', 'LLM_API_KEY', 'LLM_MODEL', 'LLM_BASE_URL', 'LLM_TIMEOUT'}
    assert env['LLM_API_KEY'] == 'test-secret'
    profile.write_text('LLM_PROVIDER=openai\nLLM_API_KEY=${AMBIENT_SECRET}\n')
    env, diagnostic = provider_environment(profile)
    assert diagnostic == 'invalid_test_profile' and env == {}


def test_missing_profile_is_not_a_skip_or_ambient_fallback(tmp_path):
    env, diagnostic = provider_environment(tmp_path / '.env.e2e')
    assert env == {} and diagnostic == 'missing_test_profile'


def test_live_profile_rejects_invalid_timeout_without_ambient_fallback(tmp_path):
    profile = tmp_path / '.env.e2e'
    profile.write_text('LLM_PROVIDER=openai\nLLM_API_KEY=test-secret\nLLM_TIMEOUT=not-an-integer\n')
    env, diagnostic = provider_environment(profile)
    assert diagnostic == 'invalid_test_profile' and env == {}
