from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python_scripts.server import run
from python_scripts.service import ProxyService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='free-proxy Python backend')
    sub = parser.add_subparsers(dest='command', required=True)

    serve_cmd = sub.add_parser('serve', help='start HTTP backend')
    serve_cmd.add_argument('--debug', action='store_true')

    list_cmd = sub.add_parser('models', help='list provider models')
    list_cmd.add_argument('--provider', required=True)

    probe_cmd = sub.add_parser('probe', help='probe provider model')
    probe_cmd.add_argument('--provider', required=True)
    probe_cmd.add_argument('--model', required=True)

    providers_cmd = sub.add_parser('providers', help='show configured providers')
    providers_cmd.add_argument('--json', action='store_true')

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = ProxyService()

    if args.command == 'serve':
        run(debug=bool(getattr(args, 'debug', False)))
        return 0

    if args.command == 'providers':
        providers = service.available_providers()
        if args.json:
            print(json.dumps({'providers': providers}, ensure_ascii=False, indent=2))
        else:
            print('\n'.join(providers) if providers else 'no providers configured')
        return 0

    if args.command == 'models':
        print(json.dumps({'provider': args.provider, 'models': service.list_models(args.provider)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == 'probe':
        result = service.probe(args.provider, args.model)
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
        return 0 if result.ok else 1

    return 1


if __name__ == '__main__':
    sys.exit(main())
