from flask import Flask, request, jsonify, send_file, render_template
import yt_dlp
import os
import uuid

app = Flask(__name__)

# Directory to temporarily store downloaded videos
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_video():
    try:
        video_url = request.form['url']
        if not video_url:
            return jsonify({'error': 'URL is required'}), 400

        # Generate a unique filename
        unique_id = str(uuid.uuid4())
        output_path = os.path.join(DOWNLOAD_DIR, f"video_{unique_id}.mp4")

        # yt-dlp options for 4K MP4 with fallback
        ydl_opts = {
            'outtmpl': output_path,
            'format': 'bestvideo[height=2160][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
        }

        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_title = info.get('title', 'video')

            # Check if 4K was downloaded
            is_4k = any(fmt.get('height') == 2160 for fmt in info.get('formats', []))
            resolution_note = "4K" if is_4k else "Best available resolution (4K not found)"

        # Verify the downloaded file exists
        if not os.path.exists(output_path):
            return jsonify({'error': 'Download failed'}), 500

        # Generate a download link
        download_link = f"/serve/{unique_id}"
        return jsonify({
            'success': True,
            'title': video_title,
            'resolution': resolution_note,
            'download_link': download_link
        })

    except yt_dlp.utils.DownloadError as e:
        return jsonify({'error': 'Download failed: ' + str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/serve/<file_id>')
def serve_file(file_id):
    file_path = os.path.join(DOWNLOAD_DIR, f"video_{file_id}.mp4")
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(file_path, as_attachment=True, download_name="downloaded_video_4k.mp4")

if __name__ == '__main__':
    app.run(debug=True)