import os
import sys

backend_dir = os.path.join(os.path.dirname(__file__), "armor-backend")
if os.path.exists(backend_dir):
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

from test_roboflow import main

if __name__ == "__main__":
    main()
