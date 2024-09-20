
import click

from .models import ErrorResponse, ProjectSpec, SecretData

key = click.style(u"\U0001F511", fg='yellow')

watch = click.style("\u23F1", fg='white')

globe = click.style('\U0001F30D', fg='blue')

spin = click.style(u"\u21BB", fg='cyan')

err = click.style('\u2715', fg='red')

chk = click.style('\u2713', fg='green')

wrn = click.style('\u26A0', fg='yellow')

def format_route_status(status: str) -> str:
    if status == 'online':
        return click.style(status.upper(), fg='green')
    elif status == 'offline':
        return click.style(status.upper(), fg='black')
    elif status == 'pending':
        return click.style(status.upper(), fg='yellow')
    elif status == 'starting':
        return click.style(status.upper(), fg='cyan')
    elif status == 'error':
        return click.style(status.upper(), fg='red', bold=True)
    else:
        return status
    
def echoerr(error: ErrorResponse):
    if isinstance(error.detail, dict):
        for key, value in error.detail.items():
            click.echo(f" {wrn} {key}: {value}")
    elif isinstance(error.detail, list):
        for item in error.detail:
            click.echo(f" {wrn} {item}")
    elif isinstance(error.detail, str):
        click.echo(f" {wrn} {error.detail}")
    elif error.detail is None:
        click.echo(f" {wrn} No error message provided!")

def parse_secrets(secrets: list) -> list[dict]:
    parsed_secrets = []
    for secret in secrets:
        secret_name, secret_data = secret.split(':')
        secret_data = dict([s.split('=') for s in secret_data.split(',')])
        secret_dict = {'name': secret_name, 'data': secret_data}
        parsed_secrets.append(secret_dict)
    return parsed_secrets


def merge_secrets(project_spec: ProjectSpec, secrets: list[str]) -> ProjectSpec:
    for secret in parse_secrets(secrets):
        if project_spec.resources is not None:
            if secret['name'] not in [s.name for s in project_spec.resources.secrets]:
                raise Exception(f"Secret '{secret['name']}' not found in project spec!")
            for existing_secret in project_spec.resources.secrets:
                if existing_secret.name == secret['name']:
                    if isinstance(existing_secret.data, SecretData):
                        if existing_secret.data.root is None:
                            existing_secret.data.root = secret['data']
                        else:
                            existing_secret.data.root.update(secret['data'])
                    else:
                        existing_secret.data.update(secret['data'])
    return project_spec
