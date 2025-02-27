#!/usr/bin/env python3

import os
import shutil
import zipfile
import logging
import re
from datetime import datetime
from pathlib import Path
import subprocess
from PIL import Image
import uuid
import ffmpeg

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('snapchat_processor.log'),
        logging.StreamHandler()
    ]
)

class SnapchatProcessor:
    def __init__(self, zip_dir="zips", tmp_dir="tmp", media_dir="media"):
        self.zip_dir = Path(zip_dir)
        self.tmp_dir = Path(tmp_dir)
        self.media_dir = Path(media_dir)
        self.supported_extensions = {'.mp4', '.jpg', '.jpeg', '.png', '.webp'}
        
    def setup_directories(self):
        """Create necessary directories if they don't exist."""
        for directory in [self.tmp_dir, self.media_dir]:
            directory.mkdir(exist_ok=True)
            logging.info(f"Ensured directory exists: {directory}")

    def extract_files(self):
        """Extract supported files from zip archives."""
        try:
            for zip_file in self.zip_dir.glob('*.zip'):
                logging.info(f"Processing zip file: {zip_file}")
                with zipfile.ZipFile(zip_file) as zf:
                    for file_info in zf.infolist():
                        if any(file_info.filename.lower().endswith(ext) for ext in self.supported_extensions):
                            if 'thumbnail' not in file_info.filename.lower():
                                zf.extract(file_info, self.tmp_dir)
                                logging.info(f"Extracted: {file_info.filename}")
        except Exception as e:
            logging.error(f"Error during extraction: {str(e)}")
            raise

    def process_html_files(self):
        """Process files from the HTML folder with proper renaming."""
        html_dir = self.tmp_dir / 'html'
        try:
            if html_dir.exists():
                for folder in html_dir.iterdir():
                    if folder.is_dir():
                        for file in folder.glob('*.*'):
                            if file.suffix.lower() in self.supported_extensions:
                                new_name = f"{folder.name}{file.suffix.lower()}"
                                shutil.copy2(file, self.media_dir / new_name)
                                logging.info(f"Processed HTML file: {file} -> {new_name}")
        except Exception as e:
            logging.error(f"Error processing HTML files: {str(e)}")
            raise

    def _extract_date_from_filename(self, filename):
        """Extract date from filename pattern."""
        date_pattern = r'(\d{4}-\d{2}-\d{2})'
        match = re.search(date_pattern, filename)
        if match:
            return match.group(1)
        return None

    def apply_metadata(self, file_path):
        """Apply metadata based on filename date."""
        date_str = self._extract_date_from_filename(file_path.name)
        if date_str:
            try:
                # Convert date string to datetime
                date_time = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_time.strftime('%Y:%m:%d %H:%M:%S')
                timestamp = date_time.strftime('%Y%m%d%H%M.%S')
                
                # First use touch to set filesystem dates
                subprocess.run([
                    'touch',
                    '-t',
                    timestamp,
                    str(file_path)
                ], check=True)
                
                # Then use exiftool to set all possible date fields
                subprocess.run([
                    'exiftool',
                    '-overwrite_original',
                    '-all=',  # Remove all metadata
                    str(file_path)
                ], check=True)
                
                subprocess.run([
                    'exiftool',
                    '-overwrite_original',
                    f'-AllDates={formatted_date}',  # Set all date fields
                    str(file_path)
                ], check=True)
                
                # Set filesystem dates again to ensure they stick
                subprocess.run([
                    'touch',
                    '-t',
                    timestamp,
                    str(file_path)
                ], check=True)
                
                logging.info(f"Applied metadata to: {file_path}")
            except Exception as e:
                logging.error(f"Error applying metadata to {file_path}: {str(e)}")

    def apply_overlay(self, main_file, overlay_file, output_file):
        """Apply overlay to main file."""
        try:
            if main_file.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}:
                # Process image
                with Image.open(main_file) as base:
                    with Image.open(overlay_file) as overlay:
                        # Resize overlay to match base image size
                        overlay = overlay.resize(base.size)
                        # Convert images to RGBA if they aren't already
                        if base.mode != 'RGBA':
                            base = base.convert('RGBA')
                        if overlay.mode != 'RGBA':
                            overlay = overlay.convert('RGBA')
                        # Composite the images
                        result = Image.alpha_composite(base, overlay)
                        result.save(output_file)
            elif main_file.suffix.lower() == '.mp4':
                # Process video using ffmpeg
                overlay_path = str(overlay_file)
                main_input = ffmpeg.input(str(main_file))
                overlay_input = ffmpeg.input(overlay_path)
                
                ffmpeg.filter(
                    [main_input, overlay_input],
                    'overlay',
                    'overlay'
                ).output(
                    str(output_file)
                ).overwrite_output().run()
            
            logging.info(f"Applied overlay: {main_file} + {overlay_file} -> {output_file}")
        except Exception as e:
            logging.error(f"Error applying overlay: {str(e)}")
            raise

    def process_memories(self):
        """Process memories folder, applying overlays where applicable."""
        memories_dir = self.tmp_dir / 'memories'
        try:
            if memories_dir.exists():
                # Group files by their UUID
                files_by_uuid = {}
                for file in memories_dir.iterdir():
                    if file.is_file():
                        # Extract UUID from filename
                        uuid_match = re.search(r'(\d{4}-\d{2}-\d{2})_([^-]+)', file.name)
                        if uuid_match:
                            date, file_uuid = uuid_match.groups()
                            if file_uuid not in files_by_uuid:
                                files_by_uuid[file_uuid] = {'date': date, 'files': []}
                            files_by_uuid[file_uuid]['files'].append(file)

                # Process each group
                for file_uuid, group in files_by_uuid.items():
                    main_file = next((f for f in group['files'] if 'main' in f.name), None)
                    overlay_file = next((f for f in group['files'] if 'overlay' in f.name), None)

                    if main_file and overlay_file:
                        # Handle original file
                        original_name = main_file.name.replace('-main', '-original')
                        original_path = self.media_dir / original_name
                        
                        # Copy with appropriate metadata handling
                        if main_file.suffix.lower() == '.mp4':
                            # For videos, use ffmpeg to copy while preserving metadata
                            ffmpeg.input(str(main_file)).output(
                                str(original_path),
                                codec='copy',
                                map_metadata=0
                            ).overwrite_output().run()
                        else:
                            # For images, copy and apply date-based metadata
                            shutil.copy2(main_file, original_path)
                            self.apply_metadata(original_path)

                        # Create overlaid version
                        overlay_name = main_file.name.replace('-main', '-with-overlay')
                        overlay_path = self.media_dir / overlay_name
                        
                        # Apply overlay with metadata handling
                        self.apply_overlay(
                            main_file,
                            overlay_file,
                            overlay_path
                        )
                        
                        # Handle metadata for overlaid version
                        if main_file.suffix.lower() == '.mp4':
                            # Extract metadata from original video and apply to overlaid version
                            subprocess.run([
                                'exiftool',
                                '-overwrite_original',
                                f'-tagsFromFile',
                                str(main_file),
                                str(overlay_path)
                            ], check=True)
                        else:
                            # For images, apply date-based metadata
                            self.apply_metadata(overlay_path)
                        
                        logging.info(f"Processed memory pair: {main_file.name}")
        except Exception as e:
            logging.error(f"Error processing memories: {str(e)}")
            raise

    def process_all(self):
        """Run the complete processing pipeline."""
        try:
            logging.info("Starting Snapchat data processing")
            self.setup_directories()
            self.extract_files()
            self.process_html_files()
            
            # Process files with date-based metadata
            for file in self.tmp_dir.rglob('*.*'):
                if file.suffix.lower() in self.supported_extensions:
                    if 'thumbnail' not in file.name.lower():
                        shutil.copy2(file, self.media_dir)
                        self.apply_metadata(self.media_dir / file.name)
            
            self.process_memories()
            logging.info("Completed Snapchat data processing")
        except Exception as e:
            logging.error(f"Error in processing pipeline: {str(e)}")
            raise

if __name__ == "__main__":
    processor = SnapchatProcessor()
    processor.process_all()