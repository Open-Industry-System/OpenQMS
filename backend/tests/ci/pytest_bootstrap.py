"""Supported pytest child entry point: isolate before importing pytest/app."""
import sys

from tests.ci.python_isolation import bootstrap


def main():
    bootstrap()
    import pytest

    return pytest.main(sys.argv[1:])


if __name__ == '__main__':
    raise SystemExit(main())
