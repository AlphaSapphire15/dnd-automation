import base64
import csv
import os
import pathlib
import re
import textwrap
import json
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont # Import ImageDraw and ImageFont from Pillow
import time

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

# --- NEW: Prompting Constants ---
HOST_INDEX_FILE = "host_index.json"
HOSTS = [
    "Bald Guy (ragged linen, brown pants, baffled hero)",
    "Astra the Tiefling Bard (violet ponytail, starry coat, silver lute)",
    "Rook the Half-Orc Chef/Barbarian (braided top-knot, iron skillet axe)",
    "Fizz the Gnome Artificer (teal pigtails, copper goggles, clockwork squirrel)"
]
NEGATIVE_MONTH = {
    "february": "NO hearts, NO love clichés – lean into awkward tax season or break-up ballads.",
    "march":    "NO shamrocks, NO leprechauns – evoke early spring in unexpected ways.",
    "april":    "NO Easter eggs or bunny clichés – April Fool illusions are okay if original.",
    "july":     "NO fireworks, NO flag tropes – maybe a runaway barbecue mimic, but surprise us.",
    "october":  "NO pumpkins, NO ghosts – give us unexpected autumn weirdness instead.",
    "november": "NO turkeys, NO Thanksgiving dinner jokes – gravy elementals are okay if ironic.",
    "december": "NO Santa, NO reindeer, NO snow-globe puns – winter solstice oddities welcome."
}
TITLE_WORD_CAP = "CRITICAL: Title line must be ≤ 7 words. Subtitle line must be ≤ 10 words."
TITLE_EXAMPLE = """**GOLD STANDARD EXAMPLE (Format & Tone):**
**Druid – Living Herbology Atlas**
*Leaves leaf. Also leaves soil on furniture.*"""
JOKE_INSTRUCTION = """**COMEDY & SPECIFICITY RULES:**
▪️ EVERY slide must land a punch line (surprise, understatement, or absurd reversal).
▪️ NEVER default to seasonal clichés (no hearts in Feb, no pumpkins in Oct) – surprise us instead.
▪️ Think "highly specific micro-scenes" (one object mis-used in a ridiculous way).
▪️ Slide 1 visual: Feature the host doing something ironic/comedic related to the theme.
▪️ Slide 1 text: MUST be a hook/gag setting the vibe, not just an announcement."""
# --- END: Prompting Constants ---

if not OPENAI_API_KEY:
    print("⚠️  No OPENAI_API_KEY found in config.env – using placeholders.")
else:
    try:
        import openai
        openai.api_key = OPENAI_API_KEY
        print("✅ OpenAI API key loaded.")
    except ImportError:
        print("⚠️ OpenAI library not installed. Run 'py -m pip install openai'")
        OPENAI_API_KEY = None # Ensure key is treated as missing

if not GOOGLE_DRIVE_FOLDER_ID:
    print("⚠️  No GOOGLE_DRIVE_FOLDER_ID found in config.env – Google Drive upload disabled.")


# ------------- 2. Define Your Art Style Prompt Components (REMOVED GLOBAL ART_STYLE) -------------
# The art style description will be combined dynamically later

# ------------- 3. Function to Generate Slide Text -------------
def generate_slides_text(theme: str, host: str) -> str:
    """Calls OpenAI Chat API to generate the slide text descriptions, adapting to theme type."""
    if not OPENAI_API_KEY:
        print("ℹ️ Skipping text generation (no API key). Returning placeholder markdown.")
        # Basic placeholder generation remains the same
        placeholder_md = "### 🏷️ **Slide 1 – Title Card**\n**visual:** Placeholder visual for title featuring {host}\n**The slide should have this exact text (don't add any other text):**\nPlaceholder Title\n*Placeholder subtitle*\n\n---\n\n"
        for i, month in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], start=2):
            placeholder_md += f"### 💀 **Slide {i} – {month}**\n**visual:** Placeholder visual for {month}\n**The slide should have this exact text (don't add any other text):**\n**{month} – Placeholder Item**\n*Placeholder detail*\n\n---\n\n"
        return placeholder_md

    print(f"📝 Requesting slide text generation for theme: '{theme}' (Host: {host})...")

    # --- Determine Prompt Structure based on Theme ---
    is_month_theme = False
    theme_lower = theme.lower()

    if "month" in theme_lower or "birth month" in theme_lower:
        is_month_theme = True
        print("   -> Detected month-based theme (13 slides)." )
        slide_count_target = 13
        item_type_plural = "months (Jan-Dec)"
        item_type_singular = "Month/Title"
        specific_guideline = "Slides 2-13 correspond to January-December."
    elif "class" in theme_lower or "classes" in theme_lower:
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

    # --- Build Negative Month Notes (if applicable) ---
    neg_month_notes = ""
    if is_month_theme:
        notes_list = []
        for m, rule in NEGATIVE_MONTH.items():
            notes_list.append(f"▪️ {m.capitalize()}: {rule}")
        if notes_list:
             neg_month_notes = "\n\n### Holiday-Autopilot Guardrails:\n" + "\n".join(notes_list)

    # --- Assemble the Full Prompt --- 
    base_instructions = f"""
You are an expert TTRPG content writer known for exceptionally creative, specific, and genuinely funny D&D-themed TikTok concepts. Your primary goal is to generate highly engaging and shareable slide content based on the theme: "{theme}". Adhere strictly to the format below.

**Core Task:** Generate a {slide_count_target}-slide TikTok carousel series.
*   Slide 1 MUST be a captivating Title Card setting the scene, featuring **{host}** as the on-screen narrator in the visual description.
*   {specific_guideline}

{TITLE_EXAMPLE}

{JOKE_INSTRUCTION}

{TITLE_WORD_CAP}
# --- NEW Tweaks Start --- #
▪️ Every subtitle must contain either a food pun **or** an unexpected combat reference.
▪️ For themes involving race/class + item fusion (like Desserts as Races), the concept name MUST fuse an official 5e race/class word (Elf, Dwarf, Tiefling, Barbarian etc.) with the item/dessert word.
# --- NEW Tweaks End --- #
{neg_month_notes}

**CRITICAL OUTPUT FORMATTING FOR *EVERY* SLIDE (INCLUDING SLIDE 1):**
*   Output *only* in the format below. No extra conversation, explanations, or deviations.
*   Use markdown `###` for slide headers.
*   Use `---` as a separator ONLY between slides.

### 🏷️ **Slide [Number] – [{item_type_singular}]**
**visual:** (A *highly detailed*, one-sentence description of a unique retro-anime illustration capturing the specific concept below. Be vivid, specific, and avoid repeating visual elements unless essential. **For Slide 1, MUST feature {host}.**)
**The slide should have this exact text (don't add any other text):**
**[{item_type_singular} Name] – [Specific, Creative Concept Title]**
*Genuinely Funny/Witty Subtitle Directly Related to the Title Concept*

---

**REMINDER: For *every* slide (1 through {slide_count_target}), include `**The slide should have this exact text...**` followed by the TWO lines of text (Bold Title, Italic Subtitle) adhering to the word count limits.**
"""

    chat_prompt_content = base_instructions
    # --- End Prompt Assembly ---

    try:
        resp = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a creative, funny TTRPG TikTok content writer following a strict template, specific creative guidelines, and word count limits."},
                {"role": "user", "content": chat_prompt_content}
            ],
            temperature=1.05, # Increased temperature
            timeout=60,      # Added timeout
        )
        generated_text = resp.choices[0].message.content
        print("✅ Text generation complete.")
        return generated_text
    except Exception as e:
        print(f"⚠️ Text generation failed: {e}")
        print("ℹ️ Returning placeholder markdown due to error.")
        # Fallback uses basic placeholder generator now
        return generate_slides_text(theme, host) # Pass host to placeholder fallback


# ------------- 4. Function to Parse Generated Text -------------
def parse_slides(md_block: str, expected_slides: int) -> list[dict]:
    """Parses the markdown block into a list of dictionaries, one per slide."""
    print("🧩 Parsing generated markdown using chunk splitting...")
    slides = []
    # Split the entire block into chunks based on the --- separator
    chunks = [chunk.strip() for chunk in md_block.split("---") if chunk.strip()]

    # Regex to find the visual description within a chunk
    visual_pattern = re.compile(r"\*\*visual:\*\*\s*(.*)", re.IGNORECASE)
    # REMOVED: Regex to find the exact slide text block (as the model isn't consistent)
    # text_pattern = re.compile(r"\*\*The slide should have this exact text.*?\*\*\s*\n?(.*)", re.IGNORECASE | re.DOTALL)

    for i, chunk in enumerate(chunks):
        if i >= expected_slides: # Stop if we somehow find more than expected slides
            print(f"⚠️ Found more than {expected_slides} chunks, stopping at {expected_slides}.")
            break

        visual_match = visual_pattern.search(chunk)
        # REMOVED: text_match = text_pattern.search(chunk)

        if not visual_match:
            print(f"⚠️ Could not find '**visual:**' in chunk {i+1}. Skipping.")
            continue
        # REMOVED: Check for text_match

        visual_prompt = visual_match.group(1).strip()

        # Assume the text *after* the visual line is the slide text
        # Find the end position of the visual match to split the chunk
        text_start_index = visual_match.end()
        slide_text_block = chunk[text_start_index:].strip()

        # Clean up potential leading markdown/newlines if the model format varies slightly
        slide_text_block = re.sub(r"^\s*\*\*.*?\*\*\s*\n?", "", slide_text_block).strip()

        # Determine month/title (using a simpler pattern that looks for the first bold text after 'Slide X – ')
        month_title_match = re.search(r"Slide \d+ – \*\*(.*?)\*\*", chunk)
        month_or_title = month_title_match.group(1).strip() if month_title_match else f"Slide_{i+1}"

        # Ensure we actually got some slide text
        if not slide_text_block:
             print(f"⚠️ Found visual prompt but no slide text in chunk {i+1}. Skipping.")
             continue

        slides.append({
            "slide_number": i + 1,
            "month_or_title": month_or_title,
            "visual_prompt": visual_prompt,
            "slide_text": slide_text_block
        })

    print(f"✅ Parsed {len(slides)} slides.")
    if len(slides) != expected_slides:
        print(f"⚠️ Warning: Expected {expected_slides} slides, but parsed {len(slides)}. Check generated text format.")

    return slides


# ------------- 5. Function to Generate Image -------------
# Updated to accept slide_text and construct the full prompt dynamically
def make_image(theme: str, visual: str, slide_text: str, out_name: str) -> str | None:
    """Calls OpenAI Image API to generate an image with specific text, saves it, returns the path or None on failure."""
    img_dir = pathlib.Path("images")
    img_dir.mkdir(exist_ok=True)
    # Define paths for both versions
    img_path_v1 = img_dir / f"{out_name}_v1.png"
    img_path_v2 = img_dir / f"{out_name}_v2.png"

    # --- Placeholder Generation (Generates two placeholders) ---
    if not OPENAI_API_KEY:
        print(f"ℹ️ Creating placeholder images: {img_path_v1}, {img_path_v2}")
        placeholder_path_v1 = None
        placeholder_path_v2 = None # Generate placeholder v2 as well
        try:
            img = Image.new("RGB", (1024, 1536), "#AAAAAA") # Use the target size
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("arial.ttf", size=60)
            except IOError:
                font = ImageFont.load_default(size=60) # Fallback font
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

            # Save V1 placeholder
            img.save(img_path_v1, "PNG")
            print(f"   -> ✅ Saved placeholder image v1: {img_path_v1}")
            placeholder_path_v1 = str(img_path_v1)

            # Save V2 placeholder (identical for simplicity)
            img.save(img_path_v2, "PNG")
            print(f"   -> ✅ Saved placeholder image v2: {img_path_v2}")
            placeholder_path_v2 = str(img_path_v2)

        except Exception as e:
            print(f"⚠️ Failed to create placeholder image with text: {e}")
            # Try basic placeholders if advanced failed
            try:
                 Image.new("RGB", (300, 450), "#AAAAAA").save(img_path_v1, "PNG")
                 placeholder_path_v1 = str(img_path_v1)
                 print(f"   -> ✅ Saved basic placeholder v1: {img_path_v1}")
            except Exception as e_inner:
                 print(f"   -> ⚠️ Failed to create basic placeholder image v1: {e_inner}")
            try:
                 Image.new("RGB", (300, 450), "#AAAAAA").save(img_path_v2, "PNG")
                 placeholder_path_v2 = str(img_path_v2)
                 print(f"   -> ✅ Saved basic placeholder v2: {img_path_v2}")
            except Exception as e_inner:
                 print(f"   -> ⚠️ Failed to create basic placeholder image v2: {e_inner}")

        # Return tuple of paths (or None if failed)
        return placeholder_path_v1, placeholder_path_v2

    print(f"🖼️ Requesting 2 image generations for: {out_name}...")

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
            model="gpt-image-1", # Reverted back to gpt-image-1 as requested
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
                 generated_paths.append("IMG_GEN_FAILED") # Use sentinel on save failure

    except openai.BadRequestError as e:
         print(f"❌ Image Generation Failed (Bad Request): {e}")
         print(f"   Problematic visual prompt part: '{visual}'")
         print("   Skipping image generation for this slide.")
         return "IMG_GEN_FAILED", "IMG_GEN_FAILED" # Return sentinels on API error

    except Exception as e:
        print(f"⚠️ Image generation failed: {e}")
        print(f"   Visual prompt part: '{visual}'")
        print("   Skipping image generation for this slide.")
        return "IMG_GEN_FAILED", "IMG_GEN_FAILED" # Return sentinels on API error

    # Return tuple, ensuring length 2
    path1 = generated_paths[0] if len(generated_paths) > 0 else "IMG_GEN_FAILED"
    path2 = generated_paths[1] if len(generated_paths) > 1 else "IMG_GEN_FAILED"
    # Handle cases where only one image was successfully saved from the API response
    if len(generated_paths) == 1:
        path2 = "IMG_GEN_FAILED"

    return path1, path2


# ------------- 6. Google Drive Functions -------------

def get_drive_service():
    """Gets authenticated Google Drive service object."""
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"⚠️ Failed to refresh Google token: {e}. Deleting token and re-authenticating.")
                os.remove(TOKEN_PATH)
                creds = None # Force re-authentication
        if not creds: # Re-authenticate if refresh failed or no token existed
             if not os.path.exists(CREDS_PATH):
                 print(f"❌ Google credentials file not found: {CREDS_PATH}")
                 print("   Please download it from Google Cloud Console and place it here.")
                 return None
             flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
             # Run flow using a local server to handle the redirect
             creds = flow.run_local_server(port=0) # Use port=0 to find a free port
        # Save the credentials for the next run
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)

    try:
        service = build('drive', 'v3', credentials=creds)
        print("✅ Google Drive API service created.")
        return service
    except HttpError as error:
        print(f'❌ An error occurred creating Google Drive service: {error}')
        return None
    except Exception as e:
        print(f'❌ An unexpected error occurred creating Google Drive service: {e}')
        return None

def find_or_create_folder(service, folder_name, parent_folder_id):
    """Finds a folder by name within a parent folder, or creates it if not found."""
    if not service:
        return None
    try:
        # Escape single quotes for the query string itself
        # Use double backslash to ensure a literal backslash is in the query string
        escaped_folder_name = folder_name.replace("'", "\\'")
        # Also remove problematic characters for the folder name itself if creating
        safe_folder_name_for_creation = re.sub(r'[\\/"]', '', folder_name)

        # Search for the folder
        query = f"name='{escaped_folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_folder_id}' in parents and trashed=false"
        response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        folders = response.get('files', [])

        if folders:
            folder_id = folders[0].get('id')
            print(f"📁 Found existing folder: '{folder_name}' (ID: {folder_id})")
            return folder_id
        else:
            # Create the folder
            print(f"📁 Folder '{folder_name}' not found, creating...")
            file_metadata = {
                'name': safe_folder_name_for_creation,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id]
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
            print(f"✅ Created folder: '{folder_name}' (ID: {folder_id})")
            return folder_id
    except HttpError as error:
        print(f"❌ An error occurred finding/creating folder '{folder_name}': {error}")
        return None
    except Exception as e:
        print(f"❌ An unexpected error occurred finding/creating folder '{folder_name}': {e}")
        return None


def upload_image_to_drive(service, local_image_path, target_folder_id):
    """Uploads a locally generated image to the specified Google Drive folder."""
    if not local_image_path: # Check if path is None or empty FIRST
        print(f"   -> Skipping Google Drive upload (invalid local image path provided: {local_image_path}).")
        return

    if not service or not target_folder_id:
        print("   -> Skipping Google Drive upload (service or folder ID missing).")
        return

    file_path = pathlib.Path(local_image_path)
    if not file_path.is_file():
        print(f"   -> Skipping Google Drive upload ('{local_image_path}' not found).")
        return

    try:
        file_metadata = {
            'name': file_path.name,
            'parents': [target_folder_id]
        }
        media = MediaFileUpload(str(file_path), mimetype='image/png')
        file = service.files().create(body=file_metadata,
                                      media_body=media,
                                      fields='id').execute()
        print(f"   -> ✅ Successfully uploaded '{file_path.name}' to Google Drive (ID: {file.get('id')})")
    except HttpError as error:
        print(f"   -> ❌ An error occurred uploading '{file_path.name}' to Google Drive: {error}")
    except Exception as e:
         print(f"   -> ❌ An unexpected error occurred uploading '{file_path.name}' to Google Drive: {e}")

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

    # --- Get Host Rotation Index ---
    current_host_index = 0
    try:
        if os.path.exists(HOST_INDEX_FILE):
            with open(HOST_INDEX_FILE, 'r') as f:
                data = json.load(f)
                current_host_index = int(data.get('host_index', 0))
        else:
             print(f"ℹ️ Host index file ({HOST_INDEX_FILE}) not found, starting from index 0.")
    except (json.JSONDecodeError, ValueError, IOError) as e:
        print(f"⚠️ Error reading host index file ({HOST_INDEX_FILE}): {e}. Resetting to index 0.")
        current_host_index = 0

    # Increment and save for next run
    next_host_index = current_host_index + 1
    try:
        with open(HOST_INDEX_FILE, 'w') as f:
            json.dump({'host_index': next_host_index}, f)
    except IOError as e:
        print(f"⚠️ Could not write updated host index to {HOST_INDEX_FILE}: {e}")
    # --- End Host Rotation Index ---

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
        theme_successfully_processed = True # Assume success initially for the theme
        outer_theme_error = False # Flag for unrecoverable theme errors

        # --- Select Host for this theme ---
        # Use the index loaded *before* the loop started
        host = HOSTS[ current_host_index % len(HOSTS) ]
        print(f"   -> Narrator for title card: {host}")
        # --- End Select Host ---

        # Sanitize theme name for use in filenames
        # CORRECTED REGEX: Remove forbidden characters
        safe_theme_name = re.sub(r'[\\\\/*?:"<>|]', "", theme).replace(" ", "_")
        if len(safe_theme_name) > 50:
             safe_theme_name = safe_theme_name[:50]

        try:
            # --- Theme-specific Google Drive Folder ---
            theme_folder_id = None
            if drive_service and GOOGLE_DRIVE_FOLDER_ID:
                # Wrap folder finding/creation in try-except to prevent fatal error
                try:
                    theme_folder_id = find_or_create_folder(drive_service, theme, GOOGLE_DRIVE_FOLDER_ID)
                    if not theme_folder_id:
                         print("⚠️ Could not find or create theme folder in Google Drive. Uploads will be skipped for this theme.")
                except Exception as folder_e:
                    print(f"❌ Error setting up Google Drive folder for theme '{theme}': {folder_e}. Uploads disabled.")
                    # Allow processing to continue without uploads for this theme

            # 1. Generate the text block
            markdown_block = None
            try:
                markdown_block = generate_slides_text(theme, host)
                if not markdown_block:
                     print("❌ Text generation skipped or returned empty. Cannot proceed with this theme.")
                     outer_theme_error = True # Mark as fatal for this theme
                     continue # Move to the next theme in the loop
            except Exception as text_gen_e:
                 print(f"❌ Text generation failed with error: {text_gen_e}. Cannot proceed with this theme.")
                 outer_theme_error = True
                 continue

            print("\n--- Raw Generated Markdown Block ---")
            print(markdown_block[:1000] + "... (truncated)" if len(markdown_block) > 1000 else markdown_block)
            print("--- End Raw Markdown Block ---\n")

            # Determine expected slides based on theme type (matching logic in generator)
            theme_lower_main = theme.lower() # Use a different variable name to avoid scope issues
            if "month" in theme_lower_main or "birth month" in theme_lower_main:
                expected_slides = 13
            elif "class" in theme_lower_main or "classes" in theme_lower_main:
                expected_slides = 14
            else:
                expected_slides = 13

            # 2. Parse the text block into structured slide data
            parsed_slide_data = None
            try:
                parsed_slide_data = parse_slides(markdown_block, expected_slides)
                if not parsed_slide_data:
                    print("❌ Failed to parse slides from generated text. Cannot proceed with this theme.")
                    outer_theme_error = True
                    continue # Move to the next theme
            except Exception as parse_e:
                print(f"❌ Failed to parse slides with error: {parse_e}. Cannot proceed with this theme.")
                outer_theme_error = True
                continue

            # 3. Generate images (2 per slide), upload to Drive, and collect data for CSV
            final_slide_rows = []
            print("-" * 30)
            print("⏳ Starting image generation & upload loop...")
            any_slide_failed = False # Track if ANY slide had issues

            for slide in parsed_slide_data:
                slide_num = slide['slide_number']
                slide_title = slide['month_or_title']
                visual_prompt = slide['visual_prompt']
                slide_text = slide['slide_text']
                print(f"--- Processing Slide {slide_num} ('{slide_title}') ---")

                local_image_path_v1 = None
                local_image_path_v2 = None
                slide_generation_failed = False

                try:
                    # Generate filename base (without _v1/_v2)
                    # CORRECTED REGEX: Remove forbidden characters
                    safe_slide_title = re.sub(r'[\\\\/*?:"<>|]', "", slide_title).replace(" ", "_")
                    if not safe_slide_title: # Handle cases where title becomes empty
                        safe_slide_title = f"Slide_{slide_num}_Title"
                    filename_base = f"{slide_num:02d}_{safe_slide_title}"

                    # Generate two image versions - WRAP IN TRY/EXCEPT
                    try:
                        local_image_path_v1, local_image_path_v2 = make_image(theme, visual_prompt, slide_text, filename_base)
                    except Exception as img_gen_e:
                         print(f"   -> ❌❌ CRITICAL ERROR during image generation call for slide {slide_num}: {img_gen_e}")
                         local_image_path_v1 = "IMG_GEN_FAILED" # Ensure sentinels on unexpected error
                         local_image_path_v2 = "IMG_GEN_FAILED"

                    # Check if generation returned sentinels
                    if local_image_path_v1 == "IMG_GEN_FAILED":
                         print(f"   -> ⚠️ Image v1 generation/saving failed for slide {slide_num}.")
                         any_slide_failed = True
                    if local_image_path_v2 == "IMG_GEN_FAILED":
                         print(f"   -> ⚠️ Image v2 generation/saving failed for slide {slide_num}.")
                         any_slide_failed = True # Mark theme as partially failed if v2 fails too

                    # Upload both versions to Google Drive if possible - WRAP EACH UPLOAD
                    if drive_service and theme_folder_id:
                        # Upload V1
                        if local_image_path_v1 != "IMG_GEN_FAILED":
                            try:
                                upload_image_to_drive(drive_service, local_image_path_v1, theme_folder_id)
                            except Exception as upload_e:
                                print(f"   -> ❌ Error uploading image v1 for slide {slide_num}: {upload_e}")
                                # Don't mark as failed just for upload error, but log it
                        else:
                             print(f"   -> Skipping Google Drive upload for slide {slide_num} v1 (generation failed).")

                        # Upload V2
                        if local_image_path_v2 != "IMG_GEN_FAILED":
                             try:
                                 upload_image_to_drive(drive_service, local_image_path_v2, theme_folder_id)
                             except Exception as upload_e:
                                 print(f"   -> ❌ Error uploading image v2 for slide {slide_num}: {upload_e}")
                                 # Don't mark as failed just for upload error, but log it
                        else:
                             print(f"   -> Skipping Google Drive upload for slide {slide_num} v2 (generation failed).")

                    elif not drive_service or not theme_folder_id:
                        # Check if BOTH failed using the sentinel
                        if local_image_path_v1 == "IMG_GEN_FAILED" and local_image_path_v2 == "IMG_GEN_FAILED":
                             print(f"   -> Skipping Google Drive upload for slide {slide_num} (service/folder missing & no images generated).")
                        else:
                             print(f"   -> Skipping Google Drive upload for slide {slide_num} (service/folder missing).")


                except Exception as slide_proc_e:
                    # Catch any other unexpected error during this slide's processing
                    print(f"   -> ❌❌ Unexpected error processing slide {slide_num}: {slide_proc_e}")
                    any_slide_failed = True        # Mark theme partially failed
                    local_image_path_v1 = "IMG_GEN_FAILED" # Ensure sentinels if unexpected error
                    local_image_path_v2 = "IMG_GEN_FAILED"

                # Add data to list for CSV writing, regardless of errors (use placeholders)
                final_slide_rows.append({
                    "theme": theme,
                    "slide_number": slide_num,
                    "month_or_title": slide_title,
                    "visual_prompt": visual_prompt,
                    "slide_text": slide_text,
                    "image_file_v1": local_image_path_v1 if local_image_path_v1 != "IMG_GEN_FAILED" else "GENERATION_FAILED",
                    "image_file_v2": local_image_path_v2 if local_image_path_v2 != "IMG_GEN_FAILED" else "GENERATION_FAILED"
                })
                # print("-" * 10) # Removed to reduce noise
                # time.sleep(1) # Keep delay between slides? Maybe remove if too slow.

            print("✅ Image generation & upload loop complete for theme.")
            if any_slide_failed:
                print("⚠️ Some slides encountered errors during image generation or upload.")
                theme_successfully_processed = False # Mark theme as not fully successful
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
                # Theme success depends on image generation, not just CSV write now
            except Exception as e:
                print(f"⚠️ Failed to write CSV file '{csv_filename}': {e}")
                theme_successfully_processed = False # Mark theme as failed if CSV write fails


        except Exception as theme_e:
             # This catches errors *outside* the slide loop (e.g., text gen, parsing, folder creation)
             print(f"❌❌❌ An critical error occurred processing theme '{theme}': {theme_e}")
             print("      Skipping remainder of this theme and moving to the next.")
             theme_successfully_processed = False # Mark theme failed
             outer_theme_error = True # Indicate a fatal error for this theme prevented full processing

        # --- Mark Theme as Processed (if successful) ---
        if theme_successfully_processed:
            mark_theme_as_processed(theme)
            processed_in_this_run_count += 1
        elif outer_theme_error:
            print(f"   -> Theme '{theme}' encountered critical error, NOT marked as processed.")
        else: # Theme finished but had slide errors
             print(f"   -> Theme '{theme}' completed with slide errors, NOT marked as processed.")


        print(f"===== Finished processing theme: '{theme}' =====")
        # Add a delay only if there are more themes to process
        if theme_index < len(themes_to_run_now) - 1:
            print("   -> Waiting 5 seconds before next theme...")
            time.sleep(5)

    # --- End Theme Loop ---

    print(f"\n🎉 Batch script finished! Processed {processed_in_this_run_count} themes fully successfully in this run. 🎉")

# ------------- 8. Run the main function ------------- # Renumbered
if __name__ == "__main__":
    main() 