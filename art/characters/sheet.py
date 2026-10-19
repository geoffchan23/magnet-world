from PIL import Image, ImageDraw, ImageFont

D = "/Users/geoff/Desktop/Work/Personal/magnet-world/concepts"
items = [("1-kid", "1 Kid"), ("2-fox", "2 Fox"), ("3-robot", "3 Robot"), ("4-dino", "4 Dino")]
S = 1024
sheet = Image.new("RGB", (S * 2, S * 2), "white")
font = None
for f in ("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
          "/Library/Fonts/Arial Bold.ttf"):
    try:
        font = ImageFont.truetype(f, 110)
        break
    except OSError:
        pass
font = font or ImageFont.load_default()
for i, (fn, label) in enumerate(items):
    im = Image.open(f"{D}/{fn}.png").convert("RGB")
    x, y = (i % 2) * S, (i // 2) * S
    sheet.paste(im, (x, y))
    d = ImageDraw.Draw(sheet)
    tw = d.textlength(label, font=font)
    pad = 28
    box = (x + 40, y + 40, x + 40 + tw + pad * 2, y + 40 + 140)
    d.rounded_rectangle(box, radius=40, fill=(255, 255, 255))
    d.text((x + 40 + pad, y + 52), label, font=font, fill=(40, 48, 66))
# thin dividers
d = ImageDraw.Draw(sheet)
d.line([(S, 0), (S, 2 * S)], fill="white", width=8)
d.line([(0, S), (2 * S, S)], fill="white", width=8)
sheet.save(f"{D}/sheet.png")
sheet.resize((1024, 1024), Image.LANCZOS).save("/private/tmp/claude-501/-Users-geoff-Desktop-Work-Personal/cf9a1f6d-8d92-4db3-b237-0d299e539bef/scratchpad/chars/sheet_small.png")
print("ok")
