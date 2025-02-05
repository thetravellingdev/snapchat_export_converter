#!/usr/bin/env python3

import json
from PIL import Image
from pathlib import Path
import zipfile
from tqdm import tqdm
import logging
import subprocess
import piexif
import os
import time
import datetime

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
    """Find mp4 files that are voice memos and convert them to mp3."""
    import os
    import stat
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    
    # Find all mp4 files
    mp4_files = list(tmp_dir.rglob('*.mp4'))
    voice_memos = []
    
    with tqdm(mp4_files, unit="file", ncols=80) as pbar:
        for file in pbar:
            pbar.set_description(f"Checking {file.name[:30]}")
            try:
                # Make file fully writable for owner
                os.chmod(str(file), stat.S_IRUSR | stat.S_IWUSR)
                
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
                    # Create output path with mp3 extension
                    output_path = file.with_suffix('.mp3')
                    
                    # Convert to mp3
                    subprocess.run([
                        'ffmpeg',
                        '-i', str(file),
                        '-vn',  # No video
                        '-acodec', 'libmp3lame',  # Use MP3 codec
                        '-q:a', '2',  # High quality
                        str(output_path),
                        '-y',  # Overwrite if exists
                        '-loglevel', 'error'
                    ], check=True)
                    
                    # Set permissions and timestamps on new file
                    os.chmod(str(output_path), stat.S_IRUSR | stat.S_IWUSR)
                    file_stat = os.stat(str(file))
                    os.utime(str(output_path), (file_stat.st_atime, file_stat.st_mtime))
                    
                    # Remove original mp4
                    os.remove(str(file))  # Using os.remove instead of Path.unlink()
                    
                    voice_memos.append(output_path)
                    
            except Exception as e:
                logging.error(f"Failed to process {file}: {e}")
    
    logging.info(f"Converted {len(voice_memos)} voice memos to MP3")

def get_exif_date(exif_dict):
    """Extract date from EXIF data, return None if not found."""
    if not exif_dict:
        return None
        
    # Try to get date from different EXIF tags
    date_tags = [
        ('Exif', piexif.ExifIFD.DateTimeOriginal),
        ('Exif', piexif.ExifIFD.DateTimeDigitized),
        ('0th', piexif.ImageIFD.DateTime)
    ]
    
    for ifd, tag in date_tags:
        if ifd in exif_dict and tag in exif_dict[ifd]:
            try:
                date_str = exif_dict[ifd][tag].decode('utf-8')
                return datetime.datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
            except:
                continue
    return None

def merge_exif_data(main_exif, overlay_exif):
    """Merge EXIF data, preferring older dates."""
    final_exif = main_exif if main_exif else {'0th':{}, 'Exif':{}, 'GPS':{}, '1st':{}, 'thumbnail':None}
    
    if not overlay_exif:
        return final_exif
        
    # Get dates from both images
    main_date = get_exif_date(main_exif)
    overlay_date = get_exif_date(overlay_exif)
    
    # Determine which date to use (prefer older)
    use_overlay_date = False
    if main_date and overlay_date:
        use_overlay_date = overlay_date < main_date
    elif overlay_date:
        use_overlay_date = True
    
    # Update EXIF data
    if use_overlay_date:
        # Use overlay's date tags
        for ifd in ('0th', 'Exif'):
            if ifd in overlay_exif:
                date_tags = [
                    piexif.ImageIFD.DateTime if ifd == '0th' else None,
                    piexif.ExifIFD.DateTimeOriginal if ifd == 'Exif' else None,
                    piexif.ExifIFD.DateTimeDigitized if ifd == 'Exif' else None
                ]
                date_tags = [tag for tag in date_tags if tag]
                for tag in date_tags:
                    if tag in overlay_exif[ifd]:
                        if ifd not in final_exif:
                            final_exif[ifd] = {}
                        final_exif[ifd][tag] = overlay_exif[ifd][tag]
    
    # Merge other metadata (non-date)
    for ifd in ('0th', 'Exif', 'GPS', '1st'):
        if ifd in overlay_exif and overlay_exif[ifd]:
            if ifd not in final_exif:
                final_exif[ifd] = {}
            # Only copy non-date tags
            for tag, value in overlay_exif[ifd].items():
                if tag not in [piexif.ImageIFD.DateTime, 
                             piexif.ExifIFD.DateTimeOriginal,
                             piexif.ExifIFD.DateTimeDigitized]:
                    final_exif[ifd][tag] = value
    
    return final_exif

def process_image_overlays():
    """Find and process image files with overlays, renaming appropriately."""
    import re
    from PIL import Image
    import piexif
    
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
                
                # Load images and their EXIF data
                main_img = Image.open(original_path)
                overlay_img = Image.open(overlay_path)
                
                # Get EXIF data
                main_exif = None
                overlay_exif = None
                try:
                    main_exif = piexif.load(main_img.info.get('exif', b''))
                except:
                    pass
                try:
                    overlay_exif = piexif.load(overlay_img.info.get('exif', b''))
                except:
                    pass
                
                # Merge EXIF data (prefer older dates)
                final_exif = merge_exif_data(main_exif, overlay_exif)
                
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
                    
                    # Save with EXIF
                    if final_exif:
                        try:
                            exif_bytes = piexif.dump(final_exif)
                            background.save(with_overlay_path, 'JPEG', exif=exif_bytes)
                        except:
                            background.save(with_overlay_path, 'JPEG')
                    else:
                        background.save(with_overlay_path, 'JPEG')
                else:
                    # Save PNG with EXIF if available
                    if final_exif:
                        try:
                            exif_bytes = piexif.dump(final_exif)
                            result.save(with_overlay_path, exif=exif_bytes)
                        except:
                            result.save(with_overlay_path)
                    else:
                        result.save(with_overlay_path)
                
                # Remove overlay file
                overlay_path.unlink()
                
            except Exception as e:
                logging.error(f"Failed to process {main_path}: {e}")
    
    logging.info(f"Processed {len(pairs)} image pairs")

def get_video_creation_date(file_path):
    """Extract creation date from video metadata."""
    try:
        result = subprocess.run([
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            str(file_path)
        ], capture_output=True, text=True)
        
        metadata = json.loads(result.stdout)
        if 'format' in metadata and 'tags' in metadata['format']:
            tags = metadata['format']['tags']
            if 'creation_time' in tags:
                return datetime.datetime.strptime(tags['creation_time'].split('.')[0], '%Y-%m-%d %H:%M:%S')
    except:
        pass
    return None

def process_video_overlays():
    """Find and process video files with overlays using ffmpeg."""
    import re
    import subprocess
    import json
    
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
                
                # Get creation dates
                filename_date = datetime.datetime.strptime(original_path.name.split('_')[0], '%Y-%m-%d')
                video_date = get_video_creation_date(original_path)
                
                # Use the older date
                final_date = min([d for d in [filename_date, video_date] if d is not None])
                date_str = final_date.strftime('%Y-%m-%d %H:%M:%S')
                
                # Check if video has audio stream
                has_audio = subprocess.run([
                    'ffprobe',
                    '-i', str(original_path),
                    '-show_streams',
                    '-select_streams', 'a',
                    '-loglevel', 'error'
                ], capture_output=True, text=True).stdout.strip()

                # Build ffmpeg command based on audio presence
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-i', str(original_path),
                    '-i', str(overlay_path),
                    '-metadata', f'creation_time={date_str}',
                    '-filter_complex', '[0:v][1:v]overlay=0:0',
                    '-movflags', '+faststart'
                ]

                if has_audio:
                    ffmpeg_cmd.extend([
                        '-c:a', 'copy',
                        '-map_metadata:s:a', '0:s:a'
                    ])

                ffmpeg_cmd.extend([
                    str(with_overlay_path),
                    '-y',
                    '-loglevel', 'error'
                ])

                subprocess.run(ffmpeg_cmd, check=True)
                
                # Set file system timestamps to match
                timestamp = final_date.timestamp()
                os.utime(with_overlay_path, (timestamp, timestamp))
                os.utime(original_path, (timestamp, timestamp))
                
                # Remove overlay file
                overlay_path.unlink()
                
            except subprocess.CalledProcessError as e:
                logging.error(f"FFmpeg failed for {main_path}: {e}")
            except Exception as e:
                logging.error(f"Failed to process {main_path}: {e}")
    
    logging.info(f"Processed {len(pairs)} video pairs")

def get_file_metadata(file_path):
    """Extract metadata from image or video file."""
    import json
    from PIL import Image
    import piexif
    
    metadata = {
        'creation_time': file_path.stat().st_ctime,
        'modification_time': file_path.stat().st_mtime,
        'exif_data': None,
        'video_metadata': None
    }
    
    # Handle images
    if file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
        try:
            with Image.open(file_path) as img:
                if 'exif' in img.info:
                    metadata['exif_data'] = piexif.load(img.info['exif'])
        except Exception as e:
            logging.error(f"Failed to extract EXIF from {file_path}: {e}")
    
    # Handle videos
    elif file_path.suffix.lower() == '.mp4':
        try:
            # Get video metadata using ffprobe
            result = subprocess.run([
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(file_path)
            ], capture_output=True, text=True)
            
            if result.stdout:
                metadata['video_metadata'] = json.loads(result.stdout)
        except Exception as e:
            logging.error(f"Failed to extract video metadata from {file_path}: {e}")
    
    return metadata

def score_metadata(metadata):
    """Score metadata completeness. Higher score means more complete metadata."""
    score = 0
    
    # Basic file timestamps
    if metadata['creation_time']:
        score += 1
    if metadata['modification_time']:
        score += 1
    
    # EXIF data for images
    if metadata['exif_data']:
        # Add points for each EXIF section that contains data
        for section in ['0th', 'Exif', 'GPS', '1st']:
            if section in metadata['exif_data'] and metadata['exif_data'][section]:
                score += 2
    
    # Video metadata
    if metadata['video_metadata']:
        if 'format' in metadata['video_metadata']:
            score += 2
        if 'streams' in metadata['video_metadata']:
            score += len(metadata['video_metadata']['streams'])
    
    return score

def remove_duplicates():
    """Find and remove duplicate files while preserving the best metadata."""
    import hashlib
    from collections import defaultdict
    
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    hash_dict = defaultdict(list)
    
    # First pass: Calculate hashes and gather metadata
    all_files = list(tmp_dir.rglob('*'))
    files = [f for f in all_files if f.is_file()]
    
    with tqdm(files, desc="Analyzing files", unit="file", ncols=80) as pbar:
        for file_path in pbar:
            pbar.set_description(f"Analyzing {file_path.name[:30]}")
            try:
                # Calculate SHA-256 hash in chunks
                sha256_hash = hashlib.sha256()
                with open(file_path, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
                
                # Store both file path and its metadata
                metadata = get_file_metadata(file_path)
                hash_dict[sha256_hash.hexdigest()].append((file_path, metadata))
                
            except Exception as e:
                logging.error(f"Failed to analyze {file_path}: {e}")
    
    # Find duplicates and determine which to keep
    to_delete = []
    duplicate_groups = [files for files in hash_dict.values() if len(files) > 1]
    
    with tqdm(duplicate_groups, desc="Processing duplicates", unit="group", ncols=80) as pbar:
        for group in pbar:
            # Score each file's metadata
            scored_files = [(f, m, score_metadata(m)) for f, m in group]
            
            # Sort by metadata score (highest first), then by modification time (newest first)
            scored_files.sort(key=lambda x: (-x[2], -x[1]['modification_time']))
            
            # Keep the first (best) file, mark others for deletion
            to_delete.extend(f for f, _, _ in scored_files[1:])
            
            pbar.set_description(f"Found {len(to_delete)} duplicates")
    
    # Remove duplicates with progress bar
    if not to_delete:
        logging.info("No duplicates found")
        return
    
    with tqdm(to_delete, desc="Removing duplicates", unit="file", ncols=80) as pbar:
        for file_path in pbar:
            pbar.set_description(f"Removing {file_path.name[:30]}")
            try:
                file_path.unlink()
            except Exception as e:
                logging.error(f"Failed to remove {file_path}: {e}")
    
    logging.info(f"Removed {len(to_delete)} duplicate files")
    if to_delete:
        logging.info("Kept files with best metadata quality and newest timestamps")

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

def extract_date_from_filename(filename):
    """Extract date from filename format like '2023-11-22_UUID'."""
    import datetime
    date_str = filename.split('_')[0]
    try:
        return datetime.datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return None

def update_image_metadata(file_path):
    """Update image metadata with creation date from filename if not present."""
    from PIL import Image
    import piexif
    import time
    
    date = extract_date_from_filename(file_path.name)
    if not date:
        return
    
    try:
        # Convert date to EXIF format
        exif_date = date.strftime("%Y:%m:%d %H:%M:%S")
        
        # Read existing EXIF
        img = Image.open(file_path)
        try:
            exif_dict = piexif.load(img.info.get('exif', b''))
        except:
            exif_dict = {'0th':{}, 'Exif':{}, 'GPS':{}, '1st':{}, 'thumbnail':None}
        
        # Add date if not present
        if piexif.ImageIFD.DateTime not in exif_dict['0th']:
            exif_dict['0th'][piexif.ImageIFD.DateTime] = exif_date
        if piexif.ExifIFD.DateTimeOriginal not in exif_dict['Exif']:
            exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = exif_date
        if piexif.ExifIFD.DateTimeDigitized not in exif_dict['Exif']:
            exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = exif_date
            
        # Save updated EXIF
        exif_bytes = piexif.dump(exif_dict)
        img.save(file_path, exif=exif_bytes)
        
        # Update file timestamps
        timestamp = time.mktime(date.timetuple())
        os.utime(file_path, (timestamp, timestamp))
        
    except Exception as e:
        logging.error(f"Failed to update image metadata for {file_path}: {e}")

def update_video_metadata(file_path):
    """Update video metadata with creation date from filename if not present."""
    import json
    
    date = extract_date_from_filename(file_path.name)
    if not date:
        return
        
    try:
        # Check existing metadata
        result = subprocess.run([
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            str(file_path)
        ], capture_output=True, text=True)
        
        metadata = json.loads(result.stdout)
        
        # Only update if creation_time not present
        if 'format' not in metadata or 'tags' not in metadata['format'] or 'creation_time' not in metadata['format']['tags']:
            # Create temporary file
            temp_path = file_path.with_name(file_path.stem + '_temp' + file_path.suffix)
            
            # Add creation date
            subprocess.run([
                'ffmpeg',
                '-i', str(file_path),
                '-metadata', f'creation_time={date.strftime("%Y-%m-%d %H:%M:%S")}',
                '-c', 'copy',
                str(temp_path),
                '-y'
            ], check=True)
            
            # Replace original with updated file
            temp_path.replace(file_path)
            
            # Update file timestamps
            timestamp = time.mktime(date.timetuple())
            os.utime(file_path, (timestamp, timestamp))
            
    except Exception as e:
        logging.error(f"Failed to update video metadata for {file_path}: {e}")

def update_all_metadata():
    """Update metadata for all media files using dates from filenames."""
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    
    # Find all media files
    media_files = []
    for ext in ['.jpg', '.jpeg', '.png', '.webp', '.mp4']:
        media_files.extend(tmp_dir.rglob(f'*{ext}'))
    
    with tqdm(media_files, unit="file", ncols=80) as pbar:
        for file_path in pbar:
            pbar.set_description(f"Updating metadata: {file_path.name[:30]}")
            
            if file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
                update_image_metadata(file_path)
            elif file_path.suffix.lower() == '.mp4':
                update_video_metadata(file_path)

def reorganize_files():
    """Move all files to media folder, named by original folder and sorted by date."""
    root = Path(__file__).parent.parent
    tmp_dir = root / 'tmp'
    media_dir = root / 'media'
    
    # Create media directory
    media_dir.mkdir(exist_ok=True)
    
    # Get all media files and their metadata
    files_with_metadata = []
    for ext in ['.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mp3']:
        for file_path in tmp_dir.rglob(f'*{ext}'):
            try:
                # Get original folder name
                folder_name = file_path.parent.name.lower()
                if folder_name == 'tmp':  # Skip root tmp folder
                    continue
                    
                # Get creation date from filename
                date_str = file_path.name.split('_')[0]
                creation_date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                
                files_with_metadata.append((file_path, folder_name, creation_date))
            except Exception as e:
                logging.error(f"Failed to process metadata for {file_path}: {e}")
    
    # Sort by folder name and creation date
    files_with_metadata.sort(key=lambda x: (x[1], x[2]))
    
    # Group by folder for separate counters
    folder_counters = {}
    
    with tqdm(files_with_metadata, unit="file", ncols=80) as pbar:
        for file_path, folder_name, _ in pbar:
            try:
                pbar.set_description(f"Moving {file_path.name[:30]}")
                
                # Initialize counter for new folders
                if folder_name not in folder_counters:
                    folder_counters[folder_name] = 1
                
                # Create new filename
                new_name = f"{folder_name}_{folder_counters[folder_name]}{file_path.suffix.lower()}"
                new_path = media_dir / new_name
                
                # Increment counter for this folder
                folder_counters[folder_name] += 1
                
                # Move file
                file_path.rename(new_path)
                
            except Exception as e:
                logging.error(f"Failed to move {file_path}: {e}")
    
    # Log summary
    for folder, count in folder_counters.items():
        logging.info(f"Moved {count-1} files from {folder}")

def main():

    logging.info("1/10 📦 Starting extraction...")
    extract_snapchat_data()
    logging.info("✅ Extraction complete\n")
    
    logging.info("2/10 🧹 Removing unwanted file types...")
    remove_unwanted_files()
    logging.info("✅ Unwanted file removal complete\n")    

    logging.info("3/10 🖼️  Removing thumbnails...")
    remove_thumbnails()
    logging.info("✅ Thumbnail removal complete\n")

    logging.info("4/10 🔍 Finding and removing duplicates...")
    remove_duplicates()
    logging.info("✅ Duplicate removal complete\n")
    
    logging.info("5/10 🎤 Finding voice memos...")
    find_voice_memos()
    logging.info("✅ Voice memo detection complete\n")
    
    logging.info("6/10 📸 Processing image overlays...")
    process_image_overlays()
    logging.info("✅ Image overlay processing complete\n")
    
    logging.info("7/10 🎥 Processing video overlays...")
    process_video_overlays()
    logging.info("✅ Video overlay processing complete\n")

    logging.info("8/10 📅 Updating file metadata from filenames...")
    update_all_metadata()
    logging.info("✅ Metadata update complete\n")

    logging.info("9/10 🗑️  Cleaning up empty folders...")
    remove_empty_folders()
    logging.info("✅ Empty folder cleanup complete\n")

    logging.info("10/10 📁 Reorganizing files into categories...")
    reorganize_files()
    logging.info("✅ File reorganization complete\n")
    
    print("\n✨ All operations completed successfully! ✨\n")

if __name__ == "__main__":
    main()