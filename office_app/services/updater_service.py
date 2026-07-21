import os
import sys
import subprocess
import urllib.request
import tempfile
import threading

class UpdaterService:
    # Change this whenever you compile a new .exe!
    CURRENT_VERSION = "1.0.17"
    MIN_INSTALLER_BYTES = 40 * 1024 * 1024

    def __init__(self, client):
        self.sb = client

    @staticmethod
    def _parse_version(v: str):
        """Convert 'x.y.z' to a comparable tuple of ints."""
        try:
            return tuple(int(x) for x in v.strip().split("."))
        except (ValueError, AttributeError):
            return (0, 0, 0)

    @classmethod
    def _validate_downloaded_exe(cls, path: str) -> None:
        size = os.path.getsize(path)
        if size < cls.MIN_INSTALLER_BYTES:
            raise RuntimeError(
                f"Downloaded update is too small ({size} bytes). "
                "Check that the update URL is a direct public .exe download."
            )

        with open(path, "rb") as f:
            if f.read(2) != b"MZ":
                raise RuntimeError(
                    "Downloaded update is not a Windows executable. "
                    "Check that the update URL does not point to a web page or login screen."
                )

    def check_for_update(self):
        """Returns (latest_version, download_url) if a *newer* version is available, else None."""
        try:
            response = self.sb.table("app_updates").select("*").eq("id", 1).execute()
            if response.data:
                record = response.data[0]
                latest = record.get("latest_version")
                url = record.get("download_url")

                # Semver comparison: only update if remote version is strictly newer.
                # Prevents accidental downgrades if someone sets an old version in the DB.
                if latest and url and self._parse_version(latest) > self._parse_version(self.CURRENT_VERSION):
                    return latest, url
        except Exception as e:
            print(f"Update check failed: {e}")
        return None

    def download_and_install(self, url, progress_callback=None, success_callback=None, error_callback=None):
        """Downloads the file and triggers the replacement script."""
        # Cancellation flag: call cancel() from the outside (e.g. QProgressDialog.canceled)
        # to abort the download before os._exit is called.
        self._cancelled = False

        def _download():
            try:
                # 1. Setup paths
                current_exe = sys.executable
                if not current_exe.endswith(".exe"):
                    raise RuntimeError("Not running as a compiled .exe, cannot auto-update.")

                exe_dir = os.path.dirname(current_exe)
                exe_name = os.path.basename(current_exe)
                new_exe_path = os.path.join(exe_dir, f"new_{exe_name}")

                # 2. Download the file with progress
                with urllib.request.urlopen(url, timeout=15) as req:
                    total_size = int(req.headers.get('content-length', 0))
                    downloaded = 0
                    block_size = 8192

                    with open(new_exe_path, "wb") as f:
                        while True:
                            if self._cancelled:
                                # Clean up the partial download and bail out silently
                                try:
                                    os.remove(new_exe_path)
                                except OSError:
                                    pass
                                return
                            buffer = req.read(block_size)
                            if not buffer:
                                break
                            f.write(buffer)
                            downloaded += len(buffer)
                            if total_size > 0 and progress_callback:
                                percent = int((downloaded / total_size) * 100)
                                progress_callback(percent)

                # One final cancel check before doing anything destructive
                if self._cancelled:
                    try:
                        os.remove(new_exe_path)
                    except OSError:
                        pass
                    return

                self._validate_downloaded_exe(new_exe_path)

                # 3. Create the replacement batch script
                # Use PID in filename to avoid collisions if multiple instances run
                bat_path = os.path.join(tempfile.gettempdir(), f"ssm_updater_{os.getpid()}.bat")
                backup_exe_path = os.path.join(exe_dir, f"previous_{exe_name}")
                bat_content = f"""@echo off
timeout /t 2 /nobreak > NUL
if exist "{backup_exe_path}" del "{backup_exe_path}"
rename "{current_exe}" "{os.path.basename(backup_exe_path)}"
rename "{new_exe_path}" "{exe_name}"
start "" "{current_exe}"
timeout /t 5 /nobreak > NUL
if exist "{backup_exe_path}" del "{backup_exe_path}"
del "%~f0"
"""
                with open(bat_path, "w") as bat_file:
                    bat_file.write(bat_content)

                # 4. Trigger success callback to let the UI know it's about to restart
                if success_callback:
                    success_callback()

                # 5. Launch the batch script detached and exit the app
                subprocess.Popen(bat_path, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                os._exit(0)

            except Exception as e:
                if error_callback:
                    error_callback(str(e))

        # Run download in a background thread so UI doesn't freeze
        threading.Thread(target=_download, daemon=True).start()

    def cancel(self):
        """Signal the download thread to abort. Safe to call from any thread."""
        self._cancelled = True
