# D&D TikTok Slide Generator

This Python script reads themes from a `themes_to_generate.csv` file and, for each theme, generates text and **two versions** of corresponding images for a TikTok series. It adapts the number of slides (13 or 14) based on the theme type, uploads the generated images to a specified Google Drive folder, and keeps track of completed themes to avoid re-processing.

## Features

*   **Batch Processing:** Reads multiple themes from `themes_to_generate.csv`.
*   **Processing Limit:** Asks the user how many new themes to process per run.
*   **Completion Tracking:** Creates and updates `processed_themes.txt` to automatically skip themes that were successfully completed in previous runs.
*   **Flexible Slide Count:** Generates 13 slides (Title + 12 Months/Examples) for most themes, or 14 slides (Title + 13 Classes) for themes containing "class".
*   **AI Text Generation:** Generates slide concepts using OpenAI's Chat API (`gpt-4o`), with prompts designed to encourage unique, theme-focused ideas and avoid clichés.
*   **Dual AI Image Generation:** Generates **two image versions** for each slide using OpenAI's Image API (`gpt-image-1`), attempting to render specific text on the image via the prompt.
*   **Local Saving:** Saves generated images locally to an `images/` directory (e.g., `01_Title_v1.png`, `01_Title_v2.png`).
*   **Google Drive Upload:** (Optional) Uploads both image versions to a specified parent folder in Google Drive, creating a theme-specific subfolder for each run.
*   **Theme-Specific CSV Output:** Outputs slide data (theme, number, title, prompts, text, image paths for v1 and v2) to a separate CSV file for each theme (e.g., `slides_MyTheme.csv`).

## Setup

1.  **Clone the repository (or download the files).**
2.  **Create `themes_to_generate.csv`:** Create a file named `themes_to_generate.csv` in the project root. Add a header row `Theme`, and list each theme you want to generate on a new line below it. Themes already listed in `processed_themes.txt` will be skipped.
3.  **Create a virtual environment:**
    ```bash
    py -m venv venv
    ```
4.  **Activate the virtual environment:**
    *   Windows (PowerShell): `.\venv\Scripts\Activate.ps1`
    *   Windows (CMD): `.\venv\Scripts\activate.bat`
    *   macOS/Linux: `source venv/bin/activate`
5.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
6.  **Set up API Keys and Google Drive Folder:**
    *   Create a file named `config.env` in the project root.
    *   Add your OpenAI API key:
        ```
        OPENAI_API_KEY='YOUR_API_KEY_HERE'
        ```
    *   **(Optional) Set up Google Drive Upload:**
        *   Follow the steps [here](https://developers.google.com/drive/api/quickstart/python) (or similar guides) to enable the Google Drive API in the Google Cloud Console, create OAuth 2.0 credentials for a **Desktop Application**, and download the `client_secret.json` file.
        *   Place the downloaded `client_secret.json` file in the same directory as `main.py`.
        *   Create a parent folder in your Google Drive where you want theme-specific folders to be created (e.g., name it "Loreify TikTok Posts").
        *   Open that parent folder in Google Drive and copy its Folder ID from the URL (the string after `/folders/`).
        *   Add the Folder ID to your `config.env` file:
            ```
            GOOGLE_DRIVE_FOLDER_ID='YOUR_GOOGLE_DRIVE_PARENT_FOLDER_ID_HERE'
            ```
        *   If you omit `GOOGLE_DRIVE_FOLDER_ID` from `config.env`, Drive uploads will be skipped.

## Usage

1.  Ensure your virtual environment is active.
2.  Ensure `themes_to_generate.csv` is populated with the themes you want.
3.  Run the script:
    ```bash
    py main.py
    ```
4.  **(Optional) Enter Limit:** The script will ask how many *new* themes (those not listed in `processed_themes.txt`) you want to process in this run. Enter a number or press Enter to process all new themes.
5.  **(First Google Drive Run Only):** The script will open your web browser, asking you to log in to your Google Account and authorize the application to access your Google Drive. Follow the prompts. A `token.json` file will be created locally to store your authorization for future runs.
6.  The script will process the selected themes sequentially.
7.  For each theme, it generates text, then generates two versions of each image, saves them locally, uploads them to Google Drive (if configured), and creates a theme-specific CSV file (e.g., `slides_MyTheme.csv`).
8.  Successfully completed themes are added to `processed_themes.txt` to be skipped in future runs. 