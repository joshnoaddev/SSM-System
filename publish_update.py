import os
import glob
from office_app.services.supabase_client import get_supabase

# Import the service so we can read the version automatically!
from office_app.services.updater_service import UpdaterService

def publish():
    print("--- SSM Auto-Updater Publisher ---")
    
    # 1. Find the compiled .exe
    exes = glob.glob("dist/*.exe")
    if not exes:
        print("Error: No .exe found in the 'dist' folder. Did you run build_release.ps1?")
        return
    
    exe_path = exes[0]
    
    # AUTOMATED: Read the version directly from your code!
    version = UpdaterService.CURRENT_VERSION
    file_name = f"SSM_System_v{version}.exe"

    sb = get_supabase()

    # 2. Upload to Supabase Storage
    print(f"\nUploading to Supabase Storage as {file_name}...")
    print("(This might take a minute depending on your internet upload speed...)")
    
    with open(exe_path, "rb") as f:
        sb.storage.from_("releases").upload(
            path=file_name,
            file=f.read(),
            file_options={"upsert": "true", "content-type": "application/octet-stream"}
        )
    
    # 3. Get the Public Download URL
    public_url = sb.storage.from_("releases").get_public_url(file_name)
    
    # 4. Update the Database
    print("Updating database to notify all clients...")
    sb.table("app_updates").update({
        "latest_version": version,
        "download_url": public_url
    }).eq("id", 1).execute()
    
    print(f"\n✅ SUCCESS! All computers will automatically download version {version} on their next restart.")

if __name__ == "__main__":
    publish()