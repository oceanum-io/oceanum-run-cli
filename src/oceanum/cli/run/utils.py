
import click

from .models import ErrorResponse, ProjectSpec, SecretData

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
    

def project_status_color(status: str) -> str:
    if status == 'ready':
        return click.style(status.upper(), fg='green')
    elif status == 'degraded':
        return click.style(status.upper(), fg='yellow')
    elif status == 'updating':
        return click.style(status.upper(), fg='cyan')
    elif status == 'error':
        return click.style(status.upper(), fg='red')
    else:
        return click.style(status.upper(), fg='white')
        
def stage_status_color(stage: dict) -> str:
    if stage['status'] == 'healthy':
        return click.style(stage['name'], fg='green')
    elif stage['status'] == 'degraded':
        return click.style(stage['name'], fg='yellow')
    elif stage['status'] == 'error':
        return click.style(stage['name'], fg='red')
    elif stage['status'] == 'updating':
        return click.style(stage['name'], fg='cyan')
    else:
        return stage['name']


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
