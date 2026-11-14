"""Server-owned restrictions on message content before runtime delivery."""

TEXT_PROFILE = 'local_d4_root_cause_text_v1'
START_MESSAGE = 'deliver_d4_root_cause_candidate_v1'


def require_profile_message_contents(profile, rows):
    if profile == TEXT_PROFILE and any(row.content != START_MESSAGE for row in rows):
        raise PermissionError('Message unavailable')
