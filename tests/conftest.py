# patch the function user_data_dir from the platformdirs module to return a temporary directory
# This is a pytest conftest.py file

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from oceanum.cli.common.models import TokenResponse
import pytest

tmpdir = tempfile.TemporaryDirectory()
dir_patcher = patch('platformdirs.user_data_dir', return_value=tmpdir.name)
active_org_patcher = patch.object(TokenResponse, 'active_org', return_value='test-org')
email_patcher = patch.object(TokenResponse, 'email', return_value='test@test.com')


def pytest_sessionstart(session):
    dir_patcher.start()
    TokenResponse(
        access_token='123',
        expires_in=3600,
        token_type='Bearer',
        domain='oceanum.test',
        refresh_token='456'
    ).save()
    active_org_patcher.start()
    email_patcher.start()
    

def pytest_sessionfinish(session):
    dir_patcher.stop()
    active_org_patcher.stop()
    email_patcher.stop()
    tmpdir.cleanup()