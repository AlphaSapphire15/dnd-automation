import base64
import csv
import os
import pathlib
import re
import textwrap
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image  # Import Pillow Image

# ------------- 1. Load API key and Setup -------------
load_dotenv("config.env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("⚠️  No OPENAI_API_KEY found in config.env – using placeholders.")
    # Initialize dummy openai object or skip import if key is missing
    # For simplicity, we'll handle the check within functions.
else:
    try:
        import openai
        openai.api_key = OPENAI_API_KEY
        print("✅ OpenAI API key loaded.")
    except ImportError:
        print("⚠️ OpenAI library not installed. Run 'py -m pip install openai'")
        OPENAI_API_KEY = None # Ensure key is treated as missing


# ------------- 2. Define Your Art Style Prompt -------------
# Using the detailed prompt you provided
ART_STYLE = """
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

1)Dont include the theme as text
2) make sure its dnd and not futuristic
3) make sure text is centered

visual: {visual}
""".strip()

# ------------- 3. Function to Generate Slide Text -------------
def generate_slides_text(theme: str) -> str:
    """Calls OpenAI Chat API to generate the 13 slide text descriptions."""
    if not OPENAI_API_KEY:
        print("ℹ️ Skipping text generation (no API key). Returning placeholder markdown.")
        # Generate placeholder markdown matching the expected format
        placeholder_md = "### 🏷️ **Slide 1 – Title Card**\n**visual:** Placeholder visual for title\n**The slide should have this exact text (don't add any other text):**\nPlaceholder Title\n*Placeholder subtitle*\n\n---\n\n"
        for i, month in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], start=2):
            placeholder_md += f"### 💀 **Slide {i} – {month}**\n**visual:** Placeholder visual for {month}\n**The slide should have this exact text (don't add any other text):**\n**{month} – Placeholder Item**\n*Placeholder detail*\n\n---\n\n"
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

    month_titles_map = [
        "Title Card", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]

    # Regex to find the visual description within a chunk
    visual_pattern = re.compile(r"\*\*visual:\*\*\s*(.*)", re.IGNORECASE)

    for i, chunk in enumerate(chunks):
        if i >= 13: # Stop if we somehow find more than 13 chunks
            print(f"⚠️ Found more than 13 chunks, stopping at 13.")
            break

        visual_match = visual_pattern.search(chunk)
        if not visual_match:
            print(f"⚠️ Could not find '**visual:**' in chunk {i+1}. Skipping.")
            continue

        visual_prompt = visual_match.group(1).strip()

        # Assume the text *after* the visual line is the slide text
        # Find the end position of the visual match to split the chunk
        text_start_index = visual_match.end()
        slide_text_block = chunk[text_start_index:].strip()

        # Remove potential leading/trailing instruction lines if they appear inconsistently
        slide_text_block = re.sub(r"^\*\*The slide should have this exact text.*?\*\*\s*\n?", "", slide_text_block, flags=re.IGNORECASE).strip()

        slides.append({
            "slide_number": i + 1,
            "month_or_title": month_titles_map[i] if i < len(month_titles_map) else f"Slide_{i+1}", # Assign title/month sequentially
            "visual_prompt": visual_prompt,
            "slide_text": slide_text_block # Keep the slide text exactly as found
        })

    print(f"✅ Parsed {len(slides)} slides.")
    if len(slides) != 13:
        print(f"⚠️ Warning: Expected 13 slides, but parsed {len(slides)}. Check generated text format.")

    return slides


# ------------- 5. Function to Generate Image -------------
def make_image(theme: str, visual: str, out_name: str) -> str:
    """Calls OpenAI Image API to generate an image, saves it, returns the path."""
    img_dir = pathlib.Path("images")
    img_dir.mkdir(exist_ok=True) # Ensure images directory exists
    img_path = img_dir / out_name

    if not OPENAI_API_KEY:
        print(f"ℹ️ Creating placeholder image: {img_path}")
        try:
            # Create a slightly larger, noticeable placeholder
            Image.new("RGB", (300, 450), "#AAAAAA").save(img_path, "PNG")
        except Exception as e:
            print(f"⚠️ Failed to create placeholder image: {e}")
            return "placeholder_error.png"
        # Return the simple path string for placeholders
        return str(img_path)

    print(f"🖼️ Requesting image generation for: {out_name}...")
    full_image_prompt = ART_STYLE.format(theme=theme, visual=visual)

    try:
        resp = openai.images.generate(
            model="gpt-image-1",  # Using model name from documentation
            prompt=full_image_prompt,
            n=1,
            size="1024x1536",  # Changed from 1024x1792 to a supported size for gpt-image-1
            quality="high",
        )
        b64_data = resp.data[0].b64_json
        img_bytes = base64.b64decode(b64_data)
        with open(img_path, "wb") as f:
            f.write(img_bytes)
        print(f"✅ Saved image: {img_path}")
        # Return the simple path string after successful save
        return str(img_path)

    except openai.BadRequestError as e:
         print(f"❌ Image Generation Failed (Bad Request): {e}")
         print("   This might be due to content policy violations or an issue with the prompt.")
         print(f"   Problematic visual prompt part: '{visual}'")
         print("   Creating placeholder image instead.")
         # Directly create placeholder on bad request
         try:
             Image.new("RGB", (300, 450), "#AAAAAA").save(img_path, "PNG")
             return str(img_path)
         except Exception as img_e:
             print(f"⚠️ Failed to create placeholder image after error: {img_e}")
             return "placeholder_error.png"

    except Exception as e:
        print(f"⚠️ Image generation failed: {e}")
        print(f"   Visual prompt part: '{visual}'")
        print("   Creating placeholder image instead.")
        # Directly create placeholder on other errors
        try:
            Image.new("RGB", (300, 450), "#AAAAAA").save(img_path, "PNG")
            return str(img_path)
        except Exception as img_e:
            print(f"⚠️ Failed to create placeholder image after error: {img_e}")
            return "placeholder_error.png"


# ------------- 6. Main Execution Logic -------------
def main():
    """Main function to orchestrate the process."""
    theme = input("Enter the theme for your TikTok slide series: ").strip()
    if not theme:
        print("❌ Theme cannot be empty.")
        return

    print("-" * 30)
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


    # 3. Generate image for each slide and collect data for CSV
    final_slide_rows = []
    print("-" * 30)
    print("⏳ Starting image generation loop...")
    for slide in parsed_slide_data:
        slide_num = slide['slide_number']
        month_title = slide['month_or_title']
        visual_prompt = slide['visual_prompt']
        slide_text = slide['slide_text']

        # Generate a filename (e.g., 01_TitleCard.png or 02_January.png)
        # Sanitize month/title for filename use
        safe_month_title = re.sub(r'[\\/*?:"<>|]', "", month_title).replace(" ", "_")
        filename = f"{slide_num:02d}_{safe_month_title}.png"

        # Generate image
        image_file_path = make_image(theme, visual_prompt, filename)

        # Add data to list for CSV writing
        final_slide_rows.append({
            "theme": theme,
            "slide_number": slide_num,
            "month_or_title": month_title,
            "visual_prompt": visual_prompt,
            "slide_text": slide_text,
            "image_file": image_file_path
        })
        print("-" * 10) # Separator between slides

    print("✅ Image generation loop complete.")
    print("-" * 30)

    # 4. Write data to CSV
    csv_path = pathlib.Path("slides.csv")
    print(f"💾 Writing data to {csv_path}...")
    try:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            # Define the headers based on the keys in our dictionaries
            fieldnames = ["theme", "slide_number", "month_or_title", "visual_prompt", "slide_text", "image_file"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(final_slide_rows)
        print(f"✅ Successfully wrote {len(final_slide_rows)} rows to {csv_path.resolve()}")
    except Exception as e:
        print(f"⚠️ Failed to write CSV file: {e}")

    print("-" * 30)
    print("🎉 Script finished!")

# ------------- 7. Run the main function -------------
if __name__ == "__main__":
    main() 