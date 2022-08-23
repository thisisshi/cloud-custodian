import click

from c7n_kube.server import init


PORT = '8800'
HOST = '0.0.0.0'


@click.group()
def cli():
    """
    Cloud Custodian Admission Controller
    """


@cli.command()
@click.option('--port')
@click.option('--policy-dir')
def serve(port, policy_dir):
    """
    Serve Cloud Custodian Admission Controller
    """
    port = port or PORT
    init(int(port), policy_dir)


if __name__ == '__main__':
    cli()
