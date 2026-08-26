import os
from PIL import Image

def convert_webp_to_png(root_dir):
    """
    Converts all WebP images in the specified directory and subdirectories to PNG format.
    Handles folders and filenames with spaces correctly.
    
    Args:
        root_dir (str): The root directory to search for WebP files
    """
    converted_count = 0
    failed_count = 0
    total_dirs = 0
    
    print(f"Starting conversion in: {os.path.abspath(root_dir)}")
    print("-" * 50)
    
    for subdir, dirs, files in os.walk(root_dir):
        total_dirs += 1
        print(f'Scanning directory: "{subdir}"')
        
        webp_files = [f for f in files if f.lower().endswith('.webp')]
        if webp_files:
            print(f'  Found {len(webp_files)} WebP file(s)')
        
        for file in webp_files:
            webp_path = os.path.join(subdir, file)
            png_path = os.path.splitext(webp_path)[0] + '.png'
            
            # Check if file exists and is readable
            if not os.path.exists(webp_path):
                print(f'  ✗ File not found: {webp_path}')
                failed_count += 1
                continue
                
            if not os.access(webp_path, os.R_OK):
                print(f'  ✗ File not readable: {webp_path}')
                failed_count += 1
                continue
            
            try:
                with Image.open(webp_path) as img:
                    # Ensure output directory exists
                    output_dir = os.path.dirname(png_path)
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    
                    img.save(png_path, 'PNG')
                print(f'  ✓ Converted: "{os.path.basename(webp_path)}" -> "{os.path.basename(png_path)}"')
                converted_count += 1
                
            except FileNotFoundError as e:
                print(f'  ✗ File not found during conversion: {webp_path}')
                print(f'    Error: {e}')
                failed_count += 1
            except PermissionError as e:
                print(f'  ✗ Permission denied: {webp_path}')
                print(f'    Error: {e}')
                failed_count += 1
            except Exception as e:
                print(f'  ✗ Failed to convert: {webp_path}')
                print(f'    Error: {e}')
                failed_count += 1
    
    print("-" * 50)
    print(f'Conversion complete!')
    print(f'Directories scanned: {total_dirs}')
    print(f'Successfully converted: {converted_count} files')
    if failed_count > 0:
        print(f'Failed conversions: {failed_count} files')

def main():
    try:
        # Convert all WebP files in current directory and subdirectories
        current_directory = '.'
        convert_webp_to_png(current_directory)
    except KeyboardInterrupt:
        print("\nConversion interrupted by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
