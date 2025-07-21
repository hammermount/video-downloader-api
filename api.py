from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from downloader import Downloader, DownloadConfig, Platform, DownloadType
import tempfile
from pathlib import Path
import shutil
import yt_dlp

app = Flask(__name__)
CORS(app)

# Helper to detect platform
def detect_platform(url):
    for domain, platform in Downloader.SUPPORTED_PLATFORMS.items():
        if domain in url:
            return platform
    return Platform.UNKNOWN

# Endpoint 1: Fetch video metadata
@app.route('/api/info', methods=['POST'])
def fetch_info():
    try:
        data = request.get_json()
        url = data.get('url')
        if not url:
            return jsonify({'error': 'Missing URL'}), 400

        ydl_opts = {
            'quiet': True,
            'skip_download': True,
            'forcejson': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = [
                {
                    'format_id': f['format_id'],
                    'resolution': f.get('height'),
                    'ext': f.get('ext'),
                    'filesize': f.get('filesize') or f.get('filesize_approx')
                }
                for f in info.get('formats', [])
                if f.get('height') in [480, 720, 1080]
            ]
            return jsonify({
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'formats': formats
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Endpoint 2: Download the video in selected format
@app.route('/api/download', methods=['POST'])
def download_video():
    try:
        data = request.get_json()
        url = data.get('url')
        format_code = data.get('format_id')

        if not url or not format_code:
            return jsonify({'error': 'Missing URL or format_id'}), 400

        temp_dir = Path(tempfile.mkdtemp())
        platform = detect_platform(url)
        config = DownloadConfig(
            url=url,
            platform=platform,
            format=format_code,
            output_dir=temp_dir,
            download_type=DownloadType.VIDEO
        )
        downloader = Downloader(config)
        success = downloader.download()

        if not success:
            shutil.rmtree(temp_dir)
            return jsonify({'error': 'Download failed'}), 500

        files = list(temp_dir.rglob('*'))
        video_file = next((f for f in files if f.is_file()), None)
        if not video_file:
            shutil.rmtree(temp_dir)
            return jsonify({'error': 'No video file found'}), 500

        response = send_file(video_file, as_attachment=True)
        response.call_on_close(lambda: shutil.rmtree(temp_dir))
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, threaded=True)
