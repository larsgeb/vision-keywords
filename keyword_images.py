# Import necessary libraries
import os
import base64
import requests
import pickle
import shutil
import tqdm
from iptcinfo3 import IPTCInfo
from PIL import Image
import piexif
from PIL.ExifTags import TAGS

# OpenAI API Key
api_key = "<placeholder>"


# Function to encode the image to base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


# Function to check image dimensions
def check_image_dimensions(image_path, max_width=510, max_height=510):
    with Image.open(image_path) as img:
        return img.size[0] <= max_width and img.size[1] <= max_height


# Function to resize the image to 510x510 pixels
def resize_image(image_path, output_path, target_size=(510, 510)):
    with Image.open(image_path) as img:
        img_resized = img.resize(target_size)
        img_resized.save(output_path)


# Function to update image title in EXIF data
def update_image_title(image_path, new_title):
    # Open the image
    img = Image.open(image_path)

    # Get the existing EXIF data
    try:
        exif_dict = piexif.load(img.info["exif"])
    except (KeyError, TypeError, piexif.InvalidImageDataError):
        # If there's no existing EXIF data, create an empty dictionary
        exif_dict = {
            "0th": {},
            "Exif": {},
            "GPS": {},
            "1st": {},
            "thumbnail": None,
        }

    # Update the title in the EXIF data
    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = new_title

    # Convert the EXIF data back to binary format
    exif_bytes = piexif.dump(exif_dict)

    # Save the image with updated EXIF data
    img.save(image_path, "jpeg", quality="keep", exif=exif_bytes)


# Input and output directories
input_folder = "/Users/yourusername/Desktop/input"
output_folder = "/Users/yourusername/Desktop/output"

# List of image files to process
image_files = [
    f
    for f in sorted(os.listdir(input_folder))
    if f.endswith((".jpg", ".jpeg", ".png"))
]

# API endpoint and headers
api_endpoint = "https://api.openai.com/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}",
}

# Dictionary to store results
results = {}

# Load existing results if available
if os.path.exists("results.pkl"):
    with open("results.pkl", "rb") as f:
        results = pickle.load(f)

# Flag to skip API calls (for testing purposes)
skip_API = False

# Loop through each image file
for image_file in tqdm.tqdm(image_files):
    # Skip if the result for this image is already present
    original_image_path = os.path.join(input_folder, image_file)

    if image_file not in results:
        if skip_API:
            continue

        # Getting the base64 string after resizing the image
        resized_image_path = "resized_" + image_file

        # Resize the image to 510x510 pixels
        resize_image(original_image_path, resized_image_path)

        base64_image = encode_image(resized_image_path)

        # Remove the resized image file after encoding
        os.remove(resized_image_path)

        # Extract existing keywords from IPTC data
        info = IPTCInfo(original_image_path)
        existing_kws = [str(kw.decode()) for kw in info["keywords"]]

        # Construct payload for the API request
        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"I want thirty keywords to describe this image for Adobe Stock, targeted towards discoverability. These keywords are already present: {existing_kws}, please include the ones that are relevant or location specific. Please output them comma separated. Please as the first entry, output an editorialized title, also separated by commas. Don't output any other characters.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 300,
        }

        # Make the API request
        response = requests.post(api_endpoint, headers=headers, json=payload)

        # Process API response and store results
        result = response.json()["choices"][0]["message"]["content"]
        results[image_file] = result
        results[f"{image_file}_original_kws"] = existing_kws
    else:
        result = results[image_file]

    # Extract title and keywords from API response
    result_entries = result.split(", ")
    title = result_entries[0]
    kws = result_entries[1:]

    # Define the path for the new processed image
    new_image_path = os.path.join(output_folder, image_file)

    # Copy the original image to the output folder
    shutil.copy(original_image_path, new_image_path)

    # Update image title and keywords in IPTC data
    update_image_title(new_image_path, title)
    info = IPTCInfo(new_image_path)
    info["keywords"] = kws
    info.save()

    # Save results after each iteration
    with open("results.pkl", "wb") as f:
        pickle.dump(results, f)
