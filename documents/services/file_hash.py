import hashlib
import os
from django.conf import settings
import json
from filelock import FileLock

def get_file_hash(file_obj):
    md5_hash = hashlib.md5()

    file_obj.seek(0)

    for chunk in iter(lambda: file_obj.read(4096), b""):
        md5_hash.update(chunk)

    file_obj.seek(0)

    return md5_hash.hexdigest()



def get_hash_directory():
    hash_dir = os.path.join(settings.BASE_DIR, "hashFiles")
    os.makedirs(hash_dir, exist_ok=True)
    return hash_dir


def get_or_create_file_report(file_obj, cache_key: str, report_data: dict = None):
    hash_dir = get_hash_directory()
    current_hash = get_file_hash(file_obj)
    hash_file_path = os.path.join(hash_dir, f"{current_hash}.json")
    lock_path = f"{hash_file_path}.lock"
    
    with FileLock(lock_path):
        cached_file_data = {}
        if os.path.exists(hash_file_path):
            with open(hash_file_path, "r") as f:
                try:
                    cached_file_data = json.load(f)
                except json.JSONDecodeError:
                    pass
        
        reports = cached_file_data.get("reports", {})
        
        if report_data is None:
            if cache_key in reports:
                # Cache HIT: Report found - return it
                return {
                    'report_data': reports[cache_key], 
                    'from_cache': True,
                    'hash': current_hash
                }
            else:
                return {
                    'report_data': None, 
                    'from_cache': False,
                    'hash': current_hash
                }
        else:
            reports[cache_key] = report_data
            cached_file_data['reports'] = reports

            # Atomic write: write to temp file then rename
            temp_file_path = f"{hash_file_path}.tmp"
            try:
                with open(temp_file_path, "w") as f:
                    json.dump(cached_file_data, f, indent=2)
                os.replace(temp_file_path, hash_file_path)
            except Exception as e:
                # Clean up temp file if something goes wrong
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                raise e

            return {
                'report_data': reports[cache_key], 
                'from_cache': False,
                'hash': current_hash
            }


def get_report_data_by_hash(file_hash: str) -> dict:
    """
    Load complete report data from hashFiles/{file_hash}.json
    
    Args:
        file_hash: MD5 hash of the file
        
    Returns:
        Complete JSON structure from the hash file
        
    Raises:
        FileNotFoundError: If hash file does not exist
    """
    hash_dir = get_hash_directory()
    hash_file_path = os.path.join(hash_dir, f"{file_hash}.json")
    lock_path = f"{hash_file_path}.lock"
    
    if not os.path.exists(hash_file_path):
        raise FileNotFoundError(f"No report data found for hash: {file_hash}")
    
    with FileLock(lock_path):
        with open(hash_file_path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {"reports": {}}
