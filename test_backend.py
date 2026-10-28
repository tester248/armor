import os
import sys

# Switch to armor-backend directory and add to sys.path
backend_dir = os.path.join(os.path.dirname(__file__), "armor-backend")
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from test_backend import run_tests

if __name__ == "__main__":
    run_tests()
