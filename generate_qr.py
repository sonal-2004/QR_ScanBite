import qrcode

url = "https://scanbite-fnfr.onrender.com"   # Replace with your Render URL

qr = qrcode.QRCode(
    version=1,
    box_size=15,
    border=5
)

qr.add_data(url)
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white")

img.save("scanbite_qr.png")

print("QR Code Generated Successfully!")