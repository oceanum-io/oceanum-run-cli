from unittest import TestCase
from pathlib import Path
from datetime import datetime, timezone
import requests
from unittest.mock import patch, MagicMock
from oceanum.cli.run import main, project, route, user, models
from oceanum.cli.run.main import run_group
from oceanum.cli.run.client import DeployManagerClient
from oceanum.cli.main import main
from oceanum.cli.common.models import ContextObject, TokenResponse, Auth0Config
from click.testing import CliRunner
from click.globals import get_current_context

class TestDPMCommands(TestCase):

    def setUp(self) -> None:
        self.runner = CliRunner()
        self.specfile = Path(__file__).parent / 'data/dpm-project.yaml'
        return super().setUp()

    
    

    def test_describe_help(self):
        result = self.runner.invoke(run_group, ['describe', '--help'])
        assert result.exit_code == 0


    def test_describe_route(self):
        route = models.RouteSchema(
            name='test-route',
            org='test-org',
            username='test-user',
            display_name='test-route',
            created_at=datetime.now().replace(tzinfo=timezone.utc),
            project='test-project',
            stage='test-stage',
            status='active',
            url='http://test-route'
        )
        with patch('oceanum.cli.run.client.DeployManagerClient.get_route', return_value=route) as mock_get:
            result = self.runner.invoke(main, ['run','describe','route','test-route'])
            assert result.exit_code == 0
            mock_get.assert_called_once_with('test-route')
    
    def test_describe_route_not_found(self):
        result = self.runner.invoke(main, ['run','describe','route','test-route'])
        assert result.exit_code != 0

    def test_list_routes(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.list_routes') as mock_list:
            result = self.runner.invoke(main, ['run','list','routes'])
            assert result.exit_code == 0
            mock_list.assert_called_once_with()
    
    def test_list_routes_apps(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.list_routes') as mock_list:
            result = self.runner.invoke(main, ['run','list','routes','--apps'])
            assert result.exit_code == 0
            mock_list.assert_called_once_with(publish_app=True)
    
    def test_list_routes_services(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.list_routes') as mock_list:
            result = self.runner.invoke(main, ['run','list','routes','--services'])
            assert result.exit_code == 0
            mock_list.assert_called_once_with(publish_app=False)

    def test_list_routes_open(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.list_routes') as mock_list:
            result = self.runner.invoke(main, ['run','list','routes','--open'])
            assert result.exit_code == 0
            mock_list.assert_called_once_with(open_access=True)

    def test_list_no_routes(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.list_routes') as mock_list:
            mock_list.return_value = []
            result = self.runner.invoke(main, ['run','list','routes'])
            assert result.exit_code == 0
