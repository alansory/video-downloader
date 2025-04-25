from flask import Flask, request, jsonify, render_template
import yt_dlp
import requests
import re
import time
import hmac
import hashlib
from dotenv import load_dotenv
import os


load_dotenv()  # Load environment variables from .env file
app = Flask(__name__)

# Storyblocks API configuration
STORYBLOCKS_API_BASE = "https://api.videoblocks.com/api/v2/videos/stock-item/download"
STORYBLOCKS_PUBLIC_KEY = "test_55a9815460419807f4c9aafa41ad6421a9b9d1b9cc6ffa8a52d09a825f1"
STORYBLOCKS_PRIVATE_KEY = "test_d4e124f1ff3a022197e39ce3ed96528ea0faee914957e55868305f24a67"
PROJECT_ID = "downloaderSopyan"
USER_ID = "alansory1"

def generate_storyblocks_auth(resource):
    # Set expires to 6 hours from now
    expires = str(int(time.time()) + 21600)  # 6 hours = 21600 seconds
    
    # Create HMAC
    hmac_builder = hmac.new(
        (STORYBLOCKS_PRIVATE_KEY + expires).encode('utf-8'),
        resource.encode('utf-8'),
        hashlib.sha256
    )
    hmac_hex = hmac_builder.hexdigest()
    
    # Debug print
    print(f"Resource: {resource}")
    print(f"Expires: {expires}")
    print(f"HMAC: {hmac_hex}")
    
    return expires, hmac_hex

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_video():
    try:
        video_url = request.form['url']
        platform = request.form.get('platform', 'youtube')
        resolution = request.form.get('resolution', 'best')  # Default ke 'best' untuk YouTube
        
        if not video_url:
            return jsonify({'error': 'URL is required'}), 400

        if platform == 'storyblocks':
            try:
                # Extract video ID from URL
                video_id_match = re.search(r'stock-video-id-(\d+)|[/-](\d+)$', video_url)
                if not video_id_match:
                    return jsonify({'error': 'Invalid Storyblocks URL format'}), 400
                
                video_id = next(group for group in video_id_match.groups() if group is not None)
                print(f"Extracted video ID: {video_id}")
                
                # Generate dynamic HMAC and expires
                resource = f"/api/v2/videos/stock-item/download/{video_id}"
                expires, hmac_hex = generate_storyblocks_auth(resource)
                
                # Construct Storyblocks API URL with parameters
                api_url = f"{STORYBLOCKS_API_BASE}/{video_id}"
                params = {
                    'APIKEY': STORYBLOCKS_PUBLIC_KEY,
                    'EXPIRES': expires,
                    'project_id': PROJECT_ID,
                    'user_id': USER_ID,
                    'HMAC': hmac_hex
                }
                
                print(f"API URL: {api_url}")
                print(f"Params: {params}")
                
                # Make request to Storyblocks API
                response = requests.get(api_url, params=params)
                print(f"Response status: {response.status_code}")
                print(f"Response content: {response.text}")
                
                if response.status_code != 200:
                    return jsonify({'error': f'Failed to fetch Storyblocks video data: {response.text}'}), 400
                
                video_data = response.json()
                
                # Get the highest quality MP4 URL
                download_url = None
                resolution_note = None
                
                if '_2160p' in video_data.get('MP4', {}):
                    download_url = video_data['MP4']['_2160p']
                    resolution_note = "4K (2160p)"
                elif '_1080p' in video_data.get('MP4', {}):
                    download_url = video_data['MP4']['_1080p']
                    resolution_note = "1080p"
                elif '_720p' in video_data.get('MP4', {}):
                    download_url = video_data['MP4']['_720p']
                    resolution_note = "720p"
                
                if not download_url:
                    return jsonify({'error': 'No suitable video format found'}), 400
                
                return jsonify({
                    'success': True,
                    'title': 'Storyblocks Video',
                    'resolution': resolution_note,
                    'download_url': download_url
                })
                
            except Exception as e:
                return jsonify({'error': f'Storyblocks download failed: {str(e)}'}), 400
        else:
            # YouTube/Other logic: Extract direct MP4 URL
            resolution_map = {
                '2160p': 2160,
                '1080p': 1080,
                '720p': 720,
                'best': None  # None to select the best format
            }
            
            target_height = resolution_map.get(resolution, None)
            
            ydl_opts = {
                'format_sort': ['+res', 'ext:mp4:m4a'],  # Prioritize resolution, prefer MP4
                'quiet': True,
                'no_warnings': True,
                'cookiefile': os.getenv('COOKIE'),
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)  # Don't download
                    video_title = info.get('title', 'video')
                    formats = info.get('formats', [])
                    
                    # Filter formats for MP4, non-HLS/DASH, with video codec
                    mp4_formats = [
                        fmt for fmt in formats
                        if fmt.get('ext') == 'mp4' and
                           fmt.get('vcodec') != 'none' and
                           fmt.get('protocol') in ['https', 'http']  # Avoid m3u8, dash
                    ]
                    
                    if not mp4_formats:
                        return jsonify({
                            'error': 'No direct MP4 format found. Video may only be available in HLS/DASH format.'
                        }), 400
                    
                    # Select format based on requested resolution
                    selected_format = None
                    resolution_note = "Best available resolution"
                    
                    if target_height:
                        # Find format with the matching height
                        for fmt in sorted(mp4_formats, key=lambda x: x.get('height', 0), reverse=True):
                            if fmt.get('height') == target_height:
                                selected_format = fmt
                                resolution_note = f"{target_height}p"
                                break
                    if not selected_format:
                        # Fallback to best MP4 format
                        selected_format = max(
                            mp4_formats,
                            key=lambda x: x.get('height', 0),
                            default=None
                        )
                        if selected_format and selected_format.get('height'):
                            resolution_note = f"{selected_format.get('height')}p"
                    
                    if not selected_format or not selected_format.get('url'):
                        return jsonify({'error': 'No suitable MP4 format found'}), 400
                    
                    download_url = selected_format['url']
                    
                    # Check if the requested resolution is available
                    is_4k = any(fmt.get('height') == 2160 for fmt in mp4_formats)
                    is_1080p = any(fmt.get('height') == 1080 for fmt in mp4_formats)
                    is_720p = any(fmt.get('height') == 720 for fmt in mp4_formats)
                    
                    if resolution == '2160p' and not is_4k:
                        resolution_note = "4K not available, using best resolution"
                    elif resolution == '1080p' and not is_1080p:
                        resolution_note = "1080p not available, using best resolution"
                    elif resolution == '720p' and not is_720p:
                        resolution_note = "720p not available, using best resolution"
                    
                    return jsonify({
                        'success': True,
                        'title': video_title,
                        'resolution': resolution_note,
                        'download_url': download_url
                    })

            except yt_dlp.utils.DownloadError as e:
                return jsonify({'error': f'Failed to extract video info: {str(e)}'}), 400

    except Exception as e:
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)