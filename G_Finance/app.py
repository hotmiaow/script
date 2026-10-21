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

if __name__ == "__main__":
    print("=======================================================")
    print("   Google Finance Portfolio & Financial Calculator    ")
    print("=======================================================")
    try:
        import ui
        if hasattr(ui, "View"):
            print("Detected Pythonista 3 on iOS. Launching native UIKit ui module interface...")
            import pythonista_native_ui
            pythonista_native_ui.main()
            sys.exit(0)
    except ImportError:
        pass

    try:
        from main_gui import launch_app
        launch_app()
    except (ImportError, ModuleNotFoundError) as e:
        if "tkinter" in str(e).lower() or "_tkinter" in str(e).lower():
            print("Tkinter desktop GUI is not available on this platform (e.g. iOS / Pythonista).")
            print("Launching G_Finance webview interface...")
            import webview
            webview.main()
        else:
            import traceback
            traceback.print_exc()
            os._exit(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        os._exit(1)
    finally:
        os._exit(0)
