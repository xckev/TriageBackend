import os
import base64
import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image
import requests
from flask import Flask, request, jsonify, send_from_directory, url_for
from werkzeug.utils import secure_filename
from flask_cors import CORS
from roboflow import Roboflow
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Constants
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
UPLOAD_FOLDER = 'images/damage/uploads'
OUTPUT_FOLDER = 'images/damage/outputs'

# Environment variables
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
ROBOFLOW_API_KEY = os.getenv('ROBOFLOW_API_KEY')
IMAGE_SIMILARITY_API = os.getenv('IMAGE_SIMILARITY_API_URL')

# Validate required environment variables
if not all([GOOGLE_MAPS_API_KEY, ROBOFLOW_API_KEY, IMAGE_SIMILARITY_API]):
    raise EnvironmentError("Missing required environment variables. Please check your .env file.")

# Configure Flask app
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "message": "Triage backend server is running"
    })

@app.route('/analyze-risk/<string:address>', methods=['GET'])
def analyze_risk(address):    
    try:
        # Get satellite image from Google Maps
        maps_url = f'https://maps.googleapis.com/maps/api/staticmap?center={address}&zoom=15&size=400x400&maptype=satellite&key={GOOGLE_MAPS_API_KEY}'
        response = requests.get(maps_url)
        
        # Convert image to base64
        img_array = np.frombuffer(response.content, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        _, buffer = cv2.imencode('.png', img)
        img_base64 = base64.b64encode(buffer).decode('utf-8')

        # Compare with reference images
        max_similarity = 0
        best_match = ''
        
        for filename in os.listdir('./images/risk'):
            file_path = os.path.join('./images/risk', filename)
            category = file_path.split('.')[2]
            
            with open(file_path, "rb") as img_file:
                reference_img_base64 = base64.b64encode(img_file.read()).decode('utf-8')

            response = requests.post(IMAGE_SIMILARITY_API, json={
                "img_1": img_base64,
                "img_2": reference_img_base64
            })
            
            similarity_score = response.json()['similarity']
            if similarity_score > max_similarity:
                max_similarity = similarity_score
                best_match = category

        return jsonify({"damage": str(best_match)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/analyze-damage', methods=['POST'])
def analyze_damage():
    # Validate input files
    if 'imageBefore' not in request.files or 'imageAfter' not in request.files:
        return jsonify({'error': 'Both before and after images are required'}), 400

    before_image = request.files['imageBefore']
    after_image = request.files['imageAfter']

    if not (before_image.filename and after_image.filename):
        return jsonify({'error': 'Both images must be selected'}), 400

    if not (is_allowed_file(before_image.filename) and is_allowed_file(after_image.filename)):
        return jsonify({'error': 'Invalid file type'}), 400

    try:
        # Save and process images
        before_path = save_image(before_image)
        after_path = save_image(after_image)

        # Initialize Roboflow
        rf = Roboflow(api_key=ROBOFLOW_API_KEY)
        model = rf.workspace().project("junk-jzngr").version(16).model

        # Analyze images
        before_result = model.predict(before_path, confidence=12).json()
        after_result = model.predict(after_path, confidence=12).json()

        # Process results
        before_count = sum(1 for pred in before_result['predictions'] if pred['class'] == "no-damage")
        after_count = sum(1 for pred in after_result['predictions'] if pred['class'] == "no-damage")
        
        # Generate output images
        before_output = process_image(before_path, before_result)
        after_output = process_image(after_path, after_result)

        # Calculate damage percentage
        damage_percentage = (after_count / before_count * 100) if before_count > 0 else 0

        response = {
            "before_image_url": url_for('serve_image', filename=before_output, _external=True),
            "after_image_url": url_for('serve_image', filename=after_output, _external=True),
            "damage_percentage": damage_percentage
        }

        return jsonify(response)

    except Exception as e:
        # cleanup_files(before_path, after_path)
        return jsonify({'error': str(e)}), 500

@app.route('/images/<path:filename>')
def serve_image(filename):
    try:
        response = send_from_directory(OUTPUT_FOLDER, filename)
        # cleanup_files(os.path.join(OUTPUT_FOLDER, filename))
        return response
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def is_allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file):
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    Image.open(file).convert('RGB').save(filepath, 'JPEG')
    return filepath

def process_image(image_path, result):
    image = Image.open(image_path).convert('RGB')
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(image)

    colors = {
        "minor-damage": "green",
        "major-damage": "yellow",
        "destroyed": "red",
        "no-damage": "blue"
    }

    for pred in result['predictions']:
        x_center, y_center = pred['x'], pred['y']
        width, height = pred['width'], pred['height']
        x_min, y_min = x_center - (width / 2), y_center - (height / 2)
        
        color = colors.get(pred['class'], "white")
        rect = patches.Rectangle((x_min, y_min), width, height, 
                               linewidth=3, edgecolor=color, facecolor='none')
        ax.add_patch(rect)
        ax.text(x_min, y_min - 10, pred['class'], fontsize=8, color="black")

    ax.axis('off')
    output_filename = f"output_{os.path.basename(image_path)}"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    plt.savefig(output_path, bbox_inches='tight', pad_inches=0, format='jpeg')
    plt.close(fig)
    return output_filename

def cleanup_files(*file_paths):
    for path in file_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"Error deleting {path}: {str(e)}")

if __name__ == '__main__':
    app.run(debug=False, port=80)
