# Download Cleaner
A Python utility to organize and clean up your Downloads folder through an interactive terminal menu.
Download Cleaner helps you sort files, identify large files, and review old archives without automatically deleting files in the background.

## Features
- **Organize Downloads:** Categorizes files into Documents, Images, Videos, Audio, Archives, Installers, and Code.
- **Custom destinations:** Choose where each category should be stored and optionally save your preferences.
- **Large file report:** Find files that meet or exceed a configurable size threshold. The default is 1024 MB.
- **Old archive cleanup:** Find older archives and interactively select files for deletion. The default age threshold is 15 days.
- **Duplicate detection:** Identify identical files during organization and optionally remove redundant copies.
- **Remember preferences:** Save category destinations and remember files you don't want to be prompted about again.
- **Settings viewer:** Review your current configuration from the menu.

## Requirements
- Python installed on your system.
- The `questionary` Python package.

## Installation
1. Download or clone this repository.
2. Open a terminal in the project folder.
3. Install the dependency:

   ```bash
   python -m pip install questionary
   ```

## Usage

Run the script from the project directory:

```bash
python cleanup.py
```

On Windows, you can also try:

```bash
py cleanup.py
```

Follow the interactive menu to select an operation:

1. Organize Downloads.
2. Show large files.
3. Clean up old archives.
4. Run everything.
5. View current settings.
6. Exit.

## Configuration
On its first run, Download Cleaner creates a `config.json` file next to `cleanup.py` if one doesn't already exist.

You can customize settings such as:

- Downloads folder location.
- Large-file size threshold.
- Minimum age for archive cleanup.
- File extensions and category mappings.
- Default destination folders.

The default Downloads location is detected from your user home directory.

Keep your personal configuration local. Each user should generate and customize their own `config.json`.

## Safety
- File organization displays proposed moves and asks for confirmation.
- File deletion requires an additional confirmation.
- Review selected files carefully before confirming deletion.
- Back up important files before using cleanup operations.
- Test the tool on sample files before using it on important data.

## Contributing
Suggestions, bug reports, and improvements are welcome. Please open an issue or submit a pull request.

## License
See the repository's `LICENSE` file for the terms under which this project may be used and redistributed.
