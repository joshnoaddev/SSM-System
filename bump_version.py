import re
from pathlib import Path

FILE_PATH = Path("office_app/services/updater_service.py")

def bump():
    print("--- SSM Version Bumper ---")
    if not FILE_PATH.exists():
        print(f"Error: Could not find {FILE_PATH}")
        return

    with open(FILE_PATH, "r", encoding="utf-8") as file:
        content = file.read()

    # Search for the CURRENT_VERSION = "x.y.z" line
    match = re.search(r'CURRENT_VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"', content)
    if not match:
        print("Error: Could not find CURRENT_VERSION variable in the file.")
        return

    major, minor, patch = match.groups()
    
    # Increase the last number by 1
    new_patch = int(patch) + 1
    new_version = f"{major}.{minor}.{new_patch}"
    
    # Replace it in the text
    new_content = content[:match.start(1)] + new_version + content[match.end(3):]

    # Save the file back
    with open(FILE_PATH, "w", encoding="utf-8") as file:
        file.write(new_content)

    print(f"✅ Code updated successfully! New version is: {new_version}")

if __name__ == "__main__":
    bump()