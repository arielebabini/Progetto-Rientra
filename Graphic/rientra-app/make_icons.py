import os
from PIL import Image, ImageDraw, ImageFilter

def draw_diagonal_gradient(width, height, color1, color2):
    base = Image.new("RGBA", (width, height))
    for y in range(height):
        for x in range(width):
            # Diagonal gradient factor
            factor = (x / width + y / height) / 2.0
            r = int(color1[0] + (color2[0] - color1[0]) * factor)
            g = int(color1[1] + (color2[1] - color1[1]) * factor)
            b = int(color1[2] + (color2[2] - color1[2]) * factor)
            a = int(color1[3] + (color2[3] - color1[3]) * factor)
            base.putpixel((x, y), (r, g, b, a))
    return base

def main():
    src_path = "public/logo-rientra.png"
    if not os.path.exists(src_path):
        print(f"Error: {src_path} not found.")
        return

    # Canvas dimensions (macOS standard high-res icon size)
    canvas_size = 512
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))

    # 1. Generate macOS Squircle Shadow (for native 3D Dock effect)
    squircle_size = 400
    squircle_offset = (canvas_size - squircle_size) // 2  # 56px offset
    
    shadow_layer = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    # Draw a shifted black rounded rectangle for shadow
    shadow_draw.rounded_rectangle(
        (squircle_offset, squircle_offset + 12, squircle_offset + squircle_size, squircle_offset + squircle_size + 12),
        radius=90,
        fill=(0, 0, 0, 75)
    )
    # Blur the shadow slightly for a soft look
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(15))
    canvas.alpha_composite(shadow_layer)

    # 2. Generate Squircle Background with a deep-blue/teal gradient (matching HomePage.css background)
    # Color 1: #1a2a4a (Navy blue) -> Color 2: #102840 (Deep dark slate/blue)
    color1 = (26, 42, 74, 255)
    color2 = (16, 40, 64, 255)
    gradient_img = draw_diagonal_gradient(squircle_size, squircle_size, color1, color2)

    # Mask for squircle rounded corners
    squircle_mask = Image.new("L", (squircle_size, squircle_size), 0)
    mask_draw = ImageDraw.Draw(squircle_mask)
    mask_draw.rounded_rectangle((0, 0, squircle_size, squircle_size), radius=90, fill=255)

    # Paste squircle onto canvas
    squircle_layer = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    squircle_layer.paste(gradient_img, (squircle_offset, squircle_offset), squircle_mask)
    canvas.alpha_composite(squircle_layer)

    # 3. Add a premium glow/border to the squircle edge
    border_layer = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_layer)
    # Light blue glowing border
    border_draw.rounded_rectangle(
        (squircle_offset, squircle_offset, squircle_offset + squircle_size, squircle_offset + squircle_size),
        radius=90,
        outline=(71, 191, 255, 120),  # #47bfff with opacity
        width=3
    )
    canvas.alpha_composite(border_layer)

    # 4. Process the Rientra Logo (ensure it is crisp white and centered)
    logo = Image.open(src_path).convert("RGBA")
    
    # Scale logo to fit inside the squircle (approx. 50% of canvas)
    target_logo_size = 230
    scale = min(target_logo_size / logo.width, target_logo_size / logo.height)
    logo_w = int(logo.width * scale)
    logo_h = int(logo.height * scale)
    
    # Create pure white version of the logo using its alpha channel
    white_logo = Image.new("RGBA", (logo_w, logo_h), (255, 255, 255, 255))
    logo_alpha = logo.split()[3].resize((logo_w, logo_h), Image.Resampling.LANCZOS)
    
    # Coordinates to center the logo on the 512x512 canvas
    logo_x = (canvas_size - logo_w) // 2
    logo_y = (canvas_size - logo_h) // 2

    # 5. Add a soft drop shadow under the logo for a 3D glassmorphic depth
    logo_shadow_layer = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    logo_shadow_layer.paste(
        Image.new("RGBA", (logo_w, logo_h), (0, 0, 0, 160)),
        (logo_x, logo_y + 6),
        logo_alpha
    )
    logo_shadow_layer = logo_shadow_layer.filter(ImageFilter.GaussianBlur(8))
    canvas.alpha_composite(logo_shadow_layer)

    # 6. Paste the white logo on top
    canvas.paste(white_logo, (logo_x, logo_y), logo_alpha)

    # Create build/ directory if not exists
    os.makedirs("build", exist_ok=True)

    # Save as .icns for macOS
    icns_path = "build/icon.icns"
    canvas.save(icns_path, format="ICNS")
    print(f"Saved premium macOS icon to {icns_path}")

    # Save as .ico for Windows
    ico_path = "build/icon.ico"
    canvas.save(ico_path, format="ICO", sizes=[(16,16), (32,32), (48,48), (256,256)])
    print(f"Saved Windows icon to {ico_path}")

    # Also save as a png for general use
    png_path = "build/icon.png"
    canvas.save(png_path)
    print(f"Saved PNG icon to {png_path}")

if __name__ == "__main__":
    main()
