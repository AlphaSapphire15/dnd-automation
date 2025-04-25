import base64
import csv
import os
import pathlib
import re
import textwrap
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
def generate_slides_text(theme: str) -> str:
    """Calls OpenAI Chat API to generate the 13 slide text descriptions."""
    if not OPENAI_API_KEY:
        print("ℹ️ Skipping text generation (no API key). Returning placeholder markdown.")
        # Generate placeholder markdown matching the expected format
        placeholder_md = "### 🏷️ **Slide 1 – Title Card**\\n**visual:** Placeholder visual for title\\n**The slide should have this exact text (don't add any other text):**\\nPlaceholder Title\\n*Placeholder subtitle*\\n\\n---\\n\\n"
        for i, month in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], start=2):
            placeholder_md += f"### 💀 **Slide {i} – {month}**\\n**visual:** Placeholder visual for {month}\\n**The slide should have this exact text (don't add any other text):**\\n**{month} – Placeholder Item**\\n*Placeholder detail*\\n\\n---\\n\\n"
        return placeholder_md

    print(f"📝 Requesting slide text generation for theme: '{theme}'...")
    try:
        # Use the detailed prompt format you showed
        chat_prompt_content = f"""
You are a creative TTRPG content writer. You MUST generate content in the EXACT format requested below.

Theme: "{theme}"

Generate a 13-slide TikTok carousel series based on this theme.
Slide 1 is the title card. Slides 2-13 correspond to January-December.

For **each slide**, output EXACTLY like this, including the markdown and specific phrasing:

### 🏷️ **Slide [Number] – [Month/Title Card]**
**visual:** (One sentence describing a unique retro-anime illustration appropriate for the slide's specific theme/month. Avoid repeating the exact same character description across multiple slides unless contextually necessary.)
**The slide should have this exact text (don't add any other text):**
**[Month/Title] – [Catchy Item/Concept]**
*[Witty/Funny Subtitle]*

---

Ensure the output strictly follows this template for all 13 slides. Do not add extra explanations or conversational text.
        """

        resp = openai.chat.completions.create(
            model="gpt-4o-mini", # Or "gpt-4o" if preferred
            messages=[
                {"role": "system", "content": "You are a creative writer generating TikTok slide content following a strict template."},
                {"role": "user", "content": chat_prompt_content}
            ],
            temperature=0.8, # Adjust temperature as desired
        )
        generated_text = resp.choices[0].message.content
        print("✅ Text generation complete.")
        return generated_text
    except Exception as e:
        print(f"⚠️ Text generation failed: {e}")
        print("ℹ️ Returning placeholder markdown due to error.")
        return generate_slides_text(theme) # Fallback to placeholder on error


# ------------- 4. Function to Parse Generated Text -------------
def parse_slides(md_block: str) -> list[dict]:
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
        if i >= 13: # Stop if we somehow find more than 13 chunks
            print(f"⚠️ Found more than 13 chunks, stopping at 13.")
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
    if len(slides) != 13:
        print(f"⚠️ Warning: Expected 13 slides, but parsed {len(slides)}. Check generated text format.")

    return slides


# ------------- 5. Function to Generate Image -------------
# Updated to accept slide_text and construct the full prompt dynamically
def make_image(theme: str, visual: str, slide_text: str, out_name: str) -> str | None:
    """Calls OpenAI Image API to generate an image with specific text, saves it, returns the path or None on failure."""
    img_dir = pathlib.Path("images")
    img_dir.mkdir(exist_ok=True)
    img_path = img_dir / out_name

    if not OPENAI_API_KEY:
        print(f"ℹ️ Creating placeholder image: {img_path}")
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
            img.save(img_path, "PNG")
            print(f"✅ Saved placeholder image with text: {img_path}")
            return str(img_path)
        except Exception as e:
            print(f"⚠️ Failed to create placeholder image with text: {e}")
            try:
                 Image.new("RGB", (300, 450), "#AAAAAA").save(img_path, "PNG")
                 return str(img_path) # Return path even for basic placeholder
            except Exception as e_inner:
                 print(f"⚠️ Failed to create basic placeholder image: {e_inner}")
                 return None # Indicate failure

    print(f"🖼️ Requesting image generation for: {out_name}...")

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

    try:
        resp = openai.images.generate(
            model="gpt-image-1",
            prompt=full_image_prompt,
            n=1,
            size="1024x1536",
            quality="high",
        )
        b64_data = resp.data[0].b64_json
        img_bytes = base64.b64decode(b64_data)
        with open(img_path, "wb") as f:
            f.write(img_bytes)
        print(f"✅ Saved image: {img_path}")
        return str(img_path)

    except openai.BadRequestError as e:
         print(f"❌ Image Generation Failed (Bad Request): {e}")
         print(f"   Problematic visual prompt part: '{visual}'")
         print("   Creating placeholder image instead.")
         # Attempt to create placeholder with text on bad request
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
             print(f"✅ Saved placeholder image with text: {img_path}")
             return str(img_path)
         except Exception as img_e:
             print(f"⚠️ Failed to create placeholder image with text after error: {img_e}")
             return None # Indicate failure

    except Exception as e:
        print(f"⚠️ Image generation failed: {e}")
        print(f"   Visual prompt part: '{visual}'")
        print("   Creating placeholder image instead.")
        # Attempt to create placeholder with text on other errors
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
             print(f"✅ Saved placeholder image with text: {img_path}")
             return str(img_path)
        except Exception as img_e:
            print(f"⚠️ Failed to create placeholder image with text after error: {img_e}")
            return None # Indicate failure


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
        # Search for the folder
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_folder_id}' in parents and trashed=false"
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
                'name': folder_name,
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

# ------------- 7. Main Execution Logic -------------
def main():
    """Main function to orchestrate the process."""
    theme = input("Enter the theme for your TikTok slide series: ").strip()
    if not theme:
        print("❌ Theme cannot be empty.")
        return

    print("-" * 30)

    # --- Initialize Google Drive Service (TESTING ONLY) ---
    drive_service = None
    theme_folder_id = None
    print("ℹ️ Attempting Google Drive connection and folder check...")
    if GOOGLE_DRIVE_FOLDER_ID:
        drive_service = get_drive_service()
        if drive_service:
            theme_folder_id = find_or_create_folder(drive_service, theme, GOOGLE_DRIVE_FOLDER_ID)
            if not theme_folder_id:
                 print("⚠️ Could not find or create theme folder in Google Drive.")
            else:
                 print(f"✅ Successfully found/created theme folder ID: {theme_folder_id}")
        else:
            print("⚠️ Failed to get Google Drive service.")
    else:
         print("ℹ️ Google Drive Folder ID not set. Skipping test.")
    # --- End Google Drive Init ---

    print("\n✅ Google Drive connection test finished.")
    print("🛑 Skipping OpenAI calls and image generation for this test run.")

    # --- Restore main functionality ---
    # 1. Generate the text block
    markdown_block = generate_slides_text(theme)
    print("\n--- Raw Generated Markdown Block ---")
    print(markdown_block)
    print("--- End Raw Markdown Block ---\n")

    # 2. Parse the text block into structured slide data
    parsed_slide_data = parse_slides(markdown_block)
    if not parsed_slide_data:
        print("❌ Failed to parse slides from generated text. Cannot proceed.")
        return
    if len(parsed_slide_data) != 13:
         print(f"⚠️ Continuing with {len(parsed_slide_data)} slides found.")

    # 3. Generate image, upload to Drive, and collect data for CSV
    final_slide_rows = []
    print("-" * 30)
    print("⏳ Starting image generation & upload loop...") # Restored loop title
    for slide in parsed_slide_data:
        slide_num = slide['slide_number']
        month_title = slide['month_or_title']
        visual_prompt = slide['visual_prompt']
        slide_text = slide['slide_text']

        # Generate filename
        safe_month_title = re.sub(r'[\\\\/*?:\"<>|]', "", month_title).replace(" ", "_")
        filename = f"{slide_num:02d}_{safe_month_title}.png"

        # Generate image
        local_image_path = make_image(theme, visual_prompt, slide_text, filename)

        # Upload to Google Drive if image was created successfully and service/folder are ready
        if local_image_path and drive_service and theme_folder_id:
            upload_image_to_drive(drive_service, local_image_path, theme_folder_id)
        elif not local_image_path:
             print(f"   -> Skipping Google Drive upload for slide {slide_num} (image generation failed).")

        # Add data to list for CSV writing
        final_slide_rows.append({
            "theme": theme,
            "slide_number": slide_num,
            "month_or_title": month_title,
            "visual_prompt": visual_prompt,
            "slide_text": slide_text,
            "image_file": local_image_path if local_image_path else "GENERATION_FAILED" # Record path or failure
        })
        print("-" * 10) # Separator between slides

    print("✅ Image generation & upload loop complete.") # Restored loop completion message
    print("-" * 30)

    # 4. Write data to CSV
    csv_path = pathlib.Path("slides.csv")
    print(f"💾 Writing data to {csv_path}...")
    try:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            fieldnames = ["theme", "slide_number", "month_or_title", "visual_prompt", "slide_text", "image_file"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(final_slide_rows)
        print(f"✅ Successfully wrote {len(final_slide_rows)} rows to {csv_path.resolve()}")
    except Exception as e:
        print(f"⚠️ Failed to write CSV file: {e}")

    print("-" * 30)
    print("🎉 Script finished!")
    # --- End of restored section ---

# ------------- 8. Run the main function ------------- # Renumbered
if __name__ == "__main__":
    main()