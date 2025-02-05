#!/usr/bin/env python3

from pathlib import Path
import zipfile
from tqdm import tqdm
import logging
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)

def extract_snapchat_data():
    """Extract Snapchat data zip files to tmp directory."""
    root = Path(__file__).parent.parent
    zip_dir = root / 'zips'
    tmp_dir = root / 'tmp'
    
    # Create tmp dir if it doesn't exist
    tmp_dir.mkdir(exist_ok=True)
    
    # Get list of zip files
    zip_files = list(zip_dir.glob('My Data*.zip'))
    
    if not zip_files:
        logging.error("No zip files found")
        return
    
    # Count total files across all zips
    total_files = 0
    for zip_path in zip_files:
        with zipfile.ZipFile(zip_path) as zip_ref:
            total_files += len(zip_ref.namelist())
    
    # Extract with progress bar
    with tqdm(total=total_files, unit="file", ncols=80) as pbar:
        for zip_path in zip_files:
            logging.info(f"Processing {zip_path.name}")
            try:
                with zipfile.ZipFile(zip_path) as zip_ref:
                    # Update progress for each file in the zip
                    for file in zip_ref.namelist():
                        zip_ref.extract(file, tmp_dir)
                        pbar.update(1)
                        pbar.set_description(f"Extracting {Path(file).name[:30]}")
            except Exception as e:
                logging.error(f"Failed to extract {zip_path.name}: {e}")

def remove_thumbnails():
    """Remove all thumbnail files from tmp directory."""
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    
    # Find all thumbnail files
    thumbnail_files = list(tmp_dir.rglob('*thumbnail*'))
    
    if not thumbnail_files:
        logging.info("No thumbnail files found")
        return
    
    # Remove thumbnails with progress bar
    with tqdm(thumbnail_files, unit="file", ncols=80) as pbar:
        for thumb_file in pbar:
            pbar.set_description(f"Removing {thumb_file.name[:30]}")
            try:
                thumb_file.unlink()
            except Exception as e:
                logging.error(f"Failed to remove {thumb_file}: {e}")
    
    logging.info(f"Removed {len(thumbnail_files)} thumbnail files")

def find_voice_memos():
    """Find all mp4 files that are actually voice memos (no video stream)."""
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    
    # Find all mp4 files
    mp4_files = list(tmp_dir.rglob('*.mp4'))
    voice_memos = []
    
    with tqdm(mp4_files, unit="file", ncols=80) as pbar:
        for file in pbar:
            pbar.set_description(f"Checking {file.name[:30]}")
            try:
                # Run ffprobe to check for video streams
                result = subprocess.run([
                    'ffprobe',
                    '-i', str(file),
                    '-show_streams',
                    '-select_streams', 'v',
                    '-loglevel', 'error'
                ], capture_output=True, text=True)
                
                # If there's no output, it's a voice memo
                if not result.stdout.strip():
                    # Add -voicememo to filename
                    new_path = file.with_name(file.stem + '-voicememo' + file.suffix)
                    file.rename(new_path)
                    voice_memos.append(new_path)
            except Exception as e:
                logging.error(f"Failed to check {file}: {e}")
    
    logging.info(f"Found {len(voice_memos)} voice memos")
    return voice_memos

def process_image_overlays():
    """Find and process image files with overlays, renaming appropriately."""
    import re
    from PIL import Image
    
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    overlays = {}
    mains = {}
    
    # Regular expression for UUID
    uuid_pattern = r'[0-9A-Fa-f-]{36}'
    
    # Find all files and categorize them
    for file in tmp_dir.rglob('*'):
        if not file.is_file():
            continue
            
        match = re.search(uuid_pattern, str(file))
        if not match:
            continue
            
        uuid = match.group()
        if '-overlay.' in file.name:
            overlays[uuid] = file
        elif '-main.' in file.name and file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
            mains[uuid] = file
    
    # Process pairs with progress bar
    pairs = [(uuid, main, overlays[uuid]) 
             for uuid, main in mains.items() 
             if uuid in overlays]
    
    with tqdm(pairs, unit="image", ncols=80) as pbar:
        for uuid, main_path, overlay_path in pbar:
            try:
                pbar.set_description(f"Processing {main_path.name[:30]}")
                
                # Prepare output paths
                base_path = main_path.parent / main_path.name.replace('-main', '')
                original_path = base_path.with_name(base_path.stem + '-original' + main_path.suffix)
                with_overlay_path = base_path.with_name(base_path.stem + '-with-overlay' + main_path.suffix)
                
                # Copy original
                main_path.rename(original_path)
                
                # Combine images
                main_img = Image.open(original_path)
                overlay_img = Image.open(overlay_path)
                
                # Resize overlay if needed
                if main_img.size != overlay_img.size:
                    overlay_img = overlay_img.resize(main_img.size)
                
                # Composite images
                result = Image.alpha_composite(main_img.convert('RGBA'), overlay_img)
                
                # Convert back to RGB for JPEG
                if with_overlay_path.suffix.lower() in ['.jpg', '.jpeg']:
                    # Create white background
                    background = Image.new('RGB', result.size, 'WHITE')
                    # Paste using alpha channel
                    background.paste(result, mask=result.split()[3])
                    background.save(with_overlay_path, 'JPEG')
                else:
                    result.save(with_overlay_path)
                
                # Remove overlay file
                overlay_path.unlink()
                
            except Exception as e:
                logging.error(f"Failed to process {main_path}: {e}")
    
    logging.info(f"Processed {len(pairs)} image pairs")

def process_video_overlays():
    """Find and process video files with overlays using ffmpeg."""
    import re
    import subprocess
    
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    overlays = {}
    mains = {}
    
    # Regular expression for UUID
    uuid_pattern = r'[0-9A-Fa-f-]{36}'
    
    # Find all files and categorize them
    for file in tmp_dir.rglob('*'):
        if not file.is_file():
            continue
            
        match = re.search(uuid_pattern, str(file))
        if not match:
            continue
            
        uuid = match.group()
        if '-overlay.' in file.name and file.suffix.lower() == '.png':
            overlays[uuid] = file
        elif '-main.' in file.name and file.suffix.lower() == '.mp4':
            mains[uuid] = file
    
    # Process pairs with progress bar
    pairs = [(uuid, main, overlays[uuid]) 
             for uuid, main in mains.items() 
             if uuid in overlays]
    
    with tqdm(pairs, unit="video", ncols=80) as pbar:
        for uuid, main_path, overlay_path in pbar:
            try:
                pbar.set_description(f"Processing {main_path.name[:30]}")
                
                # Prepare output paths
                base_path = main_path.parent / main_path.name.replace('-main', '')
                original_path = base_path.with_name(base_path.stem + '-original.mp4')
                with_overlay_path = base_path.with_name(base_path.stem + '-with-overlay.mp4')
                
                # Rename original
                main_path.rename(original_path)
                
                # Apply overlay using ffmpeg
                subprocess.run([
                    'ffmpeg',
                    '-i', str(original_path),
                    '-i', str(overlay_path),
                    '-filter_complex', '[0:v][1:v]overlay=0:0',
                    '-c:a', 'copy',
                    str(with_overlay_path),
                    '-y',  # Overwrite if exists
                    '-loglevel', 'error'
                ], check=True)
                
                # Remove overlay file
                overlay_path.unlink()
                
            except subprocess.CalledProcessError as e:
                logging.error(f"FFmpeg failed for {main_path}: {e}")
            except Exception as e:
                logging.error(f"Failed to process {main_path}: {e}")
    
    logging.info(f"Processed {len(pairs)} video pairs")

def remove_duplicates():
    """Find and remove exact duplicate files using SHA-256 hashing."""
    import hashlib
    from collections import defaultdict
    
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    hash_dict = defaultdict(list)
    
    # First pass: Calculate hashes
    all_files = list(tmp_dir.rglob('*'))
    files = [f for f in all_files if f.is_file()]
    
    with tqdm(files, desc="Calculating hashes", unit="file", ncols=80) as pbar:
        for file_path in pbar:
            pbar.set_description(f"Hashing {file_path.name[:30]}")
            try:
                # Calculate SHA-256 hash in chunks
                sha256_hash = hashlib.sha256()
                with open(file_path, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                hash_dict[sha256_hash.hexdigest()].append(file_path)
            except Exception as e:
                logging.error(f"Failed to hash {file_path}: {e}")
    
    # Find duplicates
    duplicates = [paths[1:] for paths in hash_dict.values() if len(paths) > 1]
    duplicate_count = sum(len(dups) for dups in duplicates)
    
    if not duplicate_count:
        logging.info("No duplicates found")
        return
    
    # Remove duplicates with progress bar
    with tqdm(total=duplicate_count, desc="Removing duplicates", unit="file", ncols=80) as pbar:
        for dup_list in duplicates:
            for dup_path in dup_list:
                pbar.set_description(f"Removing {dup_path.name[:30]}")
                try:
                    dup_path.unlink()
                    pbar.update(1)
                except Exception as e:
                    logging.error(f"Failed to remove {dup_path}: {e}")
    
    logging.info(f"Removed {duplicate_count} duplicate files")

def remove_unwanted_files():
    """Remove all files except webp, png, jpeg, jpg, and mp4."""
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    
    # Define allowed extensions
    allowed_extensions = {'.webp', '.png', '.jpeg', '.jpg', '.mp4'}
    
    # Get all files that aren't in allowed extensions
    files = [f for f in tmp_dir.rglob('*') 
             if f.is_file() and f.suffix.lower() not in allowed_extensions]
    
    if not files:
        logging.info("No unwanted files found")
        return
    
    with tqdm(files, desc="Removing unwanted files", unit="file", ncols=80) as pbar:
        for file_path in pbar:
            pbar.set_description(f"Removing {file_path.name[:30]}")
            try:
                file_path.unlink()
            except Exception as e:
                logging.error(f"Failed to remove {file_path}: {e}")
    
    logging.info(f"Removed {len(files)} unwanted files")

def remove_empty_folders():
    """Remove all empty folders recursively."""
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    
    # First count all directories for progress bar
    all_dirs = [d for d in tmp_dir.rglob('*') if d.is_dir()]
    
    if not all_dirs:
        logging.info("No directories found")
        return
    
    with tqdm(total=len(all_dirs), desc="Removing empty folders", unit="folder", ncols=80) as pbar:
        # Keep going until we can't remove any more empty dirs
        while True:
            empty_dirs = []
            
            # Find all empty directories
            for dir_path in tmp_dir.rglob('*'):
                if dir_path.is_dir():
                    try:
                        # Check if directory is empty or only contains empty directories
                        contents = list(dir_path.iterdir())
                        if not contents:
                            empty_dirs.append(dir_path)
                    except Exception as e:
                        logging.error(f"Failed to check {dir_path}: {e}")
            
            if not empty_dirs:
                break
                
            # Remove empty directories
            for dir_path in empty_dirs:
                try:
                    dir_path.rmdir()
                    pbar.update(1)
                    pbar.set_description(f"Removed {dir_path.name[:30]}")
                except Exception as e:
                    logging.error(f"Failed to remove {dir_path}: {e}")
    
    logging.info("Empty folder removal complete")

def main():
    logging.info("Starting extraction")
    extract_snapchat_data()
    logging.info("Extraction complete")
    
    logging.info("Removing unwanted file types")
    remove_unwanted_files()
    logging.info("Unwanted file removal complete")    

    logging.info("Removing thumbnails")
    remove_thumbnails()
    logging.info("Thumbnail removal complete")

    logging.info("Finding and removing duplicates")
    remove_duplicates()
    logging.info("Duplicate removal complete")
    
    logging.info("Finding voice memos")
    find_voice_memos()
    logging.info("Voice memo detection complete")
    
    logging.info("Processing image overlays")
    process_image_overlays()
    logging.info("Image overlay processing complete")
    
    logging.info("Processing video overlays")
    process_video_overlays()
    logging.info("Video overlay processing complete")

    logging.info("Cleaning up empty folders")
    remove_empty_folders()
    logging.info("Empty folder cleanup complete")

if __name__ == "__main__":
    main()