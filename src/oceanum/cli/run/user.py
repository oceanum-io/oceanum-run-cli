import sys

import click

from oceanum.cli.common.renderer import Renderer, RenderField
from oceanum.cli.common.symbols import err
from oceanum.cli.auth import login_required

from . import models
from .main import describe_group
from .client import DeployManagerClient

from .utils import echoerr

@describe_group.command(name='user', help='List DPM Users')
@click.pass_context
@login_required
def describe_user(ctx: click.Context):
    client = DeployManagerClient(ctx)
    fields = [
        RenderField(label='Username', path='$.username'),
        RenderField(label='Email', path='$.email'),
        RenderField(label='Current Org', path='$.current_org.name'),
        RenderField(label='DPM API Token', path='$.token'),
        RenderField(
            label='User Resources', 
            path='$.resources.*', 
            mod=lambda x: f"{x['resource_type'].removesuffix('s')}: {x['name']}"),
    ]
    users = client.get_users()
    if isinstance(users, models.ErrorResponse):
        click.echo(f"{err} Error fetching users:")
        echoerr(users)
        return 1
    else:
        click.echo(Renderer(data=users, fields=fields).render(output_format='plain'))