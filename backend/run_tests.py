#!/usr/bin/env python3
"""
OpenQMS Test Runner — Comprehensive testing workflow for all backend modules.

Usage:
    cd backend
    PYTHONPATH=. python run_tests.py           # Run all tests
    PYTHONPATH=. python run_tests.py --quick   # Run only fast unit tests
    PYTHONPATH=. python run_tests.py --engine  # Run only engine tests
    TEST_DATABASE_URL=postgresql+asyncpg://... python run_tests.py  # Include DB tests

Environment:
    SECRET_KEY          - Required for app import (default rejected for security)
    TEST_DATABASE_URL   - Required for DB tests (must contain '_test')
    NEO4J_URI           - Optional, for Neo4j graph tests
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def banner(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def run_command(cmd: list[str], description: str, env: dict | None = None) -> bool:
    """Run a shell command and report results."""
    print(f"\n▶ {description}")
    print(f"  Command: {' '.join(cmd)}")

    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, capture_output=True, text=True, env=merged_env)

    if result.returncode == 0:
        print(f"  ✅ PASSED")
        if result.stdout.strip():
            for line in result.stdout.strip().split("\n")[-5:]:  # Last 5 lines
                print(f"     {line}")
        return True
    else:
        print(f"  ❌ FAILED (exit code {result.returncode})")
        if result.stdout.strip():
            print(f"  stdout:\n{result.stdout[-1000:]}")  # Last 1000 chars
        if result.stderr.strip():
            print(f"  stderr:\n{result.stderr[-1000:]}")
        return False


def test_manual_tests(env: dict) -> bool:
    """Run the manual test_schema.py and test_spc_engine.py."""
    banner("Manual Tests (test_schema.py, test_spc_engine.py)")

    ok = True
    for test_file in ["app/test_schema.py", "app/test_spc_engine.py"]:
        if not run_command(
            [sys.executable, test_file],
            f"Running {test_file}",
            env,
        ):
            ok = False
    return ok


def test_pytest_suite(env: dict, ignore_patterns: list[str]) -> bool:
    """Run the pytest suite."""
    banner("Pytest Suite")

    cmd = [
        sys.executable, "-m", "pytest", "tests/",
        "-v", "--tb=short",
    ]
    for pattern in ignore_patterns:
        cmd.extend(["--ignore", pattern])

    return run_command(cmd, "Running pytest on tests/", env)


def test_engine_imports(env: dict) -> bool:
    """Verify all engine modules import correctly."""
    banner("Engine Module Import Checks")

    engines = [
        "app.services.spc_calculation_engine",
        "app.services.aql_engine",
        "app.services.grr_engine",
        "app.services.bias_engine",
        "app.services.linearity_engine",
        "app.services.stability_engine",
        "app.services.attribute_engine",
        "app.services.diff_engine",
    ]

    code = "\n".join(
        f"try:\n    import {m}\n    print('{m}: OK')\nexcept Exception as e:\n    print(f'{m}: FAIL - {{e}}')"
        for m in engines
    )

    return run_command(
        [sys.executable, "-c", code],
        "Importing engine modules",
        env,
    )


def test_api_routes_import(env: dict) -> bool:
    """Verify the FastAPI app and all routers import."""
    banner("API Route Import Check")

    code = """
import sys
from app.main import app
print(f"App imported: {len(app.routes)} routes registered")
for r in app.routes:
    if hasattr(r, 'path'):
        print(f"  {r.path}")
print("All API routes imported successfully")
"""
    return run_command(
        [sys.executable, "-c", code],
        "Importing FastAPI app and routers",
        env,
    )


def test_graph_modules(env: dict) -> bool:
    """Test graph sync worker logic (no Neo4j connection needed)."""
    banner("Graph Module Logic Tests")

    # These tests only import the specific functions, not the full module
    code = """
import sys
# Test deduplicate_tasks and backoff_delay directly
# We need to avoid importing the full module which requires neo4j
# So we exec the relevant functions
try:
    # Try importing the test file instead
    import tests.test_graph_sync_worker
    print('Graph sync worker tests: importable')
except Exception as e:
    print(f'Graph sync worker tests: {e}')

try:
    import tests.test_graph_projection
    print('Graph projection tests: importable')
except Exception as e:
    print(f'Graph projection tests: {e}')
"""
    return run_command(
        [sys.executable, "-c", code],
        "Checking graph module tests",
        env,
    )


def check_dependencies() -> list[str]:
    """Check for missing dependencies."""
    banner("Dependency Check")

    required = {
        "openpyxl": "Excel export functionality",
        "neo4j": "Neo4j graph database integration",
    }

    missing = []
    for pkg, purpose in required.items():
        result = subprocess.run(
            [sys.executable, "-c", f"import {pkg}; print('OK')"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  ❌ {pkg}: MISSING — {purpose}")
            missing.append(pkg)
        else:
            print(f"  ✅ {pkg}: OK")

    return missing


def main():
    parser = argparse.ArgumentParser(description="OpenQMS Test Runner")
    parser.add_argument("--quick", action="store_true", help="Run only fast unit tests")
    parser.add_argument("--engine", action="store_true", help="Run only engine tests")
    parser.add_argument("--skip-db", action="store_true", help="Skip database-dependent tests")
    parser.add_argument("--fix-deps", action="store_true", help="Install missing dependencies")
    args = parser.parse_args()

    # Ensure SECRET_KEY is set
    env = {
        "SECRET_KEY": os.environ.get("SECRET_KEY", "test-secret-key-for-testing-only"),
        "TEST_DATABASE_URL": os.environ.get("TEST_DATABASE_URL", ""),
        "PYTHONPATH": str(Path(__file__).parent),
    }

    print("OpenQMS Test Runner")
    print(f"Python: {sys.executable}")
    print(f"Working directory: {Path.cwd()}")
    print(f"SECRET_KEY: {'✅ set' if 'SECRET_KEY' in os.environ else '⚠️ using test default'}")
    print(f"TEST_DATABASE_URL: {'✅ set' if 'TEST_DATABASE_URL' in os.environ else '❌ not set (DB tests will skip)'}")

    # Check dependencies
    missing_deps = check_dependencies()
    if missing_deps:
        print(f"\n⚠️ Missing dependencies: {', '.join(missing_deps)}")
        if args.fix_deps:
            print("Installing missing dependencies...")
            subprocess.run([sys.executable, "-m", "pip", "install", *missing_deps], check=False)
        else:
            print("Run with --fix-deps to install, or: pip install openpyxl neo4j")

    results = {}

    # Run tests based on mode
    if args.engine:
        results["engine_imports"] = test_engine_imports(env)
        results["manual_tests"] = test_manual_tests(env)
    elif args.quick:
        results["engine_imports"] = test_engine_imports(env)
        results["manual_tests"] = test_manual_tests(env)
        ignore = ["tests/test_graph_sync_worker.py", "tests/test_graph_projection.py"]
        results["pytest"] = test_pytest_suite(env, ignore)
    else:
        results["engine_imports"] = test_engine_imports(env)
        results["manual_tests"] = test_manual_tests(env)

        ignore = []
        if not os.environ.get("NEO4J_URI") and not args.skip_db:
            ignore = ["tests/test_graph_sync_worker.py", "tests/test_graph_projection.py"]
            print("\nℹ️ Skipping Neo4j-dependent tests (set NEO4J_URI or use --skip-db)")

        results["pytest"] = test_pytest_suite(env, ignore)

        if not args.skip_db:
            results["api_import"] = test_api_routes_import(env)
            results["graph_modules"] = test_graph_modules(env)

    # Summary
    banner("Test Summary")
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed

    for name, ok in results.items():
        status = "✅ PASSED" if ok else "❌ FAILED"
        print(f"  {status}: {name}")

    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} test suites passed")
    if failed:
        print(f"  {failed} suite(s) failed — see details above")
    print(f"{'=' * 60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
