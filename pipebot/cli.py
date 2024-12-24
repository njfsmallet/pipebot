import argparse
import os
import sys
from pipebot.config import AppConfig

class CLIParser:
    def __init__(self):
        self.app_config = AppConfig()
        self.parser = self._create_parser()

    def _create_parser(self):
        parser = argparse.ArgumentParser(
            description='AI assistant powered by AWS Bedrock',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""Examples:
              $ echo 'What is Docker?' | pb
              $ kubectl get ns | pb
              $ aws s3 ls | pb --no-memory""")

        mode_group = parser.add_argument_group('Mode options')
        mode_group.add_argument('--non-interactive', action='store_true', 
                               help='Stop after first response (default: interactive)')

        memory_group = parser.add_argument_group('Memory options')
        memory_group.add_argument('--no-memory', action='store_true',
                                help='Disable conversation memory')
        memory_group.add_argument('--clear', action='store_true',
                                help='Clear conversation memory and exit')

        debug_group = parser.add_argument_group('Debug options')
        debug_group.add_argument('--debug', action='store_true',
                                help='Enable debug mode')

        kb_group = parser.add_argument_group('Knowledge Base options')
        kb_group.add_argument('--scan', action='store_true',
                             help='Scan and index knowledge base documents')
        kb_group.add_argument('--status', action='store_true',
                             help='Show knowledge base status')

        return parser

    def parse_args(self):
        return self.parser.parse_args()

    def print_help(self):
        self.parser.print_help()

    def check_for_pipe(self):
        if os.isatty(sys.stdin.fileno()):
            self.print_help()
            sys.exit(0) 