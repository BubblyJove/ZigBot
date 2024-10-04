import os
from datetime import datetime

def explore_directory(directory, output_file, indent=""):
    try:
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(f"{indent}Directory: {directory}\n")
            
            for item in sorted(os.listdir(directory)):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    size = os.path.getsize(item_path)
                    modified_time = os.path.getmtime(item_path)
                    modified_time_str = datetime.fromtimestamp(modified_time).strftime('%Y-%m-%d %H:%M:%S')
                    f.write(f"{indent}  - File: {item} (Size: {size} bytes, Modified: {modified_time_str})\n")
                elif os.path.isdir(item_path):
                    f.write(f"{indent}  + Subdirectory: {item}\n")
                    explore_directory(item_path, output_file, indent + "    ")
    except PermissionError:
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(f"{indent}  ! Permission denied for: {directory}\n")
    except Exception as e:
        with open(output_file, 'a', encoding='utf-8') as f:
            f.write(f"{indent}  ! Error exploring {directory}: {str(e)}\n")

def main():
    current_directory = os.getcwd()
    output_file = "directory_structure.txt"
    
    # Clear the output file if it exists
    open(output_file, 'w').close()
    
    with open(output_file, 'a', encoding='utf-8') as f:
        f.write(f"Directory Structure Report\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Root Directory: {current_directory}\n\n")
    
    explore_directory(current_directory, output_file)
    
    print(f"Directory structure has been written to {output_file}")

if __name__ == "__main__":
    main()
