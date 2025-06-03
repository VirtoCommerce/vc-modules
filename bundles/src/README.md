
# Release Notes Generator

This project provides a script to generate a structured `release_notes.html` file

## 📁 Project Structure

```
modules/
└── src/
    ├── collect_releases.py # The release notes generator
    └── modules_config.json
```

## 🚀 Features

- Extracts release information from GitHub repository tags.
- Filters tags by version range.
- Supports pre-release and regular release tags.
- Generates a styled `release_notes.html` file locally.
- Designed for running directly from the terminal.
- Highlights:
  - Found tags
  - Releases without notes
  - Missing releases in the specified range


## 📦 Requirements

- Python 3.8+
- Python installed and available in `PATH`
- Create a folder with files. Name example - release-notes-bot. Inside it, add:
  - A JSON config file (modules_config.json)
  - GitHub token 
  - The script file (collect_releases.py)

Open a terminal

Windows: Press Win + R, type cmd, press Enter

macOS: Press Cmd + Space, type “Terminal”, open it

Navigate to your folder:




Install dependencies:
```bash
 cd path_to_your_folder
 pip install requests
```



## ⚙️ Usage

Run the script from the project:

```bash
  python collect_releases.py
```

## 📄 Output

A file named release_notes.html will be generated in the same folder. It will include all release notes for the specified modules and versions.

- If no release exists for a given version, it will be marked as missing.

- Each module’s section will show tags found and any gaps in releases.


Enjoy automating your release note collection! 
