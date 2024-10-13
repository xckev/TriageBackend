import requests
import datetime
from flask import Flask, jsonify, send_from_directory, request, url_for
import os
from werkzeug.utils import secure_filename
from flask_cors import CORS
import logging

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image
from roboflow import Roboflow
import supervision as sv
import cv2
import threading
import time

app = Flask(__name__)
CORS(app)

app.config['UPLOAD_FOLDER'] = 'uploads'
try:
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
        logging.info(f"Created upload directory: {app.config['UPLOAD_FOLDER']}")
    else:
        logging.info(f"Upload directory already exists: {app.config['UPLOAD_FOLDER']}")
except Exception as e:
    logging.error(f"Error creating upload directory: {str(e)}")

@app.route('/', methods=['GET'])
def get_home():
    toReturn = jsonify({"text": "Welcome to the Triage backend server! API requests may be requested from this URL."})
    toReturn.headers.add('Access-Control-Allow-Origin', '*')
    return toReturn


@app.route('/run-program', methods=['POST'])
def run_program():
    logging.info("run_program function called")
    logging.info(f"Current working directory: {os.getcwd()}")
    logging.info(f"Contents of upload directory: {os.listdir(app.config['UPLOAD_FOLDER'])}")
    if 'imageBefore' not in request.files or 'imageAfter' not in request.files:
        return jsonify({'error': 'Both before and after images are required'}), 400

    image_before = request.files['imageBefore']
    image_after = request.files['imageAfter']

    if image_before.filename == '' or image_after.filename == '':
        return jsonify({'error': 'Both before and after images must be selected'}), 400

    if image_before and image_after and allowed_file(image_before.filename) and allowed_file(image_after.filename):
        image_path_before = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(image_before.filename)))
        image_path_after = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(image_after.filename)))

        try:
            image_before.save(image_path_before)
            logging.info(f"Saved image_before to: {image_path_before}")
            image_after.save(image_path_after)
            logging.info(f"Saved image_after to: {image_path_after}")
        except Exception as e:
            logging.error(f"Error saving uploaded files: {str(e)}")
            return jsonify({'error': 'Error saving uploaded files'}), 500

        rf = Roboflow(api_key="zpb5BDJeUPjMGNd2CVoO")
        project = rf.workspace().project("junk-jzngr")
        model = project.version(16).model

        # Process before image
        result_before = model.predict(image_path_before, confidence=12).json()
        before_count = sum(1 for result in result_before['predictions'] if result['class'] == "no-damage")
        output_path_before = process_image(image_path_before, result_before)

        # Process after image
        result_after = model.predict(image_path_after, confidence=12).json()
        after_count = sum(1 for result in result_after['predictions'] if result['class'] == "no-damage")
        output_path_after = process_image(image_path_after, result_after)

        damage_percentage = (after_count / before_count * 100) if before_count > 0 else 0

        response = {
            "outputImageBefore": url_for('serve_image', filename=output_path_before, _external=True),
            "outputImageAfter": url_for('serve_image', filename=output_path_after, _external=True),
            "damagePercentage": damage_percentage
        }

        return jsonify(response)

    return jsonify({'error': 'Invalid file type'}), 400

def process_image(image_path, result):
    try:
        full_path = os.path.abspath(image_path)
        image = Image.open(full_path)
        logging.info(f"Opened image from: {full_path}")
        fig, ax = plt.subplots(figsize=(10, 10))
        ax.imshow(image)

        for pred in result['predictions']:
            x_center, y_center = pred['x'], pred['y']
            width, height = pred['width'], pred['height']
            x_min, y_min = x_center - (width / 2), y_center - (height / 2)

            color = {
                "minor-damage": "green",
                "major-damage": "yellow",
                "destroyed": "red",
                "no-damage": "blue"
            }.get(pred['class'], "white")

            rect = patches.Rectangle((x_min, y_min), width, height, linewidth=3, edgecolor=color, facecolor='none')
            ax.add_patch(rect)
            ax.text(x_min, y_min - 10, pred['class'], fontsize=8, color="black")

        ax.axis('off')
        output_path = f"output_{os.path.basename(image_path)}"
        plt.savefig(output_path, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        return output_path
    except Exception as e:
        logging.error(f"Error processing image: {str(e)}")
        raise

@app.route('/images/<path:filename>')
def serve_image(filename):
    try:
        response = send_from_directory('', filename)
        
        # Schedule file deletion after a short delay
        def delete_file(file_path, delay=1):
            time.sleep(delay)
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error deleting file {file_path}: {str(e)}")

        threading.Thread(target=delete_file, args=(filename,)).start()
        
        return response
    except FileNotFoundError:
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({'filename': filename}), 200
    return jsonify({'error': 'File type not allowed'}), 400

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}

if (__name__ == "__main__"):

    app.run(host="0.0.0.0", debug=True)
