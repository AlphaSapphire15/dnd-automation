import base64
import csv
import os
import pathlib
import re
import textwrap
import time # Added for potential delays/retries
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont # Import ImageDraw and ImageFont from Pillow

# --- Google Drive Imports ---
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
# --- End Google Drive Imports ---


# ------------- 1. Load API key and Setup -------------
load_dotenv("config.env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID") # Parent folder for all themes

# --- Google Drive Setup ---
SCOPES = ['https://www.googleapis.com/auth/drive.file'] # Scope for file creation/upload
TOKEN_PATH = 'token.json'
CREDS_PATH = 'client_secret.json'
# --- End Google Drive Setup ---

# Global check for key (used by functions before main)
if not OPENAI_API_KEY:
    print("⚠️  No OPENAI_API_KEY found in config.env – using placeholders for API calls.")
else:
    try:
        import openai
        openai.api_key = OPENAI_API_KEY
        print("✅ OpenAI API key loaded globally.")
    except ImportError:
        print("⚠️ OpenAI library not installed. Run 'py -m pip install openai'")
        OPENAI_API_KEY = None # Ensure key is treated as missing

# ------------- 2. Define Your Art Style Prompt Components (REMOVED GLOBAL ART_STYLE) -------------
# The art style description will be combined dynamically later

# ------------- 3. Function to Generate Slide Text -------------
def generate_slides_text(theme: str) -> str | None:
    """Calls OpenAI Chat API to generate slide text descriptions, adapting to theme type."""
    if not OPENAI_API_KEY:
        print("ℹ️ Skipping text generation (no API key).")
        # Cannot generate placeholders without knowing theme type, return None
        return None

    print(f"📝 Requesting slide text generation for theme: '{theme}'...")

    # --- Determine Prompt Structure based on Theme ---
    is_month_theme = False
    is_class_theme = False
    theme_lower = theme.lower()

    if "month" in theme_lower or "birth month" in theme_lower:
        is_month_theme = True
        print("   -> Detected month-based theme (13 slides)." )
        slide_count_target = 13
        item_type_plural = "months (Jan-Dec)"
        item_type_singular = "Month/Title"
        specific_guideline = "Slides 2-13 correspond to January-December."
    elif "class" in theme_lower or "classes" in theme_lower:
        is_class_theme = True
        print("   -> Detected D&D class-based theme (14 slides)." )
        slide_count_target = 14 # Title + 13 classes
        item_type_plural = "D&D 5e classes (Artificer, Barbarian... Wizard)"
        item_type_singular = "Class"
        specific_guideline = f"Slides 2-14 should feature one example for each of the 13 official D&D 5e classes: Artificer, Barbarian, Bard, Cleric, Druid, Fighter, Monk, Paladin, Ranger, Rogue, Sorcerer, Warlock, Wizard. Use the class name as the concept title."
    else:
        print("   -> Detected general theme (13 slides)." )
        slide_count_target = 13
        item_type_plural = "unique examples or concepts related to the theme"
        item_type_singular = "Concept"
        specific_guideline = f"Slides 2-13 should feature 12 unique examples, items, or concepts directly related to the theme '{theme}'. DO NOT use months."


    # Base prompt structure for instructions and formatting
    # Updated to reflect singular/plural item types
    base_instructions = f"""
You are a creative TTRPG content writer specializing in quirky and humorous D&D-themed concepts. You MUST generate content in the EXACT format requested below.

Theme: "{theme}"

Generate a {slide_count_target}-slide TikTok carousel series based on this theme.
Slide 1 is the title card.
{specific_guideline}

**IMPORTANT GUIDELINES:**
*   **Avoid Clichés:** Do NOT rely on common stereotypes or generic themes (especially avoid holiday/seasonal clichés unless highly relevant and unique to the core theme).
*   **Focus on Theme:** The primary inspiration MUST be a unique, specific, and ideally humorous twist on the main theme: "{theme}".
*   **Be Creative & Specific:** Aim for unexpected combinations and subvert fantasy tropes in a D&D context.
*   **Output Format:** Strictly follow the slide format specified below for all {slide_count_target} slides.

For **each slide**, output EXACTLY like this, including the markdown and specific phrasing:

### 🏷️ **Slide [Number] – [{item_type_singular}]**
**visual:** (One sentence describing a unique retro-anime illustration appropriate for the slide's specific content. Avoid repeating the exact same character description across multiple slides unless contextually necessary.)
**The slide should have this exact text (don't add any other text):**
**[{item_type_singular} Name/Title]**
*[Witty/Funny Subtitle Related to Concept]*

---

Do not add extra explanations or conversational text.
"""

    chat_prompt_content = base_instructions # Already includes theme via f-string in base
    # --- End Prompt Structure Logic ---

    try:
        resp = openai.chat.completions.create(
            model="gpt-4o", # Using gpt-4o as requested
            messages=[
                {"role": "system", "content": f"You are a creative writer generating TikTok slide content for {slide_count_target} slides following a strict template and specific creative guidelines."},
                {"role": "user", "content": chat_prompt_content}
            ],
            temperature=0.9, # Increased temperature
        )
        generated_text = resp.choices[0].message.content
        print("✅ Text generation complete.")
        # Basic validation: Check if it looks like markdown segments are present
        if "---" not in generated_text or "visual:" not in generated_text:
             print("⚠️ Warning: Generated text format looks potentially incorrect.")
        return generated_text
    except Exception as e:
        print(f"⚠️ Text generation failed: {e}")
        return None # Indicate failure

# ------------- 4. Function to Parse Generated Text -------------
def parse_slides(md_block: str, expected_slides: int) -> list[dict]:
    """Parses the markdown block into a list of dictionaries, one per slide."""
    print("🧩 Parsing generated markdown using chunk splitting...")
    slides = []
    # Split the entire block into chunks based on the --- separator
    chunks = [chunk.strip() for chunk in md_block.split("---") if chunk.strip()]

    # Regex to find the visual description within a chunk
    visual_pattern = re.compile(r"\*\*visual:\*\*\s*(.*)", re.IGNORECASE)

    for i, chunk in enumerate(chunks):
        if i >= expected_slides: # Stop if we somehow find more chunks than expected
            print(f"⚠️ Found more than {expected_slides} chunks, stopping processing extra chunks.")
            break

        visual_match = visual_pattern.search(chunk)
        if not visual_match:
            print(f"⚠️ Could not find '**visual:**' in chunk {i+1}. Skipping.")
            continue

        visual_prompt = visual_match.group(1).strip()

        # Assume the text *after* the visual line is the slide text
        text_start_index = visual_match.end()
        slide_text_block = chunk[text_start_index:].strip()

        # Clean up potential leading markdown/newlines if the model format varies slightly
        # This now looks for the specific instruction line OR the first bold line as the start
        slide_text_block = re.sub(r"^(\s*\*\*The slide should have.*?\*\*\s*\n?)?", "", slide_text_block).strip()

        # Determine title/concept (looks for the first bold text after 'Slide X – ')
        title_match = re.search(r"Slide \d+ – \*\*(.*?)\*\*", chunk)
        slide_title = title_match.group(1).strip() if title_match else f"Item_{i+1}" # Fallback title

        # Ensure we actually got some slide text
        if not slide_text_block:
             print(f"⚠️ Found visual prompt but no slide text in chunk {i+1}. Skipping.")
             continue

        slides.append({
            "slide_number": i + 1,
            "month_or_title": slide_title, # Use the parsed title
            "visual_prompt": visual_prompt,
            "slide_text": slide_text_block
        })

    parsed_count = len(slides)
    print(f"✅ Parsed {parsed_count} slides.")
    if parsed_count != expected_slides:
        print(f"⚠️ Warning: Expected {expected_slides} slides, but parsed {parsed_count}. Check generated text format.")

    return slides


# ------------- 5. Function to Generate Image -------------
def make_image(theme: str, visual: str, slide_text: str, out_name_base: str) -> tuple[str | None, str | None]:
    """Calls OpenAI Image API for TWO images, saves them, returns tuple of paths (path1, path2) or (None, None)."""
    img_dir = pathlib.Path("images")
    img_dir.mkdir(exist_ok=True)
    # Define paths for both versions
    img_path_v1 = img_dir / f"{out_name_base}_v1.png"
    img_path_v2 = img_dir / f"{out_name_base}_v2.png"

    # --- Placeholder Generation (Generates two placeholders) ---
    if not OPENAI_API_KEY:
        print(f"ℹ️ Creating placeholder images for: {out_name_base}")
        placeholder_paths = []
        for i, img_path in enumerate([img_path_v1, img_path_v2]):
            try:
                img = Image.new("RGB", (1024, 1536), "#AAAAAA")
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("arial.ttf", size=60)
                except IOError:
                    font = ImageFont.load_default(size=60)
                lines = textwrap.wrap(slide_text, width=30)
                text_height_total = sum(font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines)
                y_start = (img.height - text_height_total) / 2
                for line in lines:
                     bbox = font.getbbox(line)
                     text_width = bbox[2] - bbox[0]
                     text_height = bbox[3] - bbox[1]
                     x = (img.width - text_width) / 2
                     draw.text((x, y_start), line, font=font, fill="#000000")
                     y_start += text_height * 1.2
                img.save(img_path, "PNG")
                print(f"   -> ✅ Saved placeholder {i+1}: {img_path}")
                placeholder_paths.append(str(img_path))
            except Exception as e:
                print(f"   -> ⚠️ Failed to create placeholder {i+1}: {e}")
                placeholder_paths.append(None)
        # Return tuple, ensuring it always has length 2
        path1 = placeholder_paths[0] if len(placeholder_paths) > 0 else None
        path2 = placeholder_paths[1] if len(placeholder_paths) > 1 else None
        return path1, path2
    # --- End Placeholder Generation ---

    print(f"🖼️ Requesting 2 image generations for: {out_name_base}...")

    # Construct the full, unique prompt for the image generator
    full_image_prompt = f"""
I want to make a slide for a series where the theme is "{theme}".
Can you make a 9:16 slide or tiktok in the following style:

Retro Sci-Fi Anime Aesthetic:
These images embody a vintage, nostalgic anime style typical of the late '70s and '80s sci-fi genre, reminiscent of classic anime movies and manga such as "Akira," "Gundam," or the works of artists like Moebius.

Limited Color Palette:
They employ muted, pastel-like colors and warm earth tones (soft yellows, oranges, beige) complemented by contrasting darker outlines. This creates a distinctive retro feel and evokes an atmosphere of warmth and nostalgia.

Strong Outlines & Detailed Line Work:
The artwork uses defined, bold outlines and careful, detailed linework, capturing meticulous textures and shading, particularly noticeable in mechanical or robotic details.

Minimalistic Backgrounds & Composition:
Backgrounds are often minimalistic, focusing attention primarily on the characters, creatures, or machines featured prominently. This helps to emphasize the subjects clearly.

Cross-cultural Influences:
There's a visible influence from both Japanese manga/anime traditions and European comic aesthetics (especially Franco-Belgian comics), particularly in terms of character design, facial structures, and clothing styles.

Instructions for this specific image:
1) make sure its dnd and not futuristic
2) make sure the text specified below is centered clearly on the image

visual: {visual}

The slide should have this exact text (don't add any other text):
{slide_text}
    """

    generated_paths = []
    try:
        resp = openai.images.generate(
            model="gpt-image-1",
            prompt=full_image_prompt,
            n=2, # Generate two images
            size="1024x1536",
            quality="high",
        )
        # Process both images in the response
        for i, img_data in enumerate(resp.data):
            img_path = img_path_v1 if i == 0 else img_path_v2
            try:
                b64_data = img_data.b64_json
                img_bytes = base64.b64decode(b64_data)
                with open(img_path, "wb") as f:
                    f.write(img_bytes)
                print(f"   -> ✅ Saved image {i+1}: {img_path}")
                generated_paths.append(str(img_path))
            except Exception as save_e:
                 print(f"   -> ⚠️ Failed to save image {i+1}: {save_e}")
                 generated_paths.append(None)

    except openai.BadRequestError as e:
         print(f"❌ Image Generation Failed (Bad Request): {e}")
         print(f"   Problematic visual prompt part: '{visual}'")
         print("   Creating placeholder images instead.")
         # Attempt to create 2 placeholders on bad request
         return make_image(theme, visual, slide_text, out_name_base) # Re-call self in placeholder mode

    except Exception as e:
        print(f"⚠️ Image generation failed: {e}")
        print(f"   Visual prompt part: '{visual}'")
        print("   Creating placeholder images instead.")
        # Attempt to create 2 placeholders on other errors
        return make_image(theme, visual, slide_text, out_name_base) # Re-call self in placeholder mode

    # Return tuple, ensuring length 2
    path1 = generated_paths[0] if len(generated_paths) > 0 else None
    path2 = generated_paths[1] if len(generated_paths) > 1 else None
    return path1, path2


# ------------- 6. Google Drive Functions -------------
def get_drive_service():
    """Gets authenticated Google Drive service object."""
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"⚠️ Failed to refresh Google token: {e}. Deleting token and re-authenticating.")
                os.remove(TOKEN_PATH)
                creds = None
        if not creds:
             if not os.path.exists(CREDS_PATH):
                 print(f"❌ Google credentials file not found: {CREDS_PATH}")
                 print("   Please download it from Google Cloud Console and place it here.")
                 return None
             flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
             creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)
    try:
        service = build('drive', 'v3', credentials=creds)
        print("✅ Google Drive API service created.")
        return service
    except HttpError as error:
        print(f"❌ An error occurred creating Google Drive service: {error}")
        return None
    except Exception as e:
        print(f"❌ An unexpected error occurred creating Google Drive service: {e}")
        return None

def find_or_create_folder(service, folder_name, parent_folder_id):
    """Finds a folder by name within a parent folder, or creates it if not found."""
    if not service:
        return None
    # Sanitize folder name slightly for Drive API (avoiding some problematic chars)
    safe_folder_name = re.sub(r'[\\"]', '', folder_name) # Remove backslash and double quote
    if not safe_folder_name:
         print(f"⚠️ Invalid theme '{folder_name}' resulted in empty safe name. Skipping folder creation.")
         return None
    try:
        query = f"name='{safe_folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_folder_id}' in parents and trashed=false"
        response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        folders = response.get('files', [])
        if folders:
            folder_id = folders[0].get('id')
            print(f"📁 Found existing folder: '{safe_folder_name}' (ID: {folder_id})")
            return folder_id
        else:
            print(f"📁 Folder '{safe_folder_name}' not found, creating...")
            file_metadata = {
                'name': safe_folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id]
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
            print(f"✅ Created folder: '{safe_folder_name}' (ID: {folder_id})")
            return folder_id
    except HttpError as error:
        print(f"❌ An error occurred finding/creating folder '{safe_folder_name}': {error}")
        return None
    except Exception as e:
        print(f"❌ An unexpected error occurred finding/creating folder '{safe_folder_name}': {e}")
        return None

def upload_image_to_drive(service, local_image_path, target_folder_id):
    """Uploads a locally generated image to the specified Google Drive folder."""
    if not service or not target_folder_id:
        print("   -> Skipping Google Drive upload (service or folder ID missing).")
        return
    if not local_image_path: # Check if path is None or empty
        print(f"   -> Skipping Google Drive upload (invalid local image path).")
        return

    file_path = pathlib.Path(local_image_path)
    if not file_path.is_file():
        print(f"   -> Skipping Google Drive upload ('{local_image_path}' not found).")
        return

    print(f"   -> Uploading '{file_path.name}' to Google Drive...")
    try:
        file_metadata = {
            'name': file_path.name,
            'parents': [target_folder_id]
        }
        media = MediaFileUpload(str(file_path), mimetype='image/png', resumable=True)
        request = service.files().create(body=file_metadata, media_body=media, fields='id')
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"      Uploaded {int(status.progress() * 100)}%")
        print(f"   -> ✅ Successfully uploaded '{file_path.name}' (ID: {response.get('id')})")

    except HttpError as error:
        print(f"   -> ❌ An error occurred uploading '{file_path.name}': {error}")
    except Exception as e:
         print(f"   -> ❌ An unexpected error occurred uploading '{file_path.name}': {e}")

# ------------- 7. Main Execution Logic (Batch Processing) ------------- # Renumbered
PROCESSED_THEMES_FILE = "processed_themes.txt"

def load_processed_themes():
    """Loads already processed themes from the tracking file."""
    processed = set()
    if os.path.exists(PROCESSED_THEMES_FILE):
        try:
            with open(PROCESSED_THEMES_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    processed.add(line.strip())
            print(f"ℹ️ Loaded {len(processed)} themes from {PROCESSED_THEMES_FILE}")
        except Exception as e:
             print(f"⚠️ Warning: Failed to read {PROCESSED_THEMES_FILE}: {e}")
    return processed

def mark_theme_as_processed(theme):
    """Appends a successfully processed theme to the tracking file."""
    try:
        with open(PROCESSED_THEMES_FILE, 'a', encoding='utf-8') as f:
             f.write(theme + '\n')
        print(f"   -> Marked '{theme}' as processed.")
    except Exception as e:
        print(f"⚠️ Warning: Failed to write '{theme}' to {PROCESSED_THEMES_FILE}: {e}")

def main():
    """Main function to read themes from CSV, process a limited number, and track completion."""

    themes_csv_path = pathlib.Path("themes_to_generate.csv")
    if not themes_csv_path.is_file():
        print(f"❌ Themes input file not found: {themes_csv_path}")
        print("   Please create it with a header 'Theme' and list themes below.")
        return

    # --- Load Themes and Filter Processed --- 
    processed_themes = load_processed_themes()
    themes_to_process = []
    try:
        with themes_csv_path.open('r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            if 'Theme' not in reader.fieldnames:
                 print("❌ CSV file must contain a header named 'Theme'.")
                 return
            # Read all themes first
            all_themes_in_csv = [row['Theme'].strip() for row in reader if row['Theme'].strip()]
            # Filter out already processed themes
            themes_to_process = [theme for theme in all_themes_in_csv if theme not in processed_themes]

    except Exception as e:
        print(f"❌ Failed to read themes from {themes_csv_path}: {e}")
        return

    if not themes_to_process:
        print("ℹ️ No *new* themes found in themes_to_generate.csv to process.")
        return

    print(f"Found {len(themes_to_process)} new themes to process: {themes_to_process}")

    # --- Ask for Limit --- 
    limit_str = input(f"Enter max themes to process this run (out of {len(themes_to_process)} new themes, press Enter for all): ").strip()
    limit = None
    try:
        if limit_str:
             limit_val = int(limit_str)
             if limit_val > 0:
                  limit = limit_val
                  print(f"   -> Processing limit set to {limit} themes.")
             else:
                  print("   -> Invalid limit, processing all new themes.")
        else:
            print("   -> No limit entered, processing all new themes.")
    except ValueError:
        print("   -> Invalid input, processing all new themes.")

    if limit is not None:
        themes_to_run_now = themes_to_process[:limit]
    else:
        themes_to_run_now = themes_to_process

    if not themes_to_run_now:
         print("ℹ️ No themes selected to run in this session.")
         return

    print(f"\nSelected {len(themes_to_run_now)} themes for this run: {themes_to_run_now}")
    # --- End Limit Logic ---

    # --- Initialize Google Drive Service (Once for the batch) ---
    drive_service = None
    if GOOGLE_DRIVE_FOLDER_ID:
        print("-" * 30)
        print("ℹ️ Initializing Google Drive connection...")
        drive_service = get_drive_service()
        if not drive_service:
             print("⚠️ Failed to get Google Drive service. Uploads will be skipped for all themes.")
        print("-" * 30)
    else:
         print("ℹ️ Google Drive Folder ID not set in config.env. Skipping all uploads.")
         print("-" * 30)

    # --- Process Each Selected Theme --- 
    processed_in_this_run_count = 0
    for theme_index, theme in enumerate(themes_to_run_now):
        print(f"\n===== Processing Theme {theme_index+1}/{len(themes_to_run_now)}: '{theme}' =====")
        theme_successfully_processed = False # Flag to track success for this theme

        # Sanitize theme name for use in filenames
        safe_theme_name = re.sub(r'[\\\\/*?:\"<>|]', "", theme).replace(" ", "_")
        if len(safe_theme_name) > 50:
             safe_theme_name = safe_theme_name[:50]

        try:
            # --- Theme-specific Google Drive Folder ---
            theme_folder_id = None
            if drive_service and GOOGLE_DRIVE_FOLDER_ID:
                theme_folder_id = find_or_create_folder(drive_service, theme, GOOGLE_DRIVE_FOLDER_ID)
                if not theme_folder_id:
                     print("⚠️ Could not find or create theme folder in Google Drive. Uploads will be skipped for this theme.")

            # 1. Generate the text block
            markdown_block = generate_slides_text(theme)
            if not markdown_block:
                 print("❌ Text generation skipped or failed. Cannot proceed with this theme.")
                 continue

            print("\n--- Raw Generated Markdown Block ---")
            print(markdown_block[:1000] + "... (truncated)" if len(markdown_block) > 1000 else markdown_block)
            print("--- End Raw Markdown Block ---\n")

            # Determine expected slides based on theme type (again, for parsing check)
            expected_slides = 14 if ("class" in theme.lower() or "classes" in theme.lower()) else 13

            # 2. Parse the text block into structured slide data
            parsed_slide_data = parse_slides(markdown_block, expected_slides)
            if not parsed_slide_data:
                print("❌ Failed to parse slides from generated text. Cannot proceed with this theme.")
                continue

            # 3. Generate images (2 per slide), upload to Drive, and collect data for CSV
            final_slide_rows = []
            print("-" * 30)
            print("⏳ Starting image generation & upload loop...")
            all_images_generated = True # Track if all images were generated ok
            for slide in parsed_slide_data:
                slide_num = slide['slide_number']
                slide_title = slide['month_or_title']
                visual_prompt = slide['visual_prompt']
                slide_text = slide['slide_text']

                # Generate filename base (without _v1/_v2)
                safe_slide_title = re.sub(r'[\\\\/*?:\"<>|]', "", slide_title).replace(" ", "_")
                filename_base = f"{slide_num:02d}_{safe_slide_title}"

                # Generate two image versions
                local_image_path_v1, local_image_path_v2 = make_image(theme, visual_prompt, slide_text, filename_base)
                if not local_image_path_v1 or not local_image_path_v2:
                     all_images_generated = False # Mark failure if any image pair fails

                # Upload both versions to Google Drive if possible
                if drive_service and theme_folder_id:
                    upload_image_to_drive(drive_service, local_image_path_v1, theme_folder_id)
                    upload_image_to_drive(drive_service, local_image_path_v2, theme_folder_id)

                # Add data to list for CSV writing
                final_slide_rows.append({
                    "theme": theme,
                    "slide_number": slide_num,
                    "month_or_title": slide_title,
                    "visual_prompt": visual_prompt,
                    "slide_text": slide_text,
                    "image_file_v1": local_image_path_v1 if local_image_path_v1 else "GENERATION_FAILED",
                    "image_file_v2": local_image_path_v2 if local_image_path_v2 else "GENERATION_FAILED"
                })
                print("-" * 10)
                time.sleep(1)

            print("✅ Image generation & upload loop complete for theme.")
            print("-" * 30)

            # 4. Write data to theme-specific CSV
            csv_filename = f"slides_{safe_theme_name}.csv"
            csv_path = pathlib.Path(csv_filename)
            print(f"💾 Writing data to {csv_path}...")
            try:
                with csv_path.open("w", newline="", encoding="utf-8") as f:
                    fieldnames = ["theme", "slide_number", "month_or_title", "visual_prompt", "slide_text", "image_file_v1", "image_file_v2"]
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(final_slide_rows)
                print(f"✅ Successfully wrote {len(final_slide_rows)} rows to {csv_path.resolve()}")
                # If CSV write is successful, mark the theme as processed
                if all_images_generated: # Only mark if images seemed okay
                     theme_successfully_processed = True
                else:
                     print("⚠️ Theme processed, but some images failed generation. Not marking as fully processed.")

            except Exception as e:
                print(f"⚠️ Failed to write CSV file '{csv_filename}': {e}")
                # Do not mark as processed if CSV writing fails

        except Exception as theme_e:
             print(f"❌❌❌ An unexpected error occurred processing theme '{theme}': {theme_e}")
             print("      Moving to the next theme.")
             # Do not mark as processed if a major error occurs

        # --- Mark Theme as Processed (if successful) ---
        if theme_successfully_processed:
            mark_theme_as_processed(theme)
            processed_in_this_run_count += 1

        print(f"===== Finished processing theme: '{theme}' =====")
        # Add a delay only if there are more themes to process
        if theme_index < len(themes_to_run_now) - 1:
            print("   -> Waiting 5 seconds before next theme...")
            time.sleep(5)

    # --- End Theme Loop ---

    print(f"\n🎉 Batch script finished! Processed {processed_in_this_run_count} themes successfully in this run. 🎉")

# ------------- 8. Run the main function ------------- # Renumbered
if __name__ == "__main__":
    main()