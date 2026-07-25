import csv
import glob
import os

def combine_csv_files():
    """
    Find all CSV files in 'before', 'after', and current directories, 
    add filename as first column, and combine them into a single CSV file.
    """
    
    # Define folders to search
    folders_to_search = ['before', 'after', '.']  # '.' represents current directory
    csv_files = []
    
    # Search for CSV files in each folder
    for folder in folders_to_search:
        if folder == '.':
            folder_path = '.'
            search_pattern = "*.csv"
        else:
            folder_path = folder
            search_pattern = os.path.join(folder, "*.csv")
        
        # Check if folder exists (except current directory)
        if folder != '.' and not os.path.exists(folder_path):
            print(f"Warning: Folder '{folder}' does not exist, skipping...")
            continue
        
        # Find CSV files in this folder
        folder_csv_files = glob.glob(search_pattern)
        
        # Filter out input.csv files
        folder_csv_files = [f for f in folder_csv_files if os.path.basename(f).lower() != 'input.csv']
        
        if folder_csv_files:
            print(f"Found {len(folder_csv_files)} CSV files in '{folder}' folder: {folder_csv_files}")
            csv_files.extend(folder_csv_files)
        else:
            print(f"No CSV files found in '{folder}' folder")
    
    if not csv_files:
        print("No CSV files found in any of the specified directories (before, after, current).")
        return
    
    print(f"\nTotal CSV files found: {len(csv_files)}")
    
    all_rows = []
    header_written = False
    combined_header = None
    
    for csv_file in csv_files:
        try:
            # Get filename without extension and include folder info
            file_basename = os.path.basename(csv_file)
            filename_without_ext = os.path.splitext(file_basename)[0]
            
            # Get the folder name for identification
            folder_name = os.path.dirname(csv_file)
            if folder_name == '' or folder_name == '.':
                folder_name = 'current'
            
            # Create identifier: folder_filename
            file_identifier = f"{folder_name}_{filename_without_ext}"
            
            with open(csv_file, 'r', newline='', encoding='utf-8') as file:
                reader = csv.reader(file)
                rows = list(reader)
                
                if not rows:
                    print(f"Warning: {csv_file} is empty, skipping...")
                    continue
                
                # Process header
                if not header_written:
                    # First file - create combined header
                    original_header = rows[0]
                    combined_header = ['source_file'] + original_header
                    header_written = True
                
                # Process data rows
                for i, row in enumerate(rows):
                    if i == 0:  # Skip header row
                        continue
                    
                    # Add folder_filename as first column
                    new_row = [file_identifier] + row
                    all_rows.append(new_row)
                
                print(f"Processed: {csv_file} ({len(rows)-1} data rows)")
                
        except Exception as e:
            print(f"Error processing {csv_file}: {str(e)}")
            continue
    
    if all_rows and combined_header:
        # Write combined CSV file
        output_file = "combined.csv"
        
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                
                # Write header
                writer.writerow(combined_header)
                
                # Write all data rows
                writer.writerows(all_rows)
            
            print(f"\nSuccessfully combined CSV files into '{output_file}'")
            print(f"Total data rows in combined file: {len(all_rows)}")
            print(f"Columns: {combined_header}")
            
        except Exception as e:
            print(f"Error writing combined file: {str(e)}")
            
    else:
        print("No data was successfully processed.")

if __name__ == "__main__":
    combine_csv_files()