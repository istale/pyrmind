#!/usr/bin/env python3
"""
Split CSV and Run Pyrmind Helper

This script helps you:
1. Split a large CSV file into smaller files based on:
   - A column value (e.g., region)
   - A fixed number of folders (rows distributed evenly)
   - A fixed number of rows per folder
2. Create a folder for each split
3. Optionally start pyrmind to process all folders in parallel

Usage:
    python split_and_run.py
    python split_and_run.py --csv data.csv --column region
    python split_and_run.py --csv data.csv --num-folders 10
    python split_and_run.py --csv data.csv --rows-per-folder 1000
"""

import csv
import os
import sys
import shutil
import subprocess
import argparse
import math


def find_csv_files():
    """Find CSV files in current directory."""
    csv_files = [f for f in os.listdir('.') if f.endswith('.csv') and os.path.isfile(f)]
    return csv_files


def select_csv_file():
    """Let user select a CSV file to process."""
    csv_files = find_csv_files()
    
    if not csv_files:
        print("No CSV files found in current directory.")
        print("Please run this script from the directory containing your CSV file.")
        sys.exit(1)
    
    if len(csv_files) == 1:
        print(f"Found: {csv_files[0]}")
        return csv_files[0]
    
    print("\nAvailable CSV files:")
    for i, f in enumerate(csv_files, 1):
        print(f"  {i}. {f}")
    
    while True:
        choice = input("\nSelect file number (or enter path): ").strip()
        if not choice:
            continue
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(csv_files):
                return csv_files[idx]
            print(f"Please enter 1-{len(csv_files)}")
            continue
        
        if os.path.isfile(choice):
            return choice
        
        print(f"File not found: {choice}")


def select_split_mode():
    """Let user select how to split the CSV."""
    print("\n" + "=" * 50)
    print("SPLIT MODE")
    print("=" * 50)
    print("""
1. BY COLUMN VALUE
   Split by unique values in a column (e.g., region=asia, europe, ...)
   → Each unique value gets its own folder

2. BY NUMBER OF FOLDERS
   Distribute rows evenly across N folders
   → 10000 rows / 5 folders = 2000 rows per folder

3. BY ROWS PER FOLDER
   Put N rows in each folder, create as many folders as needed
   → 1000 rows/folder from 10000 rows = 10 folders

4. CUSTOM GROUPS (advanced)
   Provide specific row ranges or conditions
""")
    
    while True:
        choice = input("Select mode (1/2/3/4) [1]: ").strip() or "1"
        if choice in ('1', '2', '3', '4'):
            return choice
        print("Please enter 1, 2, 3, or 4")


def select_split_column(csv_path):
    """Let user select which column to split by."""
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames
    
    if not columns:
        print("Could not read CSV headers.")
        sys.exit(1)
    
    if len(columns) == 1:
        print(f"Only one column found: {columns[0]}")
        return columns[0]
    
    print("\nAvailable columns:")
    for i, col in enumerate(columns, 1):
        print(f"  {i}. {col}")
    
    while True:
        choice = input("\nSelect column number to split by (or enter column name): ").strip()
        if not choice:
            continue
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(columns):
                return columns[idx]
            print(f"Please enter 1-{len(columns)}")
            continue
        
        if choice in columns:
            return choice
        
        print(f"Column not found: {choice}")


def select_num_folders():
    """Ask user how many folders to create."""
    while True:
        choice = input("\nNumber of folders to create: ").strip()
        if not choice:
            continue
        try:
            num = int(choice)
            if num > 0:
                return num
            print("Please enter a positive number")
        except ValueError:
            print("Please enter a valid number")


def select_rows_per_folder():
    """Ask user how many rows per folder."""
    while True:
        choice = input("\nNumber of rows per folder: ").strip()
        if not choice:
            continue
        try:
            num = int(choice)
            if num > 0:
                return num
            print("Please enter a positive number")
        except ValueError:
            print("Please enter a valid number")


def select_output_base():
    """Let user specify or confirm output base directory."""
    default = "processed"
    
    choice = input(f"\nOutput directory name [{default}]: ").strip()
    return choice if choice else default


def select_mode():
    """Let user choose between interactive and direct mode."""
    print("\n" + "=" * 50)
    print("EXECUTION MODE")
    print("=" * 50)
    print("""
1. INTERACTIVE MODE
   - Split CSV into folders
   - WAIT for you to press Enter
   - You can check folder contents in another terminal
   - Then press Enter to start processing

2. DIRECT MODE  
   - Split CSV into folders
   - START pyrmind immediately
   - Monitor with 'pyrmind attach' in another terminal

3. SPLIT ONLY
   - Just split the CSV
   - Don't start pyrmind
   - You run it manually later
""")
    
    while True:
        choice = input("Select mode (1/2/3) [1]: ").strip() or "1"
        if choice in ('1', '2', '3'):
            return choice
        print("Please enter 1, 2, or 3")


def split_by_column(csv_path, split_column, output_base):
    """Split CSV into folders based on column value."""
    print(f"\nReading {csv_path}...")
    
    groups = {}
    total_rows = 0
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        
        for row in reader:
            key = row.get(split_column, '').strip()
            if not key:
                key = '_empty_'
            
            safe_key = "".join(c for c in key if c.isalnum() or c in ('_', '-', ' ')).strip()
            safe_key = safe_key.replace(' ', '_')
            
            if safe_key not in groups:
                groups[safe_key] = []
            groups[safe_key].append(row)
            total_rows += 1
    
    print(f"Found {len(groups)} unique values in column '{split_column}'")
    print(f"Total rows: {total_rows}")
    
    os.makedirs(output_base, exist_ok=True)
    
    created_folders = []
    
    for key, rows in sorted(groups.items()):
        folder_path = os.path.join(output_base, key)
        os.makedirs(folder_path, exist_ok=True)
        
        output_csv = os.path.join(folder_path, os.path.basename(csv_path))
        
        with open(output_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        created_folders.append((key, folder_path, len(rows)))
        print(f"  Created: {key}/ ({len(rows)} rows)")
    
    return created_folders, fieldnames


def split_by_num_folders(csv_path, num_folders, output_base):
    """Split CSV evenly into N folders."""
    print(f"\nReading {csv_path}...")
    
    rows = []
    fieldnames = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        
        for row in reader:
            rows.append(row)
    
    total_rows = len(rows)
    rows_per_folder = math.ceil(total_rows / num_folders)
    
    print(f"Total rows: {total_rows}")
    print(f"Splitting into {num_folders} folders (~{rows_per_folder} rows each)")
    
    os.makedirs(output_base, exist_ok=True)
    
    created_folders = []
    
    for i in range(num_folders):
        start_idx = i * rows_per_folder
        end_idx = min(start_idx + rows_per_folder, total_rows)
        folder_rows = rows[start_idx:end_idx]
        
        if not folder_rows:
            continue
        
        folder_name = f"part_{i+1:03d}"
        folder_path = os.path.join(output_base, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        
        output_csv = os.path.join(folder_path, os.path.basename(csv_path))
        
        with open(output_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(folder_rows)
        
        created_folders.append((folder_name, folder_path, len(folder_rows)))
        print(f"  Created: {folder_name}/ ({len(folder_rows)} rows)")
    
    return created_folders, fieldnames


def split_by_rows_per_folder(csv_path, rows_per_folder, output_base):
    """Split CSV with N rows per folder."""
    print(f"\nReading {csv_path}...")
    
    rows = []
    fieldnames = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        
        for row in reader:
            rows.append(row)
    
    total_rows = len(rows)
    num_folders = math.ceil(total_rows / rows_per_folder)
    
    print(f"Total rows: {total_rows}")
    print(f"Rows per folder: {rows_per_folder}")
    print(f"Will create {num_folders} folders")
    
    os.makedirs(output_base, exist_ok=True)
    
    created_folders = []
    
    for i in range(num_folders):
        start_idx = i * rows_per_folder
        end_idx = min(start_idx + rows_per_folder, total_rows)
        folder_rows = rows[start_idx:end_idx]
        
        if not folder_rows:
            continue
        
        folder_name = f"part_{i+1:03d}"
        folder_path = os.path.join(output_base, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        
        output_csv = os.path.join(folder_path, os.path.basename(csv_path))
        
        with open(output_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(folder_rows)
        
        created_folders.append((folder_name, folder_path, len(folder_rows)))
        print(f"  Created: {folder_name}/ ({len(folder_rows)} rows)")
    
    return created_folders, fieldnames


def create_processor_script(base_path, csv_filename):
    """Create the processor.py script in each folder."""
    processor_content = f'''#!/usr/bin/env python3
"""CSV Processor - auto-generated by split_and_run.py"""

import csv
import os
import sys

def process_file(input_path):
    """Process the CSV file."""
    folder = os.path.dirname(input_path) or '.'
    name = os.path.basename(folder)
    processed = 0
    errors = 0
    
    output_path = os.path.join(folder, 'processed.csv')
    
    print(f"[{{name}}] Starting processing...")
    print(f"[{{name}}] Input: {{input_path}}")
    
    if not os.path.exists(input_path):
        print(f"[{{name}}] Error: {{input_path}} not found!")
        sys.exit(1)
    
    with open(input_path, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        
        with open(output_path, 'w', encoding='utf-8', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
            writer.writeheader()
            
            for row in reader:
                # TODO: Add your processing logic here
                # Example: transform data, validate, aggregate, etc.
                
                processed += 1
                
                if processed % 100 == 0:
                    print(f"[{{name}}] Processed {{processed}} rows...")
                
                writer.writerow(row)
    
    print(f"[{{name}}] Done! Processed: {{processed}}, Errors: {{errors}}")

if __name__ == '__main__':
    folder = sys.argv[1] if len(sys.argv) > 1 else '.'
    input_file = os.path.join(folder, '{csv_filename}')
    process_file(input_file)
'''
    
    processor_path = os.path.join(base_path, 'processor.py')
    with open(processor_path, 'w', encoding='utf-8') as f:
        f.write(processor_content)
    os.chmod(processor_path, 0o755)


def create_procfile(base_path):
    """Create Procfile in the folder."""
    procfile_content = "process: python processor.py .\n"
    procfile_path = os.path.join(base_path, 'Procfile')
    with open(procfile_path, 'w') as f:
        f.write(procfile_content)


def create_master_procfile(output_base, folders):
    """Create a master Procfile that runs all processes."""
    procfile_content = ""
    for folder_name, folder_path, row_count in folders:
        procfile_content += f"{folder_name}: python processor.py .\n"
    
    procfile_path = os.path.join(output_base, 'Procfile')
    with open(procfile_path, 'w') as f:
        f.write(procfile_content)
    
    return procfile_path


def wait_for_user():
    """Wait for user to press Enter."""
    input("\n" + "=" * 50)
    input("Split complete! Press ENTER when ready to start processing...")
    input("(You can check folder contents in another terminal)")
    input("=" * 50 + "\n")


def start_pyrmind(procfile_path):
    """Start pyrmind with the Procfile."""
    print(f"\nStarting pyrmind with {procfile_path}...")
    print("Use 'pyrmind attach' in another terminal to monitor progress")
    print("Use 'pyrmind status' to check individual process status")
    print("-" * 50)
    
    os.chdir(os.path.dirname(procfile_path) or '.')
    
    try:
        subprocess.run(['pyrmind', 'start', '-f', os.path.basename(procfile_path), '--auto-restart'])
    except KeyboardInterrupt:
        print("\nInterrupted. Use 'pyrmind kill' to stop all processes.")


def main():
    parser = argparse.ArgumentParser(
        description='Split CSV and optionally run pyrmind to process in parallel'
    )
    parser.add_argument('--csv', help='Path to CSV file')
    parser.add_argument('--column', help='Column name to split by')
    parser.add_argument('--num-folders', type=int, help='Split into N folders (rows distributed evenly)')
    parser.add_argument('--rows-per-folder', type=int, help='Number of rows per folder')
    parser.add_argument('--output', default='processed', help='Output directory')
    parser.add_argument('--mode', choices=['1', '2', '3'], 
                       help='Mode: 1=interactive, 2=direct, 3=split only')
    args = parser.parse_args()
    
    # Get CSV file
    if args.csv and os.path.isfile(args.csv):
        csv_path = args.csv
    else:
        csv_path = select_csv_file()
    
    # Determine split mode
    split_mode = None
    split_column = None
    num_folders = None
    rows_per_folder = None
    
    if args.num_folders:
        split_mode = '2'
        num_folders = args.num_folders
    elif args.rows_per_folder:
        split_mode = '3'
        rows_per_folder = args.rows_per_folder
    elif args.column:
        split_mode = '1'
        split_column = args.column
    else:
        split_mode = select_split_mode()
    
    # Get output directory
    output_base = args.output if args.output else select_output_base()
    
    # Get mode
    if args.mode:
        mode = args.mode
    else:
        mode = select_mode()
    
    # Split CSV based on mode
    print(f"\nSplitting {csv_path}...")
    
    if split_mode == '1':
        if not split_column:
            split_column = select_split_column(csv_path)
        print(f"Split mode: by column '{split_column}'")
        folders, fieldnames = split_by_column(csv_path, split_column, output_base)
    
    elif split_mode == '2':
        if not num_folders:
            num_folders = select_num_folders()
        print(f"Split mode: by {num_folders} folders (evenly distributed)")
        folders, fieldnames = split_by_num_folders(csv_path, num_folders, output_base)
    
    elif split_mode == '3':
        if not rows_per_folder:
            rows_per_folder = select_rows_per_folder()
        print(f"Split mode: {rows_per_folder} rows per folder")
        folders, fieldnames = split_by_rows_per_folder(csv_path, rows_per_folder, output_base)
    
    csv_filename = os.path.basename(csv_path)
    
    # Create processor.py and Procfile in each folder
    print("\nCreating Procfile and processor.py in each folder...")
    for folder_name, folder_path, row_count in folders:
        create_processor_script(folder_path, csv_filename)
        create_procfile(folder_path)
        print(f"  {folder_name}/ Procfile, processor.py")
    
    # Create master Procfile
    master_procfile = create_master_procfile(output_base, folders)
    print(f"\nCreated master Procfile: {master_procfile}")
    
    # Summary
    total_rows = sum(count for _, _, count in folders)
    print("\n" + "=" * 50)
    print("SPLIT COMPLETE")
    print("=" * 50)
    print(f"Folders created: {len(folders)}")
    print(f"Total rows: {total_rows}")
    print(f"Output directory: {os.path.abspath(output_base)}")
    
    # Handle based on mode
    if mode == '1':
        wait_for_user()
        start_pyrmind(master_procfile)
    
    elif mode == '2':
        print("\nStarting pyrmind immediately...")
        start_pyrmind(master_procfile)
    
    else:
        print("\nTo start processing:")
        print(f"  cd {output_base}")
        print("  pyrmind start -f Procfile --auto-restart")
        print("\nTo monitor:")
        print("  pyrmind attach")


if __name__ == '__main__':
    main()
