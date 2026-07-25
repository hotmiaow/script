# Secure Watermark Pro

A Python-based GUI application to add secure, customizable watermarks to PDFs and images. The application performs flattened rasterization (300 DPI) to ensure watermarks cannot be easily removed or extracted from the final document.

## Features
- **Intuitive UI**: Easy-to-use interface with real-time watermark preview.
- **Multiple Formats**: Supports both PDF documents and standard image formats.
- **Pre-defined Templates**: Built-in templates for Rental Applications, ID Copies, and Confidential Documents.
- **Highly Customizable**: Adjust text, alpha (transparency), size, and spacing of the watermark.
- **Secure Flattening**: Converts the final output into a 300 DPI rasterized PDF, preventing text/watermark extraction.
- **CLI Support**: Launch the app and automatically load a file by passing the path as an argument.

---

## Requirements & Installation

The error `Could not find import of reportlab.pdfgen` occurs because the required Python libraries are not installed in your environment. Follow these steps to install everything needed.

### 1. System Dependencies
The application requires `tkinter` for the GUI and `poppler-utils` for PDF rendering (required by `pdf2image`). On Ubuntu/Debian/GNOME systems, run:

```bash
sudo apt update
sudo apt install python3-tk poppler-utils
```

### 2. Python Dependencies
Install the required Python libraries using `pip`. Open your terminal and run:

```bash
pip install reportlab pypdf pdf2image Pillow
```

*(Note: If your system uses `pip3` or you are in a managed environment, you might need to run `python3 -m pip install reportlab pypdf pdf2image Pillow` or use a `venv`.)*

---

## Usage

### Standard Launch
You can launch the application by running the script:
```bash
python3 App_secure_watermark.py
```

### Command-Line Arguments
To automatically load a file when the application opens, pass the file path as an argument:
```bash
python3 App_secure_watermark.py /path/to/your/document.pdf
```

---

## GNOME Right-Click Menu Integration (Nautilus)

You can add Secure Watermark Pro directly to your GNOME right-click "Scripts" menu. This allows you to right-click any PDF or image and instantly open it in the application.

1. **Create the Nautilus Script File**
   Open your terminal and create an executable script in the GNOME specific directory:
   ```bash
   mkdir -p "$HOME/.local/share/nautilus/scripts"
   touch "$HOME/.local/share/nautilus/scripts/Add Secure Watermark"
   chmod +x "$HOME/.local/share/nautilus/scripts/Add Secure Watermark"
   ```

2. **Edit the Script**
   Open the file in a text editor (e.g., `nano` or `gedit`):
   ```bash
   gedit "$HOME/.local/share/nautilus/scripts/Add Secure Watermark"
   ```

3. **Paste the Code**
   Copy and paste the following bash script. It reliably extracts the selected file path and passes it to your Python app:
   ```bash
   #!/bin/bash
   
   # Absolute path to your Python script
   APP_PATH="/home/keith/OneDrive/script/watermark_adder/App_secure_watermark.py"
   
   # GNOME populates this variable with the selected file paths
   echo -e "$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS" | head -n 1 | while read file; do
       if [ -n "$file" ]; then
           # Launch the app with the selected file
           python3 "$APP_PATH" "$file"
       fi
   done
   ```

4. **Save and Test**
   Save the file and close the editor. Now, when you right-click any file in your GNOME File Manager (Nautilus), you can select **Scripts > Add Secure Watermark** to instantly launch the watermarker with that file loaded!
