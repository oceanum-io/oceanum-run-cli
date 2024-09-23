from unittest import TestCase
from unittest.mock import patch, MagicMock
from pathlib import Path

import requests
import yaml

from pydantic import ValidationError
from click.testing import CliRunner

from datetime import datetime, timezone

from oceanum.cli.main import main
from oceanum.cli.common.models import TokenResponse
from oceanum.cli.run import project, models, client

runner = CliRunner()

good_specfile = Path(__file__).parent/'data/dpm-project.yaml'
with good_specfile.open() as f:
    project_schema = models.ProjectSchema(
        routes=[],
        stages=[],
        builds=[],
        last_revision=models.SpecRevisionSchema(
            spec=models.ProjectSpec(**yaml.safe_load(f)),
            created_at=datetime.now().replace(tzinfo=timezone.utc),
            number=1,
            status='active',
            author='test-user',
        ),
        name='test-project',
        org='test-org',
        owner='test-user',
        created_at=datetime.now().replace(tzinfo=timezone.utc),
        description='test-description',
        status='healthy',
    )


class TestDeleteProject(TestCase):
    
    def test_delete_error(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.get_project',
            return_value=project_schema) as mock_get:
            with patch('oceanum.cli.run.client.DeployManagerClient.delete_project', 
                return_value=models.ErrorResponse(detail='test-error')) as mock_delete:
                result = runner.invoke(main, ['run', 'delete', 'project', 'test-project'], input='y')
                assert 'Failed to delete' in result.output
                assert result.exit_code == 1
                assert mock_delete.call_count == 1

    def test_delete_confirm_no(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.get_project',
            return_value=project_schema) as mock_get:
            with patch('oceanum.cli.run.client.DeployManagerClient.delete_project') as mock_delete:
                result = runner.invoke(main, ['run', 'delete', 'project', 'test-project'], input='n')
                assert result.exit_code == 1
                assert mock_delete.call_count == 0
                assert 'Aborted!' in result.output
    
    def test_delete_project_not_found(self):
        response = MagicMock(status_code=404)
        response.json.return_value = {'detail': 'not found!'}
        response.raise_for_status.side_effect = requests.exceptions.HTTPError('404')
        with patch('requests.request', return_value=response) as mock_request:
            result = runner.invoke(main, ['run', 'delete', 'project', 'some-random-project'])
            assert result.exit_code == 1
            assert mock_request.call_count == 1
            assert 'not found!' in result.output
    
    def test_delete_existing_project_error(self):
        response = MagicMock(status_code=403)
        response.json.return_value = {'detail': 'Forbidden!'}
        response.raise_for_status.side_effect = requests.exceptions.HTTPError('403')
        with patch('oceanum.cli.run.client.DeployManagerClient.get_project', return_value=project_schema) as mock_get:
            with patch('requests.request', return_value=response) as mock_request:
                result = runner.invoke(main, ['run', 'delete', 'project', 'test-project'], input='y')
                assert result.exit_code == 1
                assert mock_request.call_count == 1
                assert 'Forbidden!' in result.output

    def test_delete_project(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.get_project',
            return_value=project_schema) as mock_get:
            with patch('oceanum.cli.run.client.DeployManagerClient.delete_project') as mock_delete:
                result = runner.invoke(main, ['run', 'delete', 'project', 'test-project'], input='y')
                assert result.exit_code == 0
                assert mock_delete.call_count == 1
                assert 'removed shortly' in result.output

class TestListProject(TestCase):

    def test_list_error(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.list_projects', 
            return_value=models.ErrorResponse(detail='test-error')) as mock_list:
            result = runner.invoke(main, ['run', 'list', 'projects'])
            assert result.exit_code == 1
            assert 'Could not list' in result.output
            mock_list.assert_called_once_with()
    
    def test_list_project_not_found(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.list_projects', return_value=[]) as mock_list:
            result = runner.invoke(main, ['run', 'list', 'projects'])
            assert result.exit_code == 1
            assert 'No projects found!' in result.output
            mock_list.assert_called_once_with()
    

    def test_list_project(self):
        projects = [
            models.ProjectSchema(
                routes=[],
                stages=[],
                builds=[],
                name='test-project',
                org='test-org',
                owner='test-user',
                created_at=datetime.now().replace(tzinfo=timezone.utc),
                description='test-description',
                status='healthy',
            ),
        ]

        with patch('oceanum.cli.run.client.DeployManagerClient.list_projects', return_value=projects) as mock_list:
            result = runner.invoke(main, ['run', 'list', 'projects'])
            assert result.exit_code == 0
            mock_list.assert_called_once_with()


class TestValidateProject(TestCase):
    def setUp(self) -> None:
        self.specfile = Path(__file__).parent/'data/dpm-project.yaml'
        self.project_spec = client.DeployManagerClient.load_spec(str(self.specfile))
        return super().setUp()
    
    def test_validation_error_no_file(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.validate') as mock_validate:
            result = runner.invoke(main, ['run', 'validate', str('randomfile.yaml')])
            assert result.exit_code > 0
            assert 'does not exist' in result.output

    def test_validation_error_badspec(self):
        bad_spec = {
            'name': 'my-project',
            'org': 'test-org',
        }
        with patch('oceanum.cli.run.client.DeployManagerClient.validate') as mock_validate:
            try:
                models.ProjectSpec(**bad_spec) # type: ignore
            except ValidationError as e:
                mock_validate.return_value = models.ErrorResponse(detail=e.errors()) # type: ignore
            result = runner.invoke(main, ['run', 'validate', str(self.specfile)], catch_exceptions=True)
            assert result.exit_code > 0
            assert 'Extra inputs are not permitted' in result.output

    def test_validate_specfile(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.validate') as mock_validate:
            result = runner.invoke(main, ['run','validate', str(self.specfile)], catch_exceptions=True)
            assert result.exit_code == 0
            mock_validate.assert_called_once_with(self.specfile)


class TestUpdateProject(TestCase):
    def test_update_active(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.get_project', return_value=project_schema) as mock_get:
            patch_resp = project_schema.model_copy(update={'active': False})
            with patch('oceanum.cli.run.client.DeployManagerClient.patch_project', return_value=patch_resp) as mock_update:
                result = runner.invoke(main, ['run', 'update', 'project', 'test-project', '--active', '0'])
                assert 'updated' in result.output

    def test_update_description(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.get_project', return_value=project_schema) as mock_get:
            patch_resp = project_schema.model_copy(update={'description': 'new-description'})
            with patch('oceanum.cli.run.client.DeployManagerClient.patch_project', return_value=patch_resp) as mock_update:
                result = runner.invoke(main, ['run', 'update', 'project', 'test-project', '--description', 'new-description'])
                assert 'updated' in result.output

    def test_update_error(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.get_project', return_value=project_schema) as mock_get:
            with patch('oceanum.cli.run.client.DeployManagerClient.patch_project', return_value=models.ErrorResponse(detail='test-error')) as mock_update:
                result = runner.invoke(main, ['run', 'update', 'project', 'test-project', '--active', '0'])
                assert 'Failed to update' in result.output
                assert result.exit_code == 1


class TestDeployProject(TestCase):

    def setUp(self) -> None:
        self.specfile = str(Path(__file__).parent/'data/dpm-project.yaml')
        self.bad_specfile = str(Path(__file__).parent/'data/bad-project.yaml')
        return super().setUp()
    
    def tearDown(self) -> None:
        return super().tearDown()

    def test_deploy_help(self):
        result = runner.invoke(main, ['run','deploy', '--help'])
        assert result.exit_code == 0
        
    def test_deploy_empty(self):
        result = runner.invoke(main, ['run','deploy'])
        assert result.exit_code != 0
        assert 'Missing argument' in result.output

    def test_deploy_specfile_not_found(self):
        result = runner.invoke(main, ['run','deploy', 'randomfile.yaml'])
        assert result.exit_code != 0
        assert 'does not exist' in result.output

    def test_deploy_specfile_error(self):
        result = runner.invoke(main, ['run','deploy', str(self.bad_specfile)])
        assert result.exit_code != 0
        assert 'Extra inputs are not permitted' in result.output

    def test_deploy_specfile_no_args(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.get_project', 
            return_value=project_schema
        ) as mock_get:
            with patch('oceanum.cli.run.client.DeployManagerClient.deploy_project', 
                return_value=project_schema
            ) as mock_deploy:
                result = runner.invoke(
                    main, ['run','deploy', str(self.specfile),'--wait=0']
                )
                assert 'created successfully' in result.output
                assert result.exit_code == 0
                assert mock_deploy.call_args[0][0].name == project_schema.name
                
    def test_deploy_specfile_with_secrets(self):
        secret_overlay = 'test-secret:token=123456'
        with patch('oceanum.cli.run.client.DeployManagerClient.get_project', return_value=project_schema) as mock_get:
            with patch('oceanum.cli.run.client.DeployManagerClient.deploy_project', return_value=project_schema) as mock_deploy:
                result = runner.invoke(
                    main, ['run','deploy', str(self.specfile),'-s', secret_overlay,'--wait=0']
                )
                assert result.exit_code == 0
                assert mock_deploy.call_args[0][0].resources.secrets[0].data.root['token'] == '123456'

    def test_deploy_with_org_member(self):
        with patch('oceanum.cli.run.client.DeployManagerClient.get_project', return_value=project_schema) as mock_get:
            with patch('oceanum.cli.run.client.DeployManagerClient.deploy_project', return_value=project_schema) as mock_deploy:
                result = runner.invoke(
                    main, ['run','deploy', str(self.specfile),'--org','test','--wait=0','--user=test@test.com']
                )
                assert result.exit_code == 0
                assert mock_deploy.call_args[0][0].user_ref.root == 'test'
                assert mock_deploy.call_args[0][0].member_ref == 'test@test.com'
