# D&D TikTok Slide Generator

This Python script generates text and corresponding images for a 13-slide TikTok series based on a user-provided D&D theme. It can optionally upload the generated images to a specified Google Drive folder, organizing them into subfolders based on the theme.

## Features

*   Generates 13 slide concepts (Title + 12 Months) using OpenAI's Chat API.
*   Generates accompanying images for each slide using OpenAI's Image API (`gpt-image-1`).
*   Attempts to render the specific slide text directly onto the image via the image generation prompt.
*   Saves generated images locally to an `images/` directory.
*   **Optional:** Uploads generated images to a specified parent folder in Google Drive, creating a theme-specific subfolder for each run.
*   Outputs all slide data (theme, number, title, prompts, text, image path) to `slides.csv`.

## Setup

1.  **Clone the repository (or download the files).**
2.  **Create a virtual environment:**
    ```bash
    py -m venv venv
    ```
3.  **Activate the virtual environment:**
    *   Windows (PowerShell): `.\venv\Scripts\Activate.ps1`
    *   Windows (CMD): `.\venv\Scripts\activate.bat`
    *   macOS/Linux: `source venv/bin/activate`
4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Set up API Keys and Google Drive Folder:**
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
2.  Run the script:
    ```bash
    py main.py
    ```
3.  **(First Google Drive Run Only):** The script will open your web browser, asking you to log in to your Google Account and authorize the application to access your Google Drive. Follow the prompts. A `token.json` file will be created locally to store your authorization for future runs.
4.  Enter the theme when prompted.
5.  The script will generate text, then images, save them locally, and upload them to the appropriate Google Drive folder (if configured).
6.  Finally, it creates `slides.csv`. 