import requests

base_url = "http://localhost:5000"  # Replace with your actual server URL

files = {
    'image_before': open('Maui_Image_Before.png', 'rb'),
    'image_after': open('Maui_Image_After.png', 'rb')
}

response = requests.post(f"{base_url}/run-program", files=files)

if response.status_code == 200:
    result = response.json()
    print(f"Output image before: {result['output_image_before']}")
    print(f"Output image after: {result['output_image_after']}")
    print(f"Percentage: {result['percentage']}%")
else:
    print(f"Error: {response.status_code}")
