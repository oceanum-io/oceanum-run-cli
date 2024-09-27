from unittest import TestCase
from unittest.mock import patch, MagicMock

from datetime import datetime, timezone
import requests

from click.testing import CliRunner


from oceanum.cli.main import main
from oceanum.cli.run import models, client

runner = CliRunner()

route_schema = models.RouteSchema(
    name='test-route',
    org='test-org',
    username='test-user',
    display_name='test-route',
    created_at=datetime.now(tz=timezone.utc),
    project='test-project',
    stage='test-stage',
    status='active',
    url='http://test-route'
)

class TestAllowProject(TestCase):
    def test_allow_help(self):
        result = runner.invoke(main, ['run', 'allow', 'project', '--help'])
        assert result.exit_code == 0

    def test_allow_route_not_found(self):
        response = MagicMock(status_code=404)
        response.json.return_value = {'detail': 'not found!'}
        response.raise_for_status.side_effect = requests.exceptions.HTTPError('404')
        with patch('requests.request', return_value=response) as mock_request:
            result = runner.invoke(main, ['run', 'allow', 'route', 'some-random-route','some-user'])
            assert result.exit_code == 1
            assert mock_request.call_count == 1

    def test_allow_route(self):
        post_response = MagicMock(status_code=200)
        post_response.json.return_value = {'success': True}
        with patch.object(client.DeployManagerClient, 'get_route', return_value=route_schema) as mock_request:
            with patch.object(client.DeployManagerClient, '_post', return_value=(post_response, None)) as mock_request:
                result = runner.invoke(main, ['run', 'allow', 'route', 'test-route','some-user','--change'])
                assert result.exit_code == 0
                assert 'success' in result.output
