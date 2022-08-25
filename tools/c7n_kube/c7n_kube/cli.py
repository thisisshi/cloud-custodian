import argparse
import logging

from c7n_kube.server import init

log = logging.getLogger('custodian.k8s.cli')
logging.basicConfig(
    # TODO: make this configurable
    level=logging.INFO,
    format="%(asctime)s: %(name)s:%(levelname)s %(message)s")


PORT = '8800'
HOST = '0.0.0.0'


def cli():
    """
    Cloud Custodian Admission Controller
    """

    parser = argparse.ArgumentParser(description='Cloud Custodian Admission Controller')
    parser.add_argument('--port', type=int, help='Server port', nargs='?', default=PORT)
    parser.add_argument('--policy-dir', type=str, required=True, help='policy directory')
    args = parser.parse_args()
    init(args.port, args.policy_dir)


if __name__ == '__main__':
    cli()
