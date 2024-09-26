import sys
from os import linesep
from pathlib import Path
from functools import partial

import yaml
import requests
import click

from oceanum.cli.common.renderer import Renderer, RenderField

from oceanum.cli.auth import login_required
from .client import DeployManagerClient
from .main import list_group, describe_group, delete, run_group, update_group, allow_group
from . import models
from .utils import (
    spin, chk, err, wrn, key, info, echoerr, merge_secrets,
    project_status_color as psc,
    stage_status_color as ssc,
)

name_arguement = click.argument('name', type=str)
name_option = click.option('--name', help='Set the resource name', required=False, type=str)
project_org_option = click.option('--org', help='Set the project organization', required=False, type=str)
project_user_option = click.option('--user', help='Set the project owner email', required=False, type=str)

@list_group.command(name='projects', help='List DPM Projects')
@click.pass_context
@click.option('--search', help='Search by project name or description', default=None, type=str)
@click.option('--org', help='filter by Organization name', default=None, type=str)
@click.option('--user', help='filter by User email', default=None, type=str)
@click.option('--status', help='filter by Project status', default=None, type=str)
@login_required
def list_projects(ctx: click.Context, search: str|None, org: str|None, user: str|None, status: str|None):
    click.echo(f' {spin} Fetching DPM projects...')
    client = DeployManagerClient(ctx)
    filters = {
        'search': search,
        'org': org,
        'user': user,
        'status': status
    }
    projects = client.list_projects(**{
        k: v for k, v in filters.items() if v is not None
    })

    fields = [
        RenderField(label='Name', path='$.name'),
        RenderField(label='Org.', path='$.org'),
        RenderField(label='Rev.', path='$.last_revision.number'),
        RenderField(label='Status', path='$.status', mod=psc),
        RenderField(label='Stages', path='$.stages.*', mod=ssc),
    ]
        
    if not projects:
        click.echo(f' {wrn} No projects found!')
        sys.exit(1)
    elif isinstance(projects, models.ErrorResponse):
        click.echo(f" {err} Could not list projects!")
        echoerr(projects)
        sys.exit(1)
    else:
        click.echo(Renderer(data=projects, fields=fields).render(output_format='table'))

@run_group.command(name='validate', help='Validate DPM Project Specfile')
@click.argument('specfile', type=click.Path(exists=True))
@click.pass_context
@login_required
def validate_project(ctx: click.Context, specfile: click.Path):
    click.echo(f' {spin} Validating DPM Project Spec file...')
    client = DeployManagerClient(ctx)
    response = client.validate(str(specfile))
    if isinstance(response, models.ErrorResponse):
        click.echo(f" {err} Validation failed!")
        echoerr(response)
        sys.exit(1)
    else:
        click.echo(f' {chk} OK! Project Spec file is valid!')

@run_group.command(name='deploy', help='Deploy a DPM Project Specfile')
@name_option
@project_org_option
@project_user_option
@click.option('--wait', help='Wait for project to be deployed', default=True)
# Add option to allow passing secrets to the specfile, this will be used to replace placeholders
# can be multiple, e.g. --secret secret-1:key1=value1,key2=value2 --secret secret-2:key2=value2
@click.option('-s','--secrets',help='Replace existing secret data values, i.e secret-name:key1=value1,key2=value2', multiple=True)
@click.argument('specfile', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.pass_context
@login_required
def deploy_project(
    ctx: click.Context, 
    specfile: click.Path, 
    name: str|None, 
    org: str|None, 
    user: str|None,
    wait: bool,
    secrets: list[str]
):

    client = DeployManagerClient(ctx)
    project_spec = client.load_spec(str(specfile))
    if isinstance(project_spec, models.ErrorResponse):
        click.echo(f" {err} Failed to load project spec file!")
        echoerr(project_spec)
        sys.exit(1)

    if name is not None:
        project_spec.name = name
    if org is not None:
        project_spec.user_ref = models.UserRef(org)
    if user is not None:
        project_spec.member_ref = user

    if secrets:
        click.echo(f' {key} Parsing and merging secrets...')
        project_spec = merge_secrets(project_spec, secrets)

    user_org = getattr(project_spec.user_ref, 'root', None) or ctx.obj.token.active_org
    user_email = project_spec.member_ref or ctx.obj.token.email

    get_params = {
        'project_name': project_spec.name,
        'org': user_org,
        'user': user_email
    }
    project = client.get_project(**get_params)
    click.echo()

    if isinstance(project, models.ProjectSchema):
        click.echo(f" {spin} Updating existing DPM Project:")
    else:
        if 'not found' in str(project.detail).lower():
            click.echo(f" {spin} Deploying NEW DPM Project:")
        else:
            click.echo(f" {err} Could not deploy project!")
            echoerr(project)
            sys.exit(1)

    click.echo()
    click.echo(f'  Project Name: {project_spec.name}')
    click.echo(f"  Organization: {getattr(user_org, 'root', user_org)}")
    click.echo(f'  Owner:        {user_email}')
    click.echo()
    click.echo('Safe to Ctrl+C at any time...')
    click.echo()
    project = client.deploy_project(project_spec)
    if isinstance(project, models.ErrorResponse):
        click.echo(f" {err} Deployment failed!")
        click.echo(f" {wrn} {project.detail}")
        sys.exit(1)
    project = client.get_project(**get_params)
    if isinstance(project, models.ProjectSchema) and project.last_revision is not None:
        click.echo(f" {chk} Revision #{project.last_revision.number} created successfully!")
        if wait:
            click.echo(f' {spin} Waiting for project to be deployed...')
            client.wait_project_deployment(**get_params)
    else:
        click.echo(f" {err} Could not retrieve project details!")
        click.echo(f" {wrn} Please check the project status in the DPM console!")

@delete.command(name='project')
@click.argument('project_name', type=str)
@project_org_option
@project_user_option
@click.pass_context
@login_required
def delete_project(ctx: click.Context, project_name: str, org: str|None, user:str|None):
    client = DeployManagerClient(ctx)
    project = client.get_project(project_name, org=org, user=user)
    if isinstance(project, models.ProjectSchema):
        click.confirm(
            f"Deleting project:{linesep}"\
            f"{linesep}"\
            f"Project Name: {project_name}{linesep}"\
            f"Org: {project.org}{linesep}"\
            f"Owner: {project.owner}{linesep}"\
            f"{linesep}"\
            "This will attempt to remove all deployed resources for this project! Are you sure?",
            abort=True
        )
        response = client.delete_project(project_name, org=org, user=user)
        if isinstance(response, models.ErrorResponse):
            click.echo(f" {err} Failed to delete existing project!")
            echoerr(response)
            sys.exit(1)
        else:
            click.echo(f' {chk} Project {project_name} deleted successfuly!')
            click.echo(f' {info} Deployed resources will be removed shortly...')
    else:
        click.echo(f" {err} Failed to delete project '{project_name}'!")
        echoerr(project)
        sys.exit(1)

@describe_group.command(name='project', help='Describe a DPM Project')
@click.option('--show-spec', help='Show project spec', default=False, type=bool, is_flag=True)
@click.option('--only-spec', help='Show only project spec', default=False, type=bool, is_flag=True)
@click.argument('project_name', type=str)
@project_org_option
@project_user_option
@click.pass_context
@login_required
def describe_project(ctx: click.Context, project_name: str, org: str, user:str, show_spec: bool=False, only_spec: bool=False):
    client = DeployManagerClient(ctx)
    project = client.get_project(project_name, org=org, user=user)
    routes = project.routes if isinstance(project, models.ProjectSchema) else None
    last_revision = project.last_revision if isinstance(project, models.ProjectSchema) else None
    project_spec = last_revision.spec if last_revision is not None else None
    click.echo()
    if isinstance(project, models.ProjectSchema) and last_revision and project_spec:
        if not only_spec:
            click.echo()
            click.echo(f"Describing project...")
            click.echo()
            output = [
                ['Name', project.name],
                ['Org', project.org],
                ['User', project_spec.member_ref],
                ['Status', project.status],
                ['Created', project.created_at],
            ]
            if last_revision is not None:
                output.append(
                    ['Last Revision', [
                        ['Number', last_revision.number],
                        ['Created', last_revision.created_at],
                        ['User', project_spec.member_ref],
                        ['Status', last_revision.status],
                    ]]
                )
            if project.stages:
                stages = []
                for stage in project.stages:
                    stages.extend([
                        ['Name', stage.name],
                        ['Status', stage.status],
                        ['Message', stage.error_message],
                        ['Updated', stage.updated_at],
                    ])
                output.append(['Stages', stages])
            if project.builds:
                builds = []
                for build in project.builds:
                    build_output = [
                        ['Name', build.name],
                        ['Status', build.status],
                        ['Stage', build.stage],
                        ['Workflow', build.workflow_ref],
                        ['Updated', build.updated_at],
                    ]
                    if build.image_digest is not None:
                        image_digest = getattr(build.image_digest, 'root', None)
                        build_output.append(['Image Digest', image_digest])
                    if build.commit_sha is not None:
                        commit_sha = getattr(build.commit_sha, 'root', None)
                        build_output.append(['Source Commit', commit_sha])
                    builds.extend(build_output)
                output.append(['Builds', builds])
                
            if project.routes:
                routes = []
                for route in project.routes:
                    route_output =  [
                        ['Name', route.name],
                        ['Status', route.status],
                        ['URL', route.url],
                    ] 
                    if route.custom_domains:
                        route_output.append([
                            'Custom Domains', linesep.join(route.custom_domains)
                        ])
                    routes.extend(route_output)
                output.append(['Routes', routes])

            def print_line(output: list, indent: int = 2):
                for l,line in enumerate(output):
                    if isinstance(line[1], list):
                        click.echo(f"{' ' * indent}{line[0]}:")
                        print_line(line[1], indent=indent + 2)
                    else:
                        prefix = ((' '*(indent-2))+'- ') if indent > 2 and l==0 else (' '* indent)
                        click.echo(f"{prefix}{line[0]}: {line[1]}")
            print_line(output)

        if show_spec or only_spec:
            if not only_spec:
                click.echo()
                click.echo('Project Spec:')
                click.echo('---')
                
            # clear stage status, this will be details above
            if project_spec.resources:
                for stage in project_spec.resources.stages:
                    stage.status = None

            click.echo(yaml.dump(project_spec.model_dump(
                exclude_none=True, exclude_unset=True, by_alias=True, mode='json'
            )))
    else:
        click.echo(f"Project '{project_name}' does not have any revisions!")

    if isinstance(project, models.ErrorResponse):
        click.echo(f" {err} Could not describe project!")
        echoerr(project)
        sys.exit(1)

@update_group.command(name='project', help='Update Project parameters')
@click.argument('project_name', type=str)
@project_org_option
@project_user_option
@click.option('--description', help='Update project description', default=None, type=str)
@click.option('--active', help='Update project status', default=None, type=bool)
@click.pass_context
def update_project(ctx: click.Context, project_name: str, description: str, org: str, user:str, active: bool):
    client = DeployManagerClient(ctx)
    project = client.get_project(project_name, org=org, user=user)
    ops = []
    if isinstance(project, models.ProjectSchema):
        project.description = description
        if description:
            ops.append(models.JSONPatchOpSchema(
                op=models.Op('replace'),
                path='/description',
                value=description
            ))
        if active is not None:
            ops.append(models.JSONPatchOpSchema(
                op=models.Op('replace'),
                path='/active',
                value=active
            ))
        project = client.patch_project(project.name, ops)
        if isinstance(project, models.ProjectSchema):
            click.echo(f"Project '{project_name}' description updated!")

    if isinstance(project, models.ErrorResponse):
        click.echo(f" {err} Failed to update project description!")
        echoerr(project)
        sys.exit(1)
        

@allow_group.command(name='project')
@click.argument('project_name', type=str, required=True)
@click.argument('subject', type=str, required=True)
@project_org_option
@project_user_option
@click.option('-v','--view', help='Allow to see the project', default=None, type=bool, is_flag=True)
@click.option('-c','--change', help='Allow to edit the project, implies --view', default=None, type=bool, is_flag=True)
@click.option('-d','--delete', help='Allow delete project, implies --view and --change', default=None, type=bool, is_flag=True)
@click.pass_context
def allow_project(ctx: click.Context, project_name: str, org: str, user:str, view: bool, change: bool, delete: bool, subject: str):
    client = DeployManagerClient(ctx)
    response = client.get_project(project_name, org=org, user=user)
    if isinstance(response, models.ProjectSchema):
        permission = models.ProjectPermissionSchema(
            view=bool(view or change or delete),
            change=bool(change or delete),
            delete=bool(delete),
            subject=subject,
        )
        response = client.allow_project(response.name, permission)
        if isinstance(response, models.ConfirmationResponse):
            click.echo(f"{chk} Permissions for project '{project_name}' set successfully!")
            click.echo(f"{info} {response.detail}")
    if isinstance(response, models.ErrorResponse):
        click.echo(f" {err} Failed to grant permission to project!")
        echoerr(response)
        sys.exit(1)