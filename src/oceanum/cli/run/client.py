
import os
import yaml
import time
from enum import Enum
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional, Type

import click
import humanize
import requests
from pydantic import SecretStr, RootModel, Field, model_validator, ValidationError

from oceanum.cli.common.symbols import spin, chk, err, wrn, watch, globe
from . import models
from .utils import format_route_status as _frs

class RevealedSecretStr(RootModel):
    root: Optional[str|SecretStr] = None

    @model_validator(mode='after')
    def validate_revealed_secret_str(self):
        if isinstance(self.root, SecretStr):
            self.root = self.root.get_secret_value()
        return self            
    
class RevealedSecretData(models.SecretData):
    root: Optional[dict[str, RevealedSecretStr]] = None

class RevealedSecretSpec(models.SecretSpec):
    data: Optional[RevealedSecretData] = None

class RevealedSecretsBuildCredentials(models.BuildCredentials):
    password: Optional[RevealedSecretStr] = None

class RevealedSecretsBuildSpec(models.BuildSpec):
    credentials: Optional[RevealedSecretsBuildCredentials] = None

class RevealedSecretsCustomDomainSpec(models.CustomDomainSpec):
    tls_cert: Optional[RevealedSecretStr] = Field(
        default=None, 
        alias='tlsCert'
    )
    tls_key: Optional[RevealedSecretStr] = Field(
        default=None, 
        alias='tlsKey'
    )

class RevealedSecretsRouteSpec(models.ServiceRouteSpec):
    custom_domains: Optional[list[RevealedSecretsCustomDomainSpec]] = Field(
        default=None, 
        alias='customDomains'
    )

class RevealedSecretsServiceSpec(models.ServiceSpec):
    routes: Optional[list[RevealedSecretsRouteSpec]] = None

class RevealedSecretsImageSpec(models.ImageSpec):
    username: Optional[RevealedSecretStr] = None
    password: Optional[RevealedSecretStr] = None

class RevealedSecretsSourceRepositorySpec(models.SourceRepositorySpec):
    token: Optional[RevealedSecretStr] = None

class RevealedSecretProjectResourcesSpec(models.ProjectResourcesSpec):
    secrets: Optional[list[RevealedSecretSpec]] = None
    build: Optional[RevealedSecretsBuildCredentials] = None
    images: Optional[list[RevealedSecretsImageSpec]] = None
    sources: Optional[list[RevealedSecretsSourceRepositorySpec]] = None

class RevealedSecretsProjectSpec(models.ProjectSpec):
    resources: Optional[RevealedSecretProjectResourcesSpec] = None

def dump_with_secrets(spec: models.ProjectSpec) -> dict:
    spec_dict = spec.model_dump(
        exclude_none=True,
        exclude_unset=True,
        by_alias=True,
        mode='python'
    )
    return RevealedSecretsProjectSpec(**spec_dict).model_dump(
        exclude_none=True,
        exclude_unset=True,
        by_alias=True,
        mode='json'
    )


class DeployManagerClient:
    def __init__(self, ctx: click.Context|None = None, token: str|None = None, service: str|None = None) -> None:
        if ctx is not None:
            self.token = f"Bearer {ctx.obj.token.access_token}"
            self.service = f'https://dpm.{ctx.obj.domain}/api'
        else:
            self.token = token or os.getenv('DPM_TOKEN')
            self.service = service or os.getenv('DPM_API_URL')
        self.ctx = ctx
        self._lag = 2 # seconds

    def _request(self, 
        method: Literal['GET', 'POST', 'PUT','DELETE','PATCH'], 
        endpoint, **kwargs
    ) -> tuple[requests.Response, models.ErrorResponse|None]:
        assert self.service is not None, 'Service URL is required'
        if self.token is not None:
            headers = kwargs.pop('headers', {})|{
                'Authorization': f'{self.token}'
            }
        url = f"{self.service.removesuffix('/')}/{endpoint}"
        response = requests.request(method, url, headers=headers, **kwargs)
        return response, self._handle_errors(response)
 
    def _get(self, endpoint, **kwargs) -> tuple[requests.Response, models.ErrorResponse|None]:
        return self._request('GET', endpoint, **kwargs)
    
    def _post(self, endpoint, **kwargs) -> tuple[requests.Response, models.ErrorResponse|None]:
        return self._request('POST', endpoint, **kwargs)
    
    def _patch(self, endpoint, **kwargs) -> tuple[requests.Response, models.ErrorResponse|None]:
        return self._request('PATCH', endpoint, **kwargs)
    
    def _put(self, endpoint, **kwargs) -> tuple[requests.Response, models.ErrorResponse|None]:
        return self._request('PUT', endpoint, **kwargs)
    
    def _delete(self, endpoint, **kwargs) -> tuple[requests.Response, models.ErrorResponse|None]:
        return self._request('DELETE', endpoint, **kwargs)
    
    def _wait_project_commit(self, **params) -> bool:
        while True:
            project = self.get_project(**params)
            if isinstance(project, models.ProjectSchema) and project.last_revision is not None:
                if project.last_revision.status == 'created':
                    time.sleep(self._lag)
                    click.echo(f' {spin} Waiting for Revision #{project.last_revision.number} to be committed...')
                    continue
                elif project.last_revision.status == 'no-change':
                    click.echo(f' {wrn} No changes to commit, exiting...')
                    return False
                elif project.last_revision.status == 'failed':
                    click.echo(f" {err} Revision #{project.last_revision.number} failed to commit, exiting...")
                    return False
                elif project.last_revision.status == 'commited':
                    click.echo(f" {chk} Revision #{project.last_revision.number} committed successfully")
                    return True
            else:
                click.echo(f' {err} No project revision found, exiting...')
                break
        return True
    
    def _wait_stages_start_updating(self, **params):
        counter = 0
        while True:
            project = self.get_project(**params)
            if isinstance(project, models.ProjectSchema):
                updating = any([s.status in ['updating','degraded'] for s in project.stages])
                ready_stages = all([s.status in ['ready', 'error'] for s in project.stages])
                if updating:
                    break
                elif counter > 5 and ready_stages:
                    #click.echo(f"Project '{project.name}' finished being updated in {time.time()-start:.2f}s")
                    break
                else:
                    click.echo(f' {spin} Waiting for project to start updating...')
                    pass
                    time.sleep(self._lag)
                    counter += 1
                return project
            else:
                click.echo(f' {err} Failed to get project details!')
                break
    
    def _wait_builds_to_finish(self, **params):
        messaged = False
        project = self.get_project(**params)
        if isinstance(project, models.ProjectSchema):
            last_revision = project.last_revision if project else None
            project_spec = last_revision.spec if last_revision else None
            resources = project_spec.resources if project_spec else None
            spec_builds = resources.builds if resources else None
            if project_spec is not None and resources and spec_builds:                
                click.echo(f' {spin} {spin} Revision expects one or more images to be built, this can take several minutes...')
                time.sleep(self._lag*6)
                while True:
                    updating_builds = []
                    ready_builds = []
                    errors = []
                    project = self.get_project(**params)
                    builds = project.builds if isinstance(project, models.ProjectSchema) else []
                    project_name = project.name if isinstance(project, models.ProjectSchema) else 'unknown'
                    for build in builds:
                        if build.status in ['updating', 'pending']:
                            updating_builds.append(build)
                        elif build.status in ['error']:
                            click.echo(f" {err} Build '{build.name}' operation failed!")
                            errors.append(build)
                            ready_builds.append(build)
                        elif build.status in ['success']:
                            click.echo(f" {chk} Build '{build.name}' operation succeeded!")
                            ready_builds.append(build)

                    if errors:
                        click.echo(f" {wrn} Project '{project_name}' failed to build images! Exiting...")
                        return False
                    elif updating_builds and not messaged:
                        click.echo('Waiting for image-builds to finish, this can take several minutes...')
                        messaged = True
                        continue
                    if len(ready_builds) == len(builds):
                        click.echo(f' {chk} All builds are finished!')
                        break
                    time.sleep(self._lag)
                return True
    
    def _wait_stages_finish_updating(self, **params):
        counter = 0
        click.echo(f' {spin} Waiting for all stages to finish updating...')
        while True:
            project = self.get_project(**params)
            if isinstance(project, models.ProjectSchema):
                project_name = project.name if project else 'unknown'
                stages = project.stages if project else []
                updating = any([s.status in ['building'] for s in stages])
                all_finished = all([s.status in ['healthy', 'error'] for s in stages])
                if updating:
                    time.sleep(self._lag)
                    continue
                elif all_finished:
                    click.echo(f" {chk} Project '{project_name}' finished being updated!")
                    break
                else:
                    time.sleep(self._lag)
                    counter += 1
    
    def _check_routes(self, **params):
        project = self.get_project(**params)
        if isinstance(project, models.ProjectSchema):
            project_name = project.name if project else 'unknown'
            routes = project.routes if project else []
            for route in routes:
                urls = [f"https://{d}/" for d in route.custom_domains] + [route.url]
                if route.status == 'error':
                    click.echo(f" {err} Route '{route.name}' at stage '{route.stage}' failed to start!")
                    click.echo(f"Status is {_frs(route.status)}, inspect deployment with 'oceanum dpm inspect project {project_name}'!")
                else:
                    s = 's' if len(urls) > 1 else ''
                    click.echo(f" {chk} Route '{route.name}' is {_frs(route.status)} and available at URL{s}:")
                    for url in urls:
                        click.echo(f" {globe} {url}")
    
    def _handle_errors(self, response: requests.Response) -> models.ErrorResponse|None:
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            try:
                return models.ErrorResponse(**response.json())
            except requests.exceptions.JSONDecodeError:
                return models.ErrorResponse(detail=response.text)
            except ValidationError as e:
                return models.ErrorResponse(detail=response.json())
            except Exception as e:
                return models.ErrorResponse(detail=str(e))
    
    def wait_project_deployment(self, **params) -> bool:
        start = time.time()
        committed = self._wait_project_commit(**params)
        if committed:
            self._wait_stages_start_updating(**params)
            self._wait_builds_to_finish(**params)
            self._wait_stages_finish_updating(**params)
            self._check_routes(**params)
            delta = timedelta(seconds=time.time()-start)
            click.echo(f" {watch} Deployment finished in {humanize.naturaldelta(delta)}.")
        return True
    
    @classmethod
    def load_spec(cls, specfile: str) -> models.ProjectSpec|models.ErrorResponse:
        try:
            with Path(specfile).open() as f:
                spec_dict = yaml.safe_load(f)
            return models.ProjectSpec(**spec_dict)
        except FileNotFoundError as e:
            return models.ErrorResponse(detail=f"Specfile not found: {specfile}")
        except ValidationError as e:
            return models.ErrorResponse(detail=[
                models.ValidationErrorDetail(
                    loc=[str(v) for v in e['loc']], 
                    msg=e['msg'], 
                    type=e['type']) for e in e.errors()
                ])
    
    def deploy_project(self, spec: models.ProjectSpec) -> models.ProjectSchema | models.ErrorResponse:
        payload = dump_with_secrets(spec)
        response, errs = self._post('projects', json=payload)
        return errs if errs else models.ProjectSchema(**response.json())

    def patch_project(self, project_name: str, ops: list[models.JSONPatchOpSchema]) -> models.ProjectSchema | models.ErrorResponse:
        payload = [op.model_dump(exclude_none=True, mode='json') for op in ops]
        response, errs = self._patch(f'projects/{project_name}', json=payload)
        return errs if errs else models.ProjectSchema(**response.json())
    
    def delete_project(self, project_id: str, **filters) -> str | models.ErrorResponse:
        response, errs = self._delete(f'projects/{project_id}', params=filters or None)
        return errs if errs else "Project deleted successfully!"
    
    def get_users(self) -> list[models.UserSchema] | models.ErrorResponse:
        response, errs = self._get('users')
        if not errs:
            return [models.UserSchema(**user) for user in response.json()]
        return errs

    def list_projects(self, **filters) -> list[models.ProjectSchema] | models.ErrorResponse:
        response, errs = self._get('projects', params=filters or None)
        if not errs:
            projects_json = response.json()
            projects = []
            for project in projects_json:
                try:
                    models.ProjectSchema(**project)
                    projects.append(project)
                except Exception as e:
                    click.echo(f"Error: {e}")
                    click.echo(f"Project: {project}")
            return projects
        else:
            return errs
    
    def get_project(self, project_name: str, **filters) -> models.ProjectSchema|models.ErrorResponse:
        """
        Try to get a project by name and org/user filters,
        when the project is not found, print the error message and return None
        """
        response, errs = self._get(f'projects/{project_name}', params=filters or None)
        return errs if errs else models.ProjectSchema(**response.json())
    
    def list_routes(self, **filters) -> list[models.RouteSchema] | models.ErrorResponse:
        response, errs = self._get('routes', params=filters or None)
        if not errs:
            return [models.RouteSchema(**route) for route in response.json()]
        else:
            return errs
    
    def get_route(self, route_name: str) -> models.RouteSchema | models.ErrorResponse:
        response, errs = self._get(f'routes/{route_name}')
        return errs if errs else models.RouteSchema(**response.json())
    
    def update_route_thumbnail(self, route_name: str, thumbnail: click.File) -> models.RouteThumbnailSchema | models.ErrorResponse:
        files = {'thumbnail': thumbnail}
        response, errs = self._post(f'routes/{route_name}/thumbnail', files=files)
        return errs if errs else models.RouteThumbnailSchema(**response.json())
    
    def validate(self, specfile: str) -> models.ProjectSpec | models.ErrorResponse:
        resp = self.load_spec(specfile)
        if isinstance(resp, models.ErrorResponse):
            return resp
        else:
            spec_dict = resp.model_dump(
                exclude_none=True,
                exclude_unset=True,
                by_alias=True,
                mode='json'
            )
            response, errs = self._post('validate', json=spec_dict)
            return errs if errs else models.ProjectSpec(**response.json())
        
    def allow_project(self, 
        project_name: str, 
        permissions: models.PermissionsSchema, 
        **filters
    ) -> models.ConfirmationResponse | models.ErrorResponse:
        response, errs = self._post(
            f'projects/{project_name}/permissions',
            params=filters or None, 
            json=permissions.model_dump()
        )
        return errs if errs else models.ConfirmationResponse(**response.json())
    
    def allow_route(self, 
        route_name: str, 
        permissions: models.PermissionsSchema, 
        **filters
    ) -> models.ConfirmationResponse | models.ErrorResponse:
        response, errs = self._post(
            f'routes/{route_name}/permissions',
            params=filters or None, 
            json=permissions.model_dump()
        )
        return errs if errs else models.ConfirmationResponse(**response.json())