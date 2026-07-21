import argparse
import glob
import sys
from pathlib import Path

from office_app.services.supabase_client import get_supabase_admin_client
from office_app.services.updater_service import UpdaterService


def publish(download_url=None, upload_to_supabase=False):
    print("--- SSM Auto-Updater Publisher ---")

    version = UpdaterService.CURRENT_VERSION
    sb = get_supabase_admin_client()

    if upload_to_supabase:
        # Legacy path. This can fail when the build is larger than the Supabase
        # dashboard/upload limit, so prefer --download-url for normal releases.
        dist_folder = Path("dist")
        exes = list(dist_folder.glob("*.exe"))
        if not exes:
            print("Error: No .exe found in the 'dist' folder. Did you run build_release.ps1?")
            sys.exit(1)
        if len(exes) > 1:
            print(f"Error: Multiple .exe files found in 'dist'. Please clean the folder and keep only the latest build.")
            sys.exit(1)

        exe_path = exes[0]
        file_name = f"SSM_System_v{version}.exe"

        print(f"\nUploading to Supabase Storage as {file_name}...")
        print("(This might take a minute depending on your internet upload speed...)")

        with open(exe_path, "rb") as f:
            sb.storage.from_("releases").upload(
                path=file_name,
                file=f,
                file_options={"upsert": "true", "content-type": "application/octet-stream"},
            )

        download_url = sb.storage.from_("releases").get_public_url(file_name)
    elif not download_url:
        print("Error: provide --download-url, or pass --upload-supabase for the old upload flow.")
        sys.exit(1)

    print("Updating database to notify all clients...")
    sb.table("app_updates").update(
        {
            "latest_version": version,
            "download_url": download_url,
        }
    ).eq("id", 1).execute()  # There is only one record for app updates

    print(f"\nSUCCESS! All computers will automatically download version {version} on their next restart.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publish the latest app update metadata.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--download-url",
        help="Public direct-download URL for the compiled .exe hosted outside Supabase.",
    )
    group.add_argument(
        "--upload-supabase",
        action="store_true",
        help="Upload dist/*.exe to Supabase Storage before updating app_updates.",
    )
    args = parser.parse_args()

    publish(download_url=args.download_url, upload_to_supabase=args.upload_supabase)
