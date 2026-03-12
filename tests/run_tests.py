#!/usr/bin/env python3
"""
Claude Telemetry Test Runner
Runs all modular test files and reports a summary.
Works across Windows, macOS, and Linux platforms.
"""

import os
import platform
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

# ANSI color codes — detect Windows Terminal (WT_SESSION) and ANSICON
_is_windows = sys.platform == "win32"
COLORS_ENABLED = not _is_windows or "ANSICON" in os.environ or "WT_SESSION" in os.environ

if _is_windows and not COLORS_ENABLED:
    # Try enabling VT processing on Windows 10+ via ctypes
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        COLORS_ENABLED = True
    except Exception:
        pass

if COLORS_ENABLED:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
else:
    GREEN = RED = YELLOW = BLUE = BOLD = RESET = ""


def print_header(text, char="="):
    """Print a formatted header."""
    width = 70
    print(f"\n{BOLD}{char * width}{RESET}")
    print(f"{BOLD}{text.center(width)}{RESET}")
    print(f"{BOLD}{char * width}{RESET}")


def print_section(text):
    """Print a section header."""
    print(f"\n{BLUE}{BOLD}>> {text}{RESET}")
    print("-" * 60)


def print_pass(text):
    """Print a pass message."""
    print(f"{GREEN}[PASS]{RESET} {text}")


def print_fail(text):
    """Print a fail message."""
    print(f"{RED}[FAIL]{RESET} {text}")


def print_warn(text):
    """Print a warning message."""
    print(f"{YELLOW}[WARN]{RESET} {text}")


def print_info(text):
    """Print an info message."""
    print(f"[INFO] {text}")


def get_system_info():
    """Get system information for diagnostics."""
    info = {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
    }

    # Get hostname safely
    try:
        info["hostname"] = platform.node()
    except Exception:
        info["hostname"] = "unknown"

    return info


def run_mongodb_tests():
    """Run MongoDB availability tests."""
    print_section("MongoDB Availability Tests")

    try:
        from tests.test_mongodb_integration import run_all_tests as run_mongodb

        results = run_mongodb()

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        for result in results:
            if result.passed:
                print_pass(f"{result.name}: {result.message}")
            else:
                print_fail(f"{result.name}: {result.message}")
                if result.details:
                    print(f"       Details: {result.details}")

        return {
            "module": "MongoDB",
            "passed": passed,
            "failed": failed,
            "total": len(results),
        }

    except ImportError as e:
        print_fail(f"Failed to import test_mongodb_integration: {e}")
        return {
            "module": "MongoDB",
            "passed": 0,
            "failed": 1,
            "total": 1,
            "error": str(e),
        }
    except Exception as e:
        print_fail(f"MongoDB tests crashed: {type(e).__name__}: {e}")
        return {
            "module": "MongoDB",
            "passed": 0,
            "failed": 1,
            "total": 1,
            "error": str(e),
        }


def print_summary(module_results):
    """Print the test summary."""
    print_header("TEST SUMMARY")

    total_passed = 0
    total_failed = 0
    total_tests = 0

    # Print per-module summary
    print(f"\n{'Module':<15} {'Passed':<10} {'Failed':<10} {'Total':<10} {'Status':<10}")
    print("-" * 55)

    for result in module_results:
        module = result["module"]
        passed = result["passed"]
        failed = result["failed"]
        total = result["total"]

        total_passed += passed
        total_failed += failed
        total_tests += total

        if failed == 0:
            status = f"{GREEN}OK{RESET}"
        else:
            status = f"{RED}FAILED{RESET}"

        print(f"{module:<15} {passed:<10} {failed:<10} {total:<10} {status}")

    print("-" * 55)
    print(f"{'TOTAL':<15} {total_passed:<10} {total_failed:<10} {total_tests:<10}")

    # Print overall status
    print("\n" + "=" * 70)
    if total_failed == 0:
        print(f"{GREEN}{BOLD}ALL TESTS PASSED{RESET}")
        print("=" * 70)
        return True
    else:
        print(f"{RED}{BOLD}SOME TESTS FAILED{RESET}")
        print("=" * 70)
        print_contact_info()
        return False


def print_contact_info():
    """Print contact information for support."""
    print(f"""
{YELLOW}{BOLD}========================================{RESET}
{YELLOW}{BOLD}        PLEASE CONTACT MANAGERS        {RESET}
{YELLOW}{BOLD}========================================{RESET}

If you are experiencing issues with the test suite, please contact
your project managers for assistance.

{BOLD}Common Issues:{RESET}
  - MongoDB connection failed: Check mongodb_url in config.json or MONGODB_URL env var
  - Missing packages: Run 'pip install -r requirements.txt'

{BOLD}Information to provide:{RESET}
  1. Full test output (copy/paste from terminal)
  2. Your operating system and version
  3. Python version (python --version)
  4. Contents of config.json (with passwords masked)

{BOLD}Manager Contact:{RESET}
  - Name:  Jingheng Ye
  - Email: jingheng.cs@example.com

{YELLOW}{BOLD}========================================{RESET}
""")


def main():
    """Main entry point."""
    print_header("CLAUDE TELEMETRY TEST SUITE", "=")
    print(f"\nTest run started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Print system information
    print_section("System Information")
    sys_info = get_system_info()
    for key, value in sys_info.items():
        print_info(f"{key}: {value}")

    # Run all test modules
    module_results = []

    # MongoDB tests
    mongodb_result = run_mongodb_tests()
    module_results.append(mongodb_result)

    # Print summary
    all_passed = print_summary(module_results)
    print(f"\nTest run completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
