"""Run foundation API tests on disposable, randomly named MySQL databases."""
import argparse
import getpass
import os
from pathlib import Path
import sys
import unittest
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=3306)
    parser.add_argument('--user', default='root')
    args = parser.parse_args()
    password = getpass.getpass('MySQL test-server password: ')
    os.environ['FOUNDATION_TEST_MYSQL_URL'] = URL.create('mysql+pymysql', username=args.user,
        password=password, host=args.host, port=args.port).render_as_string(hide_password=False)
    os.environ.setdefault('JWT_SECRET', 'foundation-tests-distinct-local-key-2026')
    sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'backend/tests')]
    from test_foundation import FoundationTests
    from test_models_knowledge import ModelsKnowledgeTests
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(FoundationTests),
                              unittest.defaultTestLoader.loadTestsFromTestCase(ModelsKnowledgeTests)])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
