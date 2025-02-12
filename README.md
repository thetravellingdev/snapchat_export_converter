# Snapchat Export Converter

A script that processes your Snapchat data download and prepares it for easy import into a photo library. It automates extraction, cleanup, metadata updating, and reorganization.

## 📌 Prerequisites

- Install dependencies:
  ```sh
  pip install -r requirements.txt
  ```

## 📥 Download Your Snapchat Data

You can download your Snapchat data from [Snapchat My Data](https://accounts.snapchat.com/accounts/downloadmydata).

## 🚀 Usage

1. Place your Snapchat `.zip` files in the `zips/` folder.
2. Run the script:
   ```sh
   python src/index.ts
   ```

## 🔟 Processing Steps

1. **Extract Snapchat Data** – Unzips and organizes the contents.
2. **Remove Unwanted Files** – Deletes unnecessary file types.
3. **Remove Thumbnails** – Cleans up low-resolution duplicates.
4. **Remove Duplicates** – Identifies and removes duplicate media.
5. **Detect Voice Memos** – Searches for and organizes audio recordings.
6. **Process Image Overlays** – Extracts overlays from images.
7. **Process Video Overlays** – Extracts overlays from videos.
8. **Update Metadata** – Updates timestamps from filenames.
9. **Remove Empty Folders** – Cleans up unused directories.
10. **Reorganize Files** – Sorts files into appropriate categories.

## 📂 Folder Structure

- `zips/` – Place Snapchat data archives here.
- `tmp/` – Temporary working directory for processing files.
- `src/` – Source code and virtual environment.

After execution, your cleaned and organized files will be ready for import into your preferred photo management system.

<img 
  src="https://hub.scheef.tech/api/client_image/snapchat_exporter"
  style="display:block; opacity:0"
/>
