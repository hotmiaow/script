#!/usr/bin/env python3
"""
Launcher script for Google Finance Portfolio & Financial Calculator.
Usage:
    python3 app.py
"""

import os
import sys

# Ensure current directory is in path and working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
try:
    os.chdir(BASE_DIR)
except Exception:
    pass

from main_gui import launch_app

if __name__ == "__main__":
    print("=======================================================")
    print("   Google Finance Portfolio & Financial Calculator    ")
    print("=======================================================")
    try:
        launch_app()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        os._exit(0)
