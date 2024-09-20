
from oceanum.cli.main import main

@main.group(name='run', help='Oceanum Run Projects Management')
def run_group():
    pass

@run_group.group(name='list', help='List DPM resources')
def list_group():
    pass

@run_group.group(name='describe',help='Describe DPM resources')
def describe_group():
    pass

@run_group.group(name='delete', help='Delete DPM resources')
def delete():
    pass

@run_group.group(name='update',help='Update DPM resources')
def update_group():
    pass