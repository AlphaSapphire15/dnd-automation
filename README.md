# D&D TikTok Slide Generator

This Python script generates text and corresponding images for a 13-slide TikTok series based on a user-provided D&D theme.

## Features

*   Generates 13 slide concepts (Title + 12 Months) using OpenAI's Chat API.
*   Generates accompanying images for each slide using OpenAI's Image API (gpt-image-1 or DALL-E 3).
*   Parses generated text to extract visual prompts and slide text.
*   Saves generated images to an `images/` directory.
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
5.  **Create `config.env` file:** Create a file named `config.env` in the project root and add your OpenAI API key:
    ```
    OPENAI_API_KEY='YOUR_API_KEY_HERE'
    ```

## Usage

1.  Ensure your virtual environment is active.
2.  Run the script:
    ```bash
    py main.py
    ```
3.  Enter the theme when prompted.
4.  The script will generate text, then images (or placeholders if the API key is missing/invalid or image generation fails), and finally create `slides.csv`. 